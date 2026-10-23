"""Donanım bilgisi okuma (Qt'siz, root gerekmez; bellek modülleri hariç).

Kaynaklar (kullanıcı makinesinde doğrulandı, Pardus 23):
- Bilgisayar: /sys/class/dmi/id (sys_vendor, product_name, product_family, board_name,
  bios_version, bios_date, chassis_type)
- İşlemci: `lscpu` (LANG=C), yük /proc/stat, sıcaklık hwmon (Intel `coretemp` temp1 =
  "Package id 0", AMD `k10temp`/`zenpower`, yoksa `acpitz`)
- Bellek: /proc/meminfo; modüller `dmidecode -t memory` (root helper `hardware.memory_report`)
- Diskler: `lsblk -J`; NVMe sıcaklığı hwmon `nvme` (device bağlantısı …/nvme/nvmeN)
- Ekran: `xrandr --current` (X11; Wayland'de XWayland çıkışları)
- Pil: /sys/class/power_supply/BAT*
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

DMI = Path("/sys/class/dmi/id")
HWMON = Path("/sys/class/hwmon")
PROC_STAT = Path("/proc/stat")
MEMINFO = Path("/proc/meminfo")
POWER_SUPPLY = Path("/sys/class/power_supply")
# Root helper'ın yazdığı bellek modülü raporu (herkes okuyabilir; seri numarası yok)
MEMORY_REPORT = Path("/var/lib/linwas/memory-modules.json")

OK, WARN, BAD = "ok", "warn", "bad"

# SMBIOS kasa türleri (DMTF): dizüstü / masaüstü ayrımı
_LAPTOP_CHASSIS = {8, 9, 10, 11, 14, 30, 31, 32}
_DESKTOP_CHASSIS = {3, 4, 5, 6, 7, 13, 15, 16, 24, 35, 36}


def _run(cmd: list[str], timeout: int = 15) -> str:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_int(path: Path) -> int | None:
    text = _read(path)
    return int(text) if text.lstrip("-").isdigit() else None


# --- Bilgisayar ---


@dataclass
class Machine:
    vendor: str = ""
    product: str = ""
    family: str = ""
    board: str = ""
    bios_version: str = ""
    bios_date: date | None = None
    chassis: str = "other"  # laptop | desktop | other

    @property
    def title(self) -> str:
        """Kısa ad: aile (ör. "HP Victus"), yoksa üretici + model."""
        if self.family:
            return self.family
        if self.vendor and self.vendor.lower() not in self.product.lower():
            return f"{self.vendor} {self.product}".strip()
        return self.product or self.vendor


def clean_family(text: str) -> str:
    """ "103C_5335M7 HP Victus" → "HP Victus" (baştaki üretici kodu atılır)."""
    parts = text.split()
    if len(parts) > 1 and "_" in parts[0]:
        parts = parts[1:]
    cleaned = " ".join(parts)
    if cleaned.lower() in ("", "to be filled by o.e.m.", "default string", "not applicable"):
        return ""
    return cleaned


def parse_dmi_date(text: str) -> date | None:
    """DMI tarihi "MM/DD/YYYY"."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", text.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def machine_info(root: Path = DMI) -> Machine:
    chassis = _read_int(root / "chassis_type") or 0
    kind = (
        "laptop"
        if chassis in _LAPTOP_CHASSIS
        else "desktop"
        if chassis in _DESKTOP_CHASSIS
        else "other"
    )
    return Machine(
        vendor=_read(root / "sys_vendor"),
        product=_read(root / "product_name"),
        family=clean_family(_read(root / "product_family")),
        board=_read(root / "board_name"),
        bios_version=_read(root / "bios_version"),
        bios_date=parse_dmi_date(_read(root / "bios_date")),
        chassis=kind,
    )


# --- İşlemci ---


@dataclass
class Cpu:
    model: str = ""
    cores: int = 0
    threads: int = 0
    max_mhz: int = 0


def parse_lscpu(output: str) -> Cpu:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields.setdefault(key.strip(), value.strip())

    def num(key: str) -> float:
        try:
            return float(fields.get(key, "").replace(",", "."))
        except ValueError:
            return 0.0

    per_socket = int(num("Core(s) per socket"))
    sockets = int(num("Socket(s)")) or 1
    return Cpu(
        model=re.sub(r"\s+", " ", fields.get("Model name", "")).strip(),
        cores=per_socket * sockets,
        threads=int(num("CPU(s)")),
        max_mhz=int(num("CPU max MHz")),
    )


def cpu_info() -> Cpu:
    return parse_lscpu(_run(["lscpu"]))


def parse_proc_stat(text: str) -> tuple[int, int]:
    """/proc/stat ilk satırı → (boşta, toplam) tıkları."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            values = [int(v) for v in line.split()[1:] if v.isdigit()]
            idle = values[3] + (values[4] if len(values) > 4 else 0)  # idle + iowait
            return idle, sum(values[:8])
    return 0, 0


class CpuSampler:
    """İki okuma arasındaki işlemci yükü (%)."""

    def __init__(self, path: Path = PROC_STAT) -> None:
        self._path = path
        self._last = parse_proc_stat(_read(path))

    def sample(self) -> int:
        idle, total = parse_proc_stat(_read(self._path))
        d_idle, d_total = idle - self._last[0], total - self._last[1]
        self._last = (idle, total)
        if d_total <= 0:
            return 0
        return max(0, min(100, round(100 * (d_total - d_idle) / d_total)))


# Tercih sırası: işlemci paketi sıcaklığını veren sürücüler
_CPU_HWMON = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")


def _hwmon_dirs(root: Path) -> list[Path]:
    try:
        return sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return []


def cpu_temperature(root: Path = HWMON) -> float | None:
    """İşlemci sıcaklığı (°C); okunamazsa None."""
    found: dict[str, float] = {}
    for d in _hwmon_dirs(root):
        name = _read(d / "name")
        if name not in _CPU_HWMON or name in found:
            continue
        value = _read_int(d / "temp1_input")
        if value is not None:
            found[name] = value / 1000
    for name in _CPU_HWMON:
        if name in found:
            return found[name]
    return None


# --- Bellek ---


@dataclass
class MemoryUsage:
    total: int = 0
    used: int = 0
    swap_total: int = 0
    swap_used: int = 0

    @property
    def percent(self) -> int:
        return round(self.used * 100 / self.total) if self.total else 0


def parse_meminfo(text: str) -> MemoryUsage:
    v: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            v[key.strip()] = int(parts[0]) * 1024
    total = v.get("MemTotal", 0)
    available = v.get("MemAvailable", v.get("MemFree", 0))
    swap_total = v.get("SwapTotal", 0)
    return MemoryUsage(
        total=total,
        used=max(0, total - available),
        swap_total=swap_total,
        swap_used=max(0, swap_total - v.get("SwapFree", 0)),
    )


def memory_usage(path: Path = MEMINFO) -> MemoryUsage:
    return parse_meminfo(_read(path))


@dataclass
class MemoryModule:
    locator: str  # yuva adı (ör. "DIMM 1")
    size: str  # "8 GB"
    type: str = ""  # DDR4, DDR5 …
    speed: str = ""  # "3200 MT/s"
    manufacturer: str = ""
    part: str = ""


@dataclass
class MemoryReport:
    slots: int = 0
    max_capacity: str = ""
    modules: list[MemoryModule] = field(default_factory=list)


def parse_dmidecode_memory(text: str) -> MemoryReport:
    """`dmidecode -t memory` → yuvalar ve takılı modüller (seri numarası alınmaz)."""
    report = MemoryReport()
    for block in text.split("\n\n"):
        lines = [ln.strip() for ln in block.splitlines()]
        fields: dict[str, str] = {}
        for ln in lines[1:]:
            key, sep, value = ln.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        header = lines[1] if len(lines) > 1 else ""
        if header == "Physical Memory Array":
            report.max_capacity = fields.get("Maximum Capacity", "")
            devices = fields.get("Number Of Devices", "")
            if devices.isdigit():
                report.slots += int(devices)
        elif header == "Memory Device":
            size = fields.get("Size", "")
            if not size or size.startswith("No Module"):
                continue

            def clean(value: str) -> str:
                return "" if value.lower() in ("unknown", "not specified", "undefined") else value

            report.modules.append(
                MemoryModule(
                    locator=clean(fields.get("Locator", "")),
                    size=size,
                    type=clean(fields.get("Type", "")),
                    speed=clean(fields.get("Configured Memory Speed", fields.get("Speed", ""))),
                    manufacturer=clean(fields.get("Manufacturer", "")),
                    part=clean(fields.get("Part Number", "")),
                )
            )
    return report


def report_to_json(report: MemoryReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False)


def read_memory_report(path: Path = MEMORY_REPORT) -> MemoryReport | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        modules = [MemoryModule(**m) for m in data.get("modules", [])]
    except (OSError, ValueError, TypeError):
        return None
    return MemoryReport(
        slots=int(data.get("slots", 0)),
        max_capacity=str(data.get("max_capacity", "")),
        modules=modules,
    )


# --- Diskler ---


@dataclass
class Disk:
    name: str
    model: str
    size: str
    kind: str  # nvme | ssd | hdd
    transport: str  # nvme | sata | usb | …
    system: bool = False  # kök dosya sistemi bu diskte
    removable: bool = False
    temperature: float | None = None


def _has_root(dev: dict) -> bool:
    mounts = dev.get("mountpoints") or [dev.get("mountpoint")]
    if "/" in [m for m in mounts if m]:
        return True
    return any(_has_root(c) for c in dev.get("children") or [])


def parse_lsblk(output: str) -> list[Disk]:
    """`lsblk -J -e7 -o NAME,MODEL,SIZE,ROTA,TRAN,TYPE,RM,MOUNTPOINTS` → fiziksel diskler."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    disks = []
    for dev in data.get("blockdevices", []):
        name = str(dev.get("name", ""))
        if dev.get("type") != "disk" or name.startswith(("loop", "zram", "ram")):
            continue
        tran = str(dev.get("tran") or "")
        rota = dev.get("rota") in (True, "1", 1)
        kind = "nvme" if name.startswith("nvme") or tran == "nvme" else "hdd" if rota else "ssd"
        disks.append(
            Disk(
                name=name,
                model=re.sub(r"\s+", " ", str(dev.get("model") or "")).strip(),
                size=str(dev.get("size") or ""),
                kind=kind,
                transport=tran,
                system=_has_root(dev),
                removable=dev.get("rm") in (True, "1", 1),
            )
        )
    return disks


def _nvme_temperatures(root: Path = HWMON) -> dict[str, float]:
    """{"nvme0": 33.0} — hwmon `nvme` aygıtının device bağlantısından denetleyici adı."""
    temps: dict[str, float] = {}
    for d in _hwmon_dirs(root):
        if _read(d / "name") != "nvme":
            continue
        try:
            ctrl = Path(os.path.realpath(d / "device")).name  # …/nvme/nvme0
        except OSError:
            continue
        value = _read_int(d / "temp1_input")
        if value is not None:
            temps[ctrl] = value / 1000
    return temps


def disks() -> list[Disk]:
    out = _run(["lsblk", "-J", "-e7", "-o", "NAME,MODEL,SIZE,ROTA,TRAN,TYPE,RM,MOUNTPOINTS"])
    result = parse_lsblk(out)
    temps = _nvme_temperatures()
    for disk in result:
        m = re.match(r"^(nvme\d+)n\d+$", disk.name)
        if m:
            disk.temperature = temps.get(m.group(1))
    return result


# --- Ekran ---


@dataclass
class Display:
    output: str  # eDP-1, HDMI-1 …
    width: int
    height: int
    refresh: float
    diagonal_in: float | None
    internal: bool
    primary: bool


def parse_xrandr(output: str) -> list[Display]:
    displays: list[Display] = []
    current: dict | None = None
    for line in output.splitlines():
        m = re.match(
            r"^(\S+) connected( primary)?\s*(\d+)x(\d+)\+\d+\+\d+.*?(\d+)mm x (\d+)mm", line
        )
        if m:
            w_mm, h_mm = int(m.group(5)), int(m.group(6))
            diag = math.hypot(w_mm, h_mm) / 25.4 if w_mm and h_mm else None
            name = m.group(1)
            current = {
                "output": name,
                "width": int(m.group(3)),
                "height": int(m.group(4)),
                "refresh": 0.0,
                "diagonal_in": round(diag, 1) if diag else None,
                "internal": name.startswith(("eDP", "LVDS", "DSI")),
                "primary": bool(m.group(2)),
            }
            displays.append(Display(**current))
            continue
        if current is not None and "*" in line:
            r = re.search(r"(\d+(?:\.\d+)?)\*", line)
            if r:
                displays[-1].refresh = float(r.group(1))
            current = None
    return displays


def displays() -> list[Display]:
    return parse_xrandr(_run(["xrandr", "--current"], timeout=10))


# --- Pil ---


@dataclass
class Battery:
    name: str
    health: int | None  # tasarım kapasitesine göre %
    cycles: int | None
    full_wh: float | None
    design_wh: float | None
    capacity: int | None  # şu anki şarj %


def batteries(root: Path = POWER_SUPPLY) -> list[Battery]:
    result = []
    for d in _hwmon_dirs(root):
        if _read(d / "type") != "Battery":
            continue
        full = _read_int(d / "energy_full") or _read_int(d / "charge_full")
        design = _read_int(d / "energy_full_design") or _read_int(d / "charge_full_design")
        energy = (d / "energy_full").exists()
        health = round(full * 100 / design) if full and design else None
        cycles = _read_int(d / "cycle_count")
        result.append(
            Battery(
                name=d.name,
                health=min(health, 100) if health is not None else None,
                cycles=cycles if cycles and cycles > 0 else None,
                full_wh=full / 1e6 if full and energy else None,
                design_wh=design / 1e6 if design and energy else None,
                capacity=_read_int(d / "capacity"),
            )
        )
    return result


# --- Durum değerlendirmesi ---


def cpu_temp_state(temp: float | None) -> str:
    if temp is None or temp < 85:
        return OK
    return WARN if temp < 95 else BAD


def usage_state(percent: int, warn: int = 80, bad: int = 92) -> str:
    return BAD if percent >= bad else WARN if percent >= warn else OK


def battery_state(health: int | None) -> str:
    if health is None or health >= 80:
        return OK
    return WARN if health >= 60 else BAD


# --- Rapor ve AI bağlamı ---


def summary_dict() -> dict[str, object]:
    """Sistem raporu, panoya kopyalama ve AI bağlamı için düz özet."""
    m = machine_info()
    cpu = cpu_info()
    mem = memory_usage()
    return {
        "computer": m.title or m.product,
        "model": m.product,
        "bios": f"{m.bios_version} {m.bios_date.isoformat() if m.bios_date else ''}".strip(),
        "cpu": f"{cpu.model} ({cpu.cores} cores / {cpu.threads} threads)",
        "memory_gb": round(mem.total / 1024**3, 1),
        "disks": [f"{d.model or d.name} {d.size} {d.kind}" for d in disks()],
        "displays": [f"{d.output} {d.width}x{d.height} {d.refresh:g}Hz" for d in displays()],
        "batteries": [f"{b.name} health {b.health}%" for b in batteries() if b.health is not None],
    }
