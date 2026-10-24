"""Güç ve pil (dizüstü).

- Pil: /sys/class/power_supply/<ad>/ (Linux ABI: sysfs-class-power)
- Enerji modu: `powerprofilesctl` (power-profiles-daemon); kullanıcı yetkisiyle
- Kapak kapanınca: systemd-logind HandleLidSwitch= (logind.conf(5)); yazma root helper'da
"""

from __future__ import annotations

import os
import re
import shutil
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
    minutes_left: int | None = None  # boşalmaya/dolmaya kalan dakika; çekirdek vermiyorsa None


def _minutes_left(base: Path, status: str) -> int | None:
    """Kalan süre: enerji/akım değerlerinden (µWh/µW ya da µAh/µA). Ölçülemiyorsa None."""
    for now_f, full_f, rate_f in (
        ("energy_now", "energy_full", "power_now"),
        ("charge_now", "charge_full", "current_now"),
    ):
        now, full, rate = (_read_int(base / f) for f in (now_f, full_f, rate_f))
        if now is None or not rate or rate <= 0:
            continue
        if status == "Discharging":
            left = now / rate
        elif status == "Charging" and full:
            left = max(full - now, 0) / rate
        else:
            return None
        minutes = round(left * 60)
        # Anlık ölçüm saçma bir değer verdiyse (ör. 2 gün) gösterme
        return minutes if 0 < minutes < 24 * 60 else None
    return None


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
                minutes_left=_minutes_left(base, _read(base / "status")),
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
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
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


# --- Güç planı değiştirme (şifresiz; polkit eylemi org.linwas.power.switch) ---

SWITCH_HELPER = Path("/usr/lib/linwas/linwas-power-switch")


def can_switch_plan_directly() -> bool:
    """Kurulu pakette plan şifresiz değişir; kaynak koddan çalışırken root helper gerekir."""
    return SWITCH_HELPER.is_file() and shutil.which("pkexec") is not None


def switch_plan(plan_id: str) -> bool:
    if not re.fullmatch(r"[a-z0-9-]{1,32}", plan_id):
        return False
    r = _run(["pkexec", str(SWITCH_HELPER), plan_id], timeout=60)
    return bool(r and r.returncode == 0)
