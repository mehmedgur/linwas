"""Gelişmiş güç seçenekleri: bu bilgisayarda hangi ayar destekleniyor, hazırda bekletme ve
çakışan güç araçları (kullanıcı yetkisiyle okunur)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from linwas.backend.drivers import dpkg_installed
from linwas.core import power_agent, power_apply
from linwas.core.powerplan import SETTINGS

# Desteklenmeme nedenleri (arayüz çevirir)
NO_HARDWARE = "no_hardware"
NOT_LAPTOP = "not_laptop"
NO_DESKTOP = "no_desktop"  # masaüstü ortamı desteklenmiyor (şimdilik yalnızca GNOME)
NO_PPD = "no_ppd"
NO_IW = "no_iw"
NO_HDPARM = "no_hdparm"
MANAGED = "managed"  # başka güç aracı yönetiyor
PPD = "ppd"  # sistemin güç kipi (power-profiles-daemon) yönetiyor

USER_SETTINGS = frozenset(s.id for s in SETTINGS if s.scope == "user")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _has_ambient_sensor() -> bool:
    iio = Path("/sys/bus/iio/devices")
    return iio.is_dir() and any(any(d.glob("in_illuminance*")) for d in iio.iterdir())


def _policy_values(name: str) -> tuple[str, ...]:
    policy = power_apply.CPUFREQ / "policy0"
    return tuple(_read(policy / name).split())


@dataclass
class ConflictTool:
    name: str
    package: str
    removable: str  # "apt" | "snap" | "" (kendi kaldırıcısıyla)


@dataclass
class HibernateInfo:
    available: bool
    reasons: list[str] = field(default_factory=list)  # kernel | lockdown | swap | resume


@dataclass
class PowerSupport:
    unsupported: dict[str, str]  # ayar → neden; listede olmayan destekleniyor
    values: dict[str, tuple[str, ...]]  # yalnızca bu makinede geçerli değerler (bazı ayarlar)
    conflicts: list[ConflictTool]
    hibernate: HibernateInfo
    laptop: bool
    # power-profiles-daemon çalışırken onun yönettiği işlemci ayarları; özel planda "İşlemciyi
    # Linwas yönetsin" kapalıyken bunlar değiştirilemez
    ppd_owned: frozenset[str] = frozenset()


AGENT_PATH = Path("/usr/lib/linwas/linwas-power-agent")


def agent_running() -> bool:
    """Bu kullanıcının oturumunda güç ajanı (masaüstü ayarlarını uygulayan) çalışıyor mu."""
    uid = os.getuid()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != uid:
                continue
            if b"linwas.core.power_agent" in (proc / "cmdline").read_bytes():
                return True
        except OSError:
            continue
    return False


def taken_over() -> bool:
    """Yönetim daha önce "Linwas yönetsin" ile devralındı mı (geri verilebilir)."""
    return power_apply.TAKEOVER_PATH.exists()


def conflicts() -> list[ConflictTool]:
    out: list[ConflictTool] = []
    for name, pkg in power_apply.conflicting_tools():
        if dpkg_installed(pkg):
            removable = "apt"
        elif shutil.which("snap") and (r := _run(["snap", "list", pkg])) and r.returncode == 0:
            removable = "snap"
        else:
            removable = ""
        out.append(ConflictTool(name, pkg, removable))
    return out


def _can_hibernate() -> bool:
    r = _run(
        [
            "gdbus",
            "call",
            "--system",
            "--dest",
            "org.freedesktop.login1",
            "--object-path",
            "/org/freedesktop/login1",
            "--method",
            "org.freedesktop.login1.Manager.CanHibernate",
        ]
    )
    return bool(r and r.returncode == 0 and "'yes'" in r.stdout)


def _meminfo_kb(key: str) -> int:
    m = re.search(rf"^{key}:\s+(\d+)", _read(Path("/proc/meminfo")), re.M)
    return int(m.group(1)) if m else 0


def hibernate_info() -> HibernateInfo:
    """Hazırda bekletme kullanılabilir mi; değilse nedenleri (Linwas kurulum yapmaz)."""
    reasons: list[str] = []
    if "disk" not in _read(Path("/sys/power/state")).split():
        reasons.append("kernel")
    lockdown = re.search(r"\[(\w+)\]", _read(Path("/sys/kernel/security/lockdown")))
    if lockdown and lockdown.group(1) != "none":
        reasons.append("lockdown")
    if _meminfo_kb("SwapTotal") < _meminfo_kb("MemTotal"):
        reasons.append("swap")
    cmdline = _read(Path("/proc/cmdline"))
    if "resume=" not in cmdline and _read(Path("/sys/power/resume")) in ("", "0:0"):
        reasons.append("resume")
    available = _can_hibernate()
    return HibernateInfo(available, [] if available else reasons)


def detect(laptop: bool) -> PowerSupport:
    a = power_apply
    unsupported: dict[str, str] = {}
    values: dict[str, tuple[str, ...]] = {}

    ppd = tuple(a.ppd_profiles())
    if ppd:
        values["ppd_profile"] = ppd
    else:
        unsupported["ppd_profile"] = NO_PPD

    if not power_agent.is_supported_desktop():
        unsupported.update(dict.fromkeys(USER_SETTINGS, NO_DESKTOP))
    elif not _has_ambient_sensor():
        unsupported["adaptive_brightness"] = NO_HARDWARE

    policies = a._policies()
    if not policies:
        for sid in ("cpu_epp", "cpu_governor", "cpu_min", "cpu_max"):
            unsupported[sid] = NO_HARDWARE
    else:
        epp = _policy_values("energy_performance_available_preferences")
        if epp:
            values["cpu_epp"] = epp
        else:
            unsupported["cpu_epp"] = NO_HARDWARE
        values["cpu_governor"] = _policy_values("scaling_available_governors")
    if not (
        (a.INTEL_PSTATE / "no_turbo").exists()
        or (a.CPUFREQ / "boost").exists()
        or any((p / "boost").exists() for p in policies)
    ):
        unsupported["cpu_boost"] = NO_HARDWARE

    if not a.USB_DEVICES.is_dir():
        unsupported["usb_autosuspend"] = NO_HARDWARE
    if not a.ASPM_POLICY.exists():
        unsupported["pcie_aspm"] = NO_HARDWARE
    if not a._sata_hosts():
        unsupported["sata_alpm"] = NO_HARDWARE
    if not a.rotational_disks():
        unsupported["disk_spindown"] = NO_HARDWARE
    elif not shutil.which("hdparm"):
        unsupported["disk_spindown"] = NO_HDPARM
    if not a.wireless_interfaces():
        unsupported["wifi_powersave"] = NO_HARDWARE
    elif not shutil.which("iw") and not Path("/usr/sbin/iw").exists():
        unsupported["wifi_powersave"] = NO_IW
    if not a._rfkill_soft("bluetooth"):
        unsupported["bluetooth"] = NO_HARDWARE
    if not any((r / "device" / "power" / "wakeup").exists() for r in a.RTC.glob("rtc*")):
        unsupported["wake_timers"] = NO_HARDWARE
    gpu_ok = False
    for card in a.gpu_cards():
        vendor = _read(card / "device" / "vendor")
        gpu_ok |= (
            (
                vendor == "0x1002"
                and (card / "device" / "power_dpm_force_performance_level").exists()
            )
            or (vendor == "0x8086" and (card / "gt_max_freq_mhz").exists())
            or (vendor == "0x10de" and (card / "device" / "power" / "control").exists())
        )
    if not gpu_ok:
        unsupported["gpu_power"] = NO_HARDWARE
    if a.backlight_device() is None:
        unsupported["brightness"] = NO_HARDWARE

    if not laptop:
        for spec in SETTINGS:
            if spec.laptop_only:
                unsupported[spec.id] = NOT_LAPTOP

    found = conflicts()
    if found:
        for sid in a.LOW_LEVEL_SETTINGS:
            unsupported.setdefault(sid, MANAGED)

    return PowerSupport(
        unsupported, values, found, hibernate_info(), laptop, ppd_owned=a.ppd_owned_now()
    )
