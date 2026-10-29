# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kaynak izleyici: CPU, bellek, GPU, disk ve ağ kullanımını canlı ölçer.

Hepsi /proc ve /sys'ten okunur; root gerekmez. Yalnızca NVIDIA (kapalı sürücü) için
`nvidia-smi` çalıştırılır. Hızlar iki örnek arasındaki farktan hesaplanır, bu yüzden
`ResourceSampler.sample()` düzenli aralıkla çağrılmalıdır (ilk çağrıda hızlar 0'dır).

Hibrit grafikli dizüstülerde uyuyan (runtime suspend) GPU sorgulanmaz: sorgu onu
uyandırır ve pil tüketir. Bu durumda "uykuda" gösterilir.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

PROC = Path("/proc")
SYS = Path("/sys")

# /proc/diskstats sektörü çekirdekte her zaman 512 bayttır (aygıtın sektör boyutundan bağımsız)
_DISKSTAT_SECTOR = 512
# CPU sıcaklığı veren hwmon sürücüleri (Intel, AMD, ARM); yoksa acpitz
_CPU_HWMON = ("coretemp", "k10temp", "zenpower", "cpu_thermal")
_VENDORS = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel"}


@dataclass
class GpuStats:
    name: str
    vendor: str
    # "active" | "sleeping" (uykuda, sorgulanmadı) | "limited" (kullanım ölçülemiyor)
    state: str = "active"
    busy_pct: float | None = None
    mem_used: int | None = None  # bayt
    mem_total: int | None = None
    temp_c: float | None = None
    freq_mhz: int | None = None
    freq_max_mhz: int | None = None


@dataclass
class ProcessStats:
    pid: int
    name: str
    cpu_pct: (
        float  # tek çekirdeğin yüzdesi (Windows'taki gibi toplamın değil): 2 çekirdek dolu = %200
    )
    rss: int  # bayt


@dataclass
class ResourceSnapshot:
    time: float
    cpu_pct: float = 0.0
    cpu_cores: list[float] = field(default_factory=list)
    cpu_temp_c: float | None = None
    cpu_freq_mhz: int | None = None
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mem_total: int = 0
    mem_used: int = 0
    mem_cache: int = 0
    swap_total: int = 0
    swap_used: int = 0
    disk_read_bps: float = 0.0
    disk_write_bps: float = 0.0
    disk_busy_pct: float = 0.0
    # (bağlama noktası, kullanılan, toplam) — kök ve ayrı bölümdeyse /home
    disk_usage: list[tuple[str, int, int]] = field(default_factory=list)
    net_rx_bps: float = 0.0
    net_tx_bps: float = 0.0
    net_rx_total: int = 0  # oturum başından beri (arayüz sayaçları)
    net_tx_total: int = 0
    net_interfaces: list[str] = field(default_factory=list)
    gpus: list[GpuStats] = field(default_factory=list)
    top_processes: list[ProcessStats] = field(default_factory=list)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_int(path: Path) -> int | None:
    try:
        return int(_read(path).strip())
    except ValueError:
        return None


# --- CPU ---


def parse_proc_stat(text: str) -> dict[str, tuple[int, int]]:
    """/proc/stat → {"cpu": (boşta, toplam), "cpu0": ...}; boşta = idle + iowait."""
    result: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        if not line.startswith("cpu"):
            break
        parts = line.split()
        try:
            values = [int(v) for v in parts[1:]]
        except ValueError:
            continue
        # guest/guest_nice zaten user/nice içinde sayılır; toplama katılmaz
        total = sum(values[:8])
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        result[parts[0]] = (idle, total)
    return result


def _usage(prev: tuple[int, int] | None, cur: tuple[int, int]) -> float:
    if prev is None:
        return 0.0
    d_total = cur[1] - prev[1]
    if d_total <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1 - (cur[0] - prev[0]) / d_total)))


def _cpu_temp() -> float | None:
    fallback: float | None = None
    for hwmon in sorted((SYS / "class" / "hwmon").glob("hwmon*")):
        name = _read(hwmon / "name").strip()
        if name in _CPU_HWMON:
            value = _read_int(hwmon / "temp1_input")
            if value is not None:
                return value / 1000
        elif name == "acpitz" and fallback is None:
            value = _read_int(hwmon / "temp1_input")
            fallback = value / 1000 if value is not None else None
    return fallback


def _cpu_freq() -> int | None:
    freqs = [
        v
        for p in (SYS / "devices" / "system" / "cpu").glob("cpu[0-9]*/cpufreq/scaling_cur_freq")
        if (v := _read_int(p)) is not None
    ]
    return round(sum(freqs) / len(freqs) / 1000) if freqs else None


# --- Bellek ---


def parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo → {anahtar: bayt}."""
    result: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            result[key] = int(parts[0]) * (1024 if len(parts) > 1 else 1)
    return result


# --- Disk ---


def _physical_disks() -> set[str]:
    """Gerçek diskler (loop, zram, dm gibi sanal aygıtlar sayılmaz; çift sayım olmasın)."""
    return {p.name for p in (SYS / "block").iterdir() if (p / "device").exists()}


def parse_diskstats(text: str, disks: set[str]) -> tuple[int, int, int]:
    """/proc/diskstats → (okunan bayt, yazılan bayt, G/Ç'de geçen ms) toplamı."""
    read = written = busy = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 13 or parts[2] not in disks:
            continue
        read += int(parts[5]) * _DISKSTAT_SECTOR
        written += int(parts[9]) * _DISKSTAT_SECTOR
        busy += int(parts[12])
    return read, written, busy


def _disk_usage() -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    seen: set[int] = set()
    for mount in ("/", str(Path.home())):
        try:
            dev = os.stat(mount).st_dev
            if dev in seen:
                continue
            seen.add(dev)
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        result.append((mount, usage.total - usage.free, usage.total))
    return result


# --- Ağ ---


def _physical_interfaces() -> set[str]:
    """Gerçek ağ kartları (Wi-Fi, Ethernet); docker/köprü/VPN arayüzleri çift sayılmasın."""
    net = SYS / "class" / "net"
    try:
        return {p.name for p in net.iterdir() if (p / "device").exists()}
    except OSError:
        return set()


def parse_net_dev(text: str, interfaces: set[str] | None) -> tuple[int, int, list[str]]:
    """/proc/net/dev → (alınan bayt, gönderilen bayt, sayılan arayüzler).

    `interfaces` boşsa (gerçek kart bulunamadı) lo dışındaki hepsi sayılır.
    """
    rx = tx = 0
    used: list[str] = []
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        name = name.strip()
        parts = rest.split()
        if len(parts) < 9 or name == "lo" or (interfaces and name not in interfaces):
            continue
        rx += int(parts[0])
        tx += int(parts[8])
        used.append(name)
    return rx, tx, used


# --- GPU ---


def _pci_slot(card: Path) -> str:
    try:
        return (card / "device").resolve().name.lower()
    except OSError:
        return ""


def _hwmon_temp(device: Path) -> float | None:
    for hwmon in (device / "hwmon").glob("hwmon*"):
        value = _read_int(hwmon / "temp1_input")
        if value is not None:
            return value / 1000
    return None


def _num(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None  # "[N/A]", "[Not Supported]"


def parse_nvidia_smi(text: str) -> dict[str, GpuStats]:
    """nvidia-smi CSV çıktısı → {pci yuvası (0000:01:00.0): GpuStats}."""
    result: dict[str, GpuStats] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        bus, name, util, used, total, temp = parts[:6]
        mib = 1024 * 1024
        used_v, total_v = _num(used), _num(total)
        # nvidia-smi yuvayı 8 haneli alanla verir (00000000:01:00.0); sysfs 4 haneli
        slot = bus.lower()[-12:]
        result[slot] = GpuStats(
            name=name,
            vendor="NVIDIA",
            busy_pct=_num(util),
            mem_used=int(used_v * mib) if used_v is not None else None,
            mem_total=int(total_v * mib) if total_v is not None else None,
            temp_c=_num(temp),
        )
    return result


def _nvidia_smi() -> dict[str, GpuStats]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {}
    try:
        out = subprocess.run(
            [
                exe,
                "--query-gpu=pci.bus_id,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return parse_nvidia_smi(out)


def _intel_freq(card: Path) -> tuple[int | None, int | None]:
    # i915: cardN/gt_act_freq_mhz; xe: cardN/device/tile0/gt0/freq0/act_freq
    act = _read_int(card / "gt_act_freq_mhz")
    if act is not None:
        return act, _read_int(card / "gt_RP0_freq_mhz") or _read_int(card / "gt_max_freq_mhz")
    freq = card / "device" / "tile0" / "gt0" / "freq0"
    return _read_int(freq / "act_freq"), _read_int(freq / "rp0_freq")


def read_gpus() -> list[GpuStats]:
    cards = sorted(
        p for p in (SYS / "class" / "drm").glob("card*") if re.fullmatch(r"card\d+", p.name)
    )
    gpus: list[GpuStats] = []
    nvidia: dict[str, GpuStats] | None = None
    for card in cards:
        device = card / "device"
        vendor = _VENDORS.get(_read(device / "vendor").strip(), "")
        if not vendor:
            continue
        name = f"{vendor} GPU"
        if _read(device / "power" / "runtime_status").strip() == "suspended":
            gpus.append(GpuStats(name=name, vendor=vendor, state="sleeping"))
            continue
        if vendor == "NVIDIA":
            if nvidia is None:
                nvidia = _nvidia_smi()
            stats = nvidia.get(_pci_slot(card))
            # nouveau ya da nvidia-smi yok: kullanım ölçülemez
            gpus.append(stats or GpuStats(name=name, vendor=vendor, state="limited"))
        elif vendor == "AMD":
            busy = _read_int(device / "gpu_busy_percent")
            gpus.append(
                GpuStats(
                    name=name,
                    vendor=vendor,
                    state="active" if busy is not None else "limited",
                    busy_pct=float(busy) if busy is not None else None,
                    mem_used=_read_int(device / "mem_info_vram_used"),
                    mem_total=_read_int(device / "mem_info_vram_total"),
                    temp_c=_hwmon_temp(device),
                )
            )
        else:
            # Intel'in kullanım oranı root olmadan okunamaz (intel_gpu_top perf ister);
            # anlık frekans en yakın göstergedir
            act, top = _intel_freq(card)
            gpus.append(
                GpuStats(name=name, vendor=vendor, state="limited", freq_mhz=act, freq_max_mhz=top)
            )
    return gpus


# --- Süreçler ---


def _process_times() -> dict[int, tuple[str, int, int]]:
    """{pid: (ad, utime+stime jiffy, rss bayt)}."""
    page = os.sysconf("SC_PAGE_SIZE")
    result: dict[int, tuple[str, int, int]] = {}
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        stat = _read(entry / "stat")
        # Ad parantez içinde ve boşluk içerebilir: son ")" sonrasını böl
        lpar, rpar = stat.find("("), stat.rfind(")")
        if lpar < 0 or rpar < 0:
            continue
        fields = stat[rpar + 2 :].split()
        if len(fields) < 22:
            continue
        try:
            jiffies = int(fields[11]) + int(fields[12])
            rss = int(fields[21]) * page
        except ValueError:
            continue
        result[int(entry.name)] = (stat[lpar + 1 : rpar], jiffies, rss)
    return result


# --- Örnekleyici ---


class ResourceSampler:
    """Ardışık örneklerden hız ve yüzde hesaplar; tek iş parçacığından çağrılmalı."""

    def __init__(self, top_count: int = 8) -> None:
        self._top_count = top_count
        self._clk = os.sysconf("SC_CLK_TCK")
        self._prev_time: float | None = None
        self._prev_cpu: dict[str, tuple[int, int]] = {}
        self._prev_disk: tuple[int, int, int] | None = None
        self._prev_net: tuple[int, int] | None = None
        self._prev_procs: dict[int, tuple[str, int, int]] = {}
        self._disks = _physical_disks()
        self._ifaces = _physical_interfaces()
        self._slow_at = 0.0
        self._slow: tuple[list[tuple[str, int, int]], float | None] = ([], None)

    def sample(self) -> ResourceSnapshot:
        now = time.monotonic()
        dt = now - self._prev_time if self._prev_time is not None else 0.0
        snap = ResourceSnapshot(time=time.time())

        cpu = parse_proc_stat(_read(PROC / "stat"))
        if "cpu" in cpu:
            snap.cpu_pct = _usage(self._prev_cpu.get("cpu"), cpu["cpu"])
        snap.cpu_cores = [_usage(self._prev_cpu.get(k), v) for k, v in cpu.items() if k != "cpu"]
        self._prev_cpu = cpu
        snap.cpu_freq_mhz = _cpu_freq()
        load = _read(PROC / "loadavg").split()
        if len(load) >= 3:
            snap.load_avg = (float(load[0]), float(load[1]), float(load[2]))

        mem = parse_meminfo(_read(PROC / "meminfo"))
        snap.mem_total = mem.get("MemTotal", 0)
        snap.mem_used = snap.mem_total - mem.get("MemAvailable", mem.get("MemFree", 0))
        snap.mem_cache = mem.get("Cached", 0) + mem.get("Buffers", 0)
        snap.swap_total = mem.get("SwapTotal", 0)
        snap.swap_used = snap.swap_total - mem.get("SwapFree", 0)

        disk = parse_diskstats(_read(PROC / "diskstats"), self._disks)
        if self._prev_disk and dt > 0:
            snap.disk_read_bps = max(0, disk[0] - self._prev_disk[0]) / dt
            snap.disk_write_bps = max(0, disk[1] - self._prev_disk[1]) / dt
            # Birden çok diskte toplam meşguliyet %100'ü aşabilir; en fazla 100
            snap.disk_busy_pct = min(100.0, max(0, disk[2] - self._prev_disk[2]) / (dt * 10))
        self._prev_disk = disk

        rx, tx, used = parse_net_dev(_read(PROC / "net" / "dev"), self._ifaces)
        if self._prev_net and dt > 0:
            snap.net_rx_bps = max(0, rx - self._prev_net[0]) / dt
            snap.net_tx_bps = max(0, tx - self._prev_net[1]) / dt
        self._prev_net = (rx, tx)
        snap.net_rx_total, snap.net_tx_total, snap.net_interfaces = rx, tx, used

        # Yavaş değişenler (doluluk, sıcaklık) 5 saniyede bir
        if now - self._slow_at >= 5:
            self._slow = (_disk_usage(), _cpu_temp())
            self._slow_at = now
        snap.disk_usage, snap.cpu_temp_c = self._slow

        snap.gpus = read_gpus()
        snap.top_processes = self._top_processes(dt)
        self._prev_time = now
        return snap

    def _top_processes(self, dt: float) -> list[ProcessStats]:
        procs = _process_times()
        stats: list[ProcessStats] = []
        if dt > 0:
            for pid, (name, jiffies, rss) in procs.items():
                prev = self._prev_procs.get(pid)
                # Aynı PID yeniden kullanıldıysa (ad değişti) önceki sayaç geçersiz
                if prev is None or prev[0] != name:
                    continue
                cpu = 100.0 * (jiffies - prev[1]) / self._clk / dt
                stats.append(ProcessStats(pid=pid, name=name, cpu_pct=max(0.0, cpu), rss=rss))
        self._prev_procs = procs
        stats.sort(key=lambda p: (p.cpu_pct, p.rss), reverse=True)
        return stats[: self._top_count]


def format_bytes(value: float) -> str:
    """1536 → "1.5 KB"; ikili birimler (Windows Görev Yöneticisi gibi)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
