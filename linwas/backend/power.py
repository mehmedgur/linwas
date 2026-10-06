"""Güç ve pil (dizüstü).

- Pil: /sys/class/power_supply/<ad>/ (Linux ABI: sysfs-class-power)
- Enerji modu: `powerprofilesctl` (power-profiles-daemon); kullanıcı yetkisiyle
- Kapak kapanınca: systemd-logind HandleLidSwitch= (logind.conf(5)); yazma root helper'da
- Pil koruma: charge_control_end_threshold (yalnızca destekleyen cihazlarda); yazma root helper'da
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

POWER_SUPPLY = Path("/sys/class/power_supply")

# logind ayar dosyaları; sonra okunan öncekini ezer (logind.conf(5))
LOGIND_MAIN = Path("/etc/systemd/logind.conf")
LOGIND_DROPIN_DIRS = (
    Path("/usr/lib/systemd/logind.conf.d"),
    Path("/run/systemd/logind.conf.d"),
    Path("/etc/systemd/logind.conf.d"),
)
# Linwas'ın yazdığı ayar dosyası (root helper ile aynı yol)
LINWAS_LOGIND_DROPIN = Path("/etc/systemd/logind.conf.d/90-linwas-lid.conf")

# Arayüzde sunulan kapak davranışları; logind varsayılanı "suspend"
LID_ACTIONS = ("suspend", "lock", "ignore", "poweroff")
LID_DEFAULT = "suspend"

# Pil koruma seçenekleri (yüzde); 100 = koruma kapalı
CHARGE_LIMITS = (60, 80, 100)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _read_int(path: Path) -> int | None:
    value = _read(path)
    return int(value) if value.lstrip("-").isdigit() else None


# --- Pil ---


@dataclass
class Battery:
    name: str  # ör. BAT0
    capacity: int | None  # yüzde
    status: str  # Charging / Discharging / Full / Not charging / Unknown
    health: int | None  # tam kapasite / tasarım kapasitesi, yüzde
    cycle_count: int | None
    charge_limit: int | None  # charge_control_end_threshold; desteklenmiyorsa None


def _battery_health(base: Path) -> int | None:
    for full, design in (
        ("energy_full", "energy_full_design"),
        ("charge_full", "charge_full_design"),
    ):
        f, d = _read_int(base / full), _read_int(base / design)
        if f and d:
            return min(round(f * 100 / d), 100)
    return None


def list_batteries(root: Path = POWER_SUPPLY) -> list[Battery]:
    """Sistem pillerini döner (fare/klavye gibi aygıt pilleri hariç)."""
    batteries: list[Battery] = []
    if not root.is_dir():
        return batteries
    for base in sorted(root.iterdir()):
        if _read(base / "type") != "Battery" or _read(base / "scope") == "Device":
            continue
        cycles = _read_int(base / "cycle_count")
        batteries.append(
            Battery(
                name=base.name,
                capacity=_read_int(base / "capacity"),
                status=_read(base / "status") or "Unknown",
                health=_battery_health(base),
                cycle_count=cycles or None,  # 0 = bilgi yok (ABI)
                charge_limit=_read_int(base / "charge_control_end_threshold"),
            )
        )
    return batteries


def is_laptop() -> bool:
    return bool(list_batteries())


# --- Enerji modu ---


def parse_profiles(output: str) -> tuple[list[str], str]:
    """`powerprofilesctl list` → (profiller, etkin profil). Etkin olan "*" ile başlar."""
    profiles: list[str] = []
    active = ""
    for line in output.splitlines():
        m = re.match(r"^(\*?)\s*([a-z][a-z-]*):\s*$", line)
        if m:
            profiles.append(m.group(2))
            if m.group(1):
                active = m.group(2)
    return profiles, active


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str] | None:
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def power_profiles() -> tuple[list[str], str]:
    r = _run(["powerprofilesctl", "list"])
    return parse_profiles(r.stdout) if r and r.returncode == 0 else ([], "")


def set_power_profile(profile: str) -> bool:
    """Enerji modunu değiştirir (root gerekmez; power-profiles-daemon polkit kuralı)."""
    if not re.fullmatch(r"[a-z][a-z-]*", profile):
        return False
    r = _run(["powerprofilesctl", "set", profile])
    return bool(r and r.returncode == 0)


# --- Kapak ---


def parse_lid_action(text: str) -> str | None:
    """Ayar dosyasındaki [Login] HandleLidSwitch= değeri; yoksa None."""
    section = ""
    value = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("["):
            section = line
            continue
        if section == "[Login]" and line.startswith("HandleLidSwitch="):
            value = line.split("=", 1)[1].strip()
    return value


def current_lid_action() -> str:
    """Etkin kapak davranışı: ana dosya, sonra ek dosyalar ada göre sırayla."""
    files = [LOGIND_MAIN]
    dropins: dict[str, Path] = {}
    for d in LOGIND_DROPIN_DIRS:
        if d.is_dir():
            for f in d.glob("*.conf"):
                dropins[f.name] = f  # aynı ad: sonraki dizin öncekini ezer
    files += [dropins[n] for n in sorted(dropins)]
    action = LID_DEFAULT
    for f in files:
        value = parse_lid_action(_read(f))
        if value:
            action = value
    return action
