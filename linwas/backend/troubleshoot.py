# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sorun Giderme: tek tıkla tarama (salt okunur, root gerekmez).

Her kontrol bir CheckResult döner; arayüz sorunlu olanları çözüm düğmeleriyle gösterir.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Eşikler
_BOOT_MIN_FREE_MB = 150  # yeni çekirdek için /boot'ta gereken yaklaşık alan
_MEM_MIN_AVAILABLE = 0.10
_HOT_CELSIUS = 90
_SLOW_BOOT_SECONDS = 90
_APT_STALE_HOURS = 24 * 14
_BATTERY_WORN = 60


@dataclass
class CheckResult:
    id: str  # CHECKS içindeki kontrolün adı (check_ öneki olmadan), ör. "disk", "internet"
    ok: bool
    detail: str = ""  # teknik ayrıntı (İngilizce/ham); arayüz başlığı kendisi çevirir
    cause: str = ""  # sorunun nedeni (ör. ağ teşhisi: "wifi_off"); başlık ve çözümler buna göre
    target: str = ""  # çözümün uygulanacağı aygıt/bağlantı (ör. "wlp2s0")


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def check_disk(path: str = "/", min_free_ratio: float = 0.1) -> CheckResult:
    usage = shutil.disk_usage(path)
    free_gb = usage.free / 1024**3
    ok = usage.free / usage.total >= min_free_ratio and free_gb >= 2
    return CheckResult("disk", ok, f"{free_gb:.1f} GB free")


def check_internet() -> CheckResult:
    """İnternet yoksa nedenini de bulur (netdiag: kart, servis, Wi-Fi, adres, modem, DNS...)."""
    # nmcli networking connectivity: none / portal / limited / full / unknown
    code, out = _run(["nmcli", "networking", "connectivity", "check"])
    if code == 127:
        return CheckResult("internet", True, "nmcli not available")
    state = out.strip()
    try:
        from linwas.backend import netdiag

        # Bağlantı tamsa yalnızca vekil sunucuya bakılır (tarayıcı açmaz ama denetim geçer)
        finding = netdiag.proxy_problem() if state == "full" else netdiag.diagnose(_run)
    except Exception:
        return CheckResult("internet", state == "full", state)
    if finding is None or finding.cause == "ok":
        # NetworkManager'ın denetim adresi engelli olabilir; kendi testimiz geçtiyse sorun yok
        return CheckResult("internet", True, state)
    return CheckResult("internet", False, finding.detail or state, finding.cause, finding.target)


def check_packages() -> CheckResult:
    # dpkg --audit yarım kalmış/bozuk paketleri listeler; çıktı boşsa sorun yok
    code, out = _run(["dpkg", "--audit"])
    return CheckResult("packages", code == 0 and not out, out[:300])


def check_services() -> CheckResult:
    code, out = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    units = [line.split()[0] for line in out.splitlines() if line.strip()]
    return CheckResult("services", code == 0 and not units, ", ".join(units[:5]))


def check_sound() -> CheckResult:
    # PipeWire/PulseAudio sunucusu yanıt veriyor mu
    code, out = _run(["pactl", "info"])
    if code == 127:
        return CheckResult("sound", True, "pactl not available")
    return CheckResult("sound", code == 0, "" if code == 0 else out[:200])


def check_printing() -> CheckResult:
    code, out = _run(["systemctl", "is-active", "cups"])
    if out in ("inactive", "unknown") and code != 0:
        # CUPS kurulu değil ya da soket ile isteğe bağlı başlıyor: sorun sayılmaz
        return CheckResult("printing", True, out)
    return CheckResult("printing", out == "active", out)


def check_updates() -> CheckResult:
    from linwas.backend.packages import count_upgradable

    total, security = count_upgradable()
    return CheckResult("updates", security == 0, f"{total} updates, {security} security")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _mount_point(path: str) -> str:
    code, out = _run(["findmnt", "-no", "TARGET", "-T", path])
    return out.splitlines()[0].strip() if code == 0 and out else ""


def check_boot_space() -> CheckResult:
    """Ayrı /boot dolarsa çekirdek güncellemeleri yarım kalır (Debian kurulumunda sık)."""
    if _mount_point("/boot") != "/boot":
        return CheckResult("boot_space", True, "/boot is not separate")
    free_mb = shutil.disk_usage("/boot").free / 1024**2
    return CheckResult("boot_space", free_mb >= _BOOT_MIN_FREE_MB, f"{free_mb:.0f} MB free")


def check_home_space() -> CheckResult:
    home = str(Path.home())
    if _mount_point(home) in ("", "/"):
        return CheckResult("home_space", True, "home is on the system disk")
    result = check_disk(home)
    return CheckResult("home_space", result.ok, result.detail)


def parse_mount_options(mounts: str, target: str = "/") -> list[str]:
    """/proc/mounts içinde hedefin (son bağlamanın) seçenekleri."""
    options: list[str] = []
    for line in mounts.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == target:
            options = fields[3].split(",")
    return options


def check_readonly() -> CheckResult:
    """Dosya sistemi hatası olunca sistem diski salt okunur bağlanır; hiçbir şey kaydedilemez."""
    options = parse_mount_options(_read(Path("/proc/mounts")))
    return CheckResult("readonly", "ro" not in options, ",".join(options[:3]))


def check_memory() -> CheckResult:
    from linwas.backend.health import memory_usage

    usage = memory_usage()
    if usage is None or not usage.total:
        return CheckResult("memory", True, "unknown")
    available = 1 - usage.used / usage.total
    return CheckResult("memory", available >= _MEM_MIN_AVAILABLE, f"{usage.percent}% used")


def max_temperature(base: Path = Path("/sys/class/thermal")) -> float | None:
    """Termal bölgelerin en yükseği (°C); donanımdan bağımsız (AMD/Intel/ARM)."""
    temps = []
    for zone in base.glob("thermal_zone*"):
        raw = _read(zone / "temp")
        if raw.lstrip("-").isdigit():
            value = int(raw) / 1000
            if 0 < value < 150:  # bazı sürücüler anlamsız değer verir
                temps.append(value)
    return max(temps) if temps else None


def check_temperature() -> CheckResult:
    temp = max_temperature()
    if temp is None:
        return CheckResult("temperature", True, "no sensor")
    return CheckResult("temperature", temp < _HOT_CELSIUS, f"{temp:.0f} °C")


def check_clock() -> CheckResult:
    """Saat yanlışsa güvenli siteler ve güncellemeler sertifika hatası verir.

    Chrony varsa gerçek sapma okunur (ayrıntı "offset:<sn>"; Windows ile çift açılışta uykudan
    uyanınca saat 3 saat kayabiliyor); yoksa yalnız eşitlenmiş mi diye bakılır.
    """
    from linwas.core import clock

    offset = clock.offset_seconds()
    if offset is not None:
        return CheckResult("clock", abs(offset) < clock.WRONG_SECONDS, f"offset:{offset:.0f}")
    code, out = _run(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "NTP"])
    if code != 0:
        return CheckResult("clock", True, "timedatectl not available")
    values = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return CheckResult(
        "clock", values.get("NTPSynchronized") == "yes" or values.get("NTP") != "yes", out
    )


def check_graphics() -> CheckResult:
    """Ekran kartı sürücüsü yoksa ekran yazılımla çizilir (yavaş, oyunlar çalışmaz)."""
    from linwas.backend.driver_health import check_renderer

    item = check_renderer()
    if item is None:
        return CheckResult("graphics", True, "not checked")
    return CheckResult("graphics", item.ok, item.values.get("renderer", ""))


def check_driver_modules() -> CheckResult:
    """DKMS sürücüleri (NVIDIA, VirtualBox, Wi-Fi) çalışan çekirdek için derlenmemiş olabilir."""
    from linwas.backend.driver_health import check_dkms

    item = check_dkms()
    if item is None:
        return CheckResult("driver_modules", True, "no dkms modules")
    return CheckResult("driver_modules", item.ok, item.values.get("modules", ""))


def check_package_lists() -> CheckResult:
    from linwas.backend.packages import apt_cache_age_hours

    age = apt_cache_age_hours()
    if age is None:
        return CheckResult("package_lists", True, "unknown")
    return CheckResult("package_lists", age < _APT_STALE_HOURS, f"{age / 24:.0f} days old")


def parse_boot_seconds(out: str) -> float | None:
    """`systemd-analyze time` → toplam süre (sn). Örn. "... = 1min 5.204s"."""
    m = re.search(r"=\s*((?:\d+min\s*)?[\d.]+m?s)\s*$", out.splitlines()[0] if out else "")
    if not m:
        return None
    total = 0.0
    for value, unit in re.findall(r"([\d.]+)(min|ms|s)", m.group(1)):
        total += float(value) * {"min": 60, "s": 1, "ms": 0.001}[unit]
    return total


def check_boot_time() -> CheckResult:
    code, out = _run(["systemd-analyze", "time"])
    seconds = parse_boot_seconds(out) if code == 0 else None
    if seconds is None:
        return CheckResult("boot_time", True, "unknown")
    return CheckResult("boot_time", seconds < _SLOW_BOOT_SECONDS, f"{seconds:.0f} s")


def check_battery() -> CheckResult:
    from linwas.backend.power import list_batteries

    batteries = list_batteries()
    worn = [b for b in batteries if b.health is not None and b.health < _BATTERY_WORN]
    if not batteries:
        return CheckResult("battery", True, "no battery")
    detail = ", ".join(f"{b.name} {b.health}%" for b in batteries if b.health is not None)
    return CheckResult("battery", not worn, detail)


CHECKS: tuple[Callable[[], CheckResult], ...] = (
    check_internet,
    check_clock,
    check_readonly,
    check_disk,
    check_home_space,
    check_boot_space,
    check_memory,
    check_temperature,
    check_packages,
    check_package_lists,
    check_services,
    check_driver_modules,
    check_graphics,
    check_sound,
    check_printing,
    check_updates,
    check_boot_time,
    check_battery,
)


def run_all() -> list[CheckResult]:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # bir kontrolün hatası taramayı durdurmasın
            results.append(CheckResult(check.__name__.removeprefix("check_"), True, str(exc)))
    return results


def restart_sound() -> bool:
    """Kullanıcı ses servislerini yeniden başlatır (systemd --user, root gerekmez)."""
    return (
        _run(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"])[0]
        == 0
    )
