"""Otomatik güncelleme (Güncelleme merkezi, kararlar.md).

Linwas'ın systemd zamanlayıcısı (linwas-autoupdate.timer) günde bir kez bu modülü root olarak
çalıştırır: `python -I -m linwas.core.autoupdate`. Dışarıdan parametre almaz; yalnızca root'a ait
ayar dosyasını okur. Ayarı arayüz, root helper'ın `autoupdate.configure` işlemiyle yazar.

Kurulan: dağıtım deposundaki güncellemeler (`apt-get upgrade`; yeni paket kurmaz, kaldırmaz —
yeni çekirdek serisi ve sürücü değişikliği bu yüzden kurulmaz). Firmware'e dokunulmaz.
Beklenir: pilde (ya da pil %30'un altındayken), ölçülü bağlantıda, duraklatılmışken.

Arayüz ayarı, durumu ve geçmişi buradaki okuma işlevleriyle (root gerektirmeden) okur.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_PATH = Path("/etc/linwas/autoupdate.json")
STATE_DIR = Path("/var/lib/linwas-autoupdate")
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = Path("/run/linwas-autoupdate.lock")
TIMER_UNITS = (
    Path("/usr/lib/systemd/system/linwas-autoupdate.timer"),
    Path("/lib/systemd/system/linwas-autoupdate.timer"),
)
POWER_DIR = Path("/sys/class/power_supply")
MAX_PAUSE_WEEKS = 5
MIN_BATTERY = 30
SNAPSHOT_COMMENT = "Linwas otomatik güncelleme"
SNAPSHOTS_TO_KEEP = 3

_APT_ENV = {"DEBIAN_FRONTEND": "noninteractive", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
# Linwas::Auto=1 apt geçmişinde kaydı "otomatik" diye işaretler (backend/update_history.py)
_APT_OPTS = [
    "-o",
    "Linwas::Auto=1",
    "-o",
    "DPkg::Lock::Timeout=600",
    "-o",
    "Dpkg::Options::=--force-confdef",
    "-o",
    "Dpkg::Options::=--force-confold",
]


# --- Ayar ---


@dataclass
class AutoUpdateConfig:
    enabled: bool = True
    paused_until: str = ""  # ISO 8601 (UTC); boşsa duraklatılmamış
    snapshot: bool = True


def load_config(path: Path = CONFIG_PATH) -> AutoUpdateConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AutoUpdateConfig()
    if not isinstance(data, dict):
        return AutoUpdateConfig()
    return AutoUpdateConfig(
        enabled=data.get("enabled", True) is not False,
        paused_until=data.get("paused_until") if isinstance(data.get("paused_until"), str) else "",
        snapshot=data.get("snapshot", True) is not False,
    )


def config_with(
    current: AutoUpdateConfig,
    enabled: bool,
    snapshot: bool,
    pause_weeks: int,
    now: datetime | None = None,
) -> AutoUpdateConfig:
    """Yeni ayar: pause_weeks -1 = duraklatmayı olduğu gibi bırak, 0 = devam et, 1–5 = hafta."""
    if pause_weeks < 0:
        paused = current.paused_until
    elif pause_weeks == 0:
        paused = ""
    else:
        now = now or datetime.now(timezone.utc)
        weeks = min(pause_weeks, MAX_PAUSE_WEEKS)
        paused = (now + timedelta(weeks=weeks)).isoformat(timespec="seconds")
    return AutoUpdateConfig(enabled=enabled, paused_until=paused, snapshot=snapshot)


def write_config(cfg: AutoUpdateConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o755)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(path)


def paused_until(cfg: AutoUpdateConfig, now: datetime | None = None) -> datetime | None:
    """Duraklatma süresi dolmadıysa bitiş anı; değilse None."""
    if not cfg.paused_until:
        return None
    try:
        until = datetime.fromisoformat(cfg.paused_until)
    except ValueError:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until if until > (now or datetime.now(timezone.utc)) else None


def timer_installed() -> bool:
    return any(p.is_file() for p in TIMER_UNITS)


# --- Koşullar ---


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def on_battery(power_dir: Path = POWER_DIR) -> bool:
    """Prize takılı değilse ya da pil şarj olmuyorken %30'un altındaysa True."""
    if not power_dir.is_dir():
        return False
    # USB-C ile şarj eden dizüstülerde güç kaynağı "USB" türünde görünür
    mains = [d for d in power_dir.iterdir() if _read(d / "type") in ("Mains", "USB")]
    batteries = [d for d in power_dir.iterdir() if _read(d / "type") == "Battery"]
    if mains and not any(_read(d / "online") == "1" for d in mains):
        return True
    for bat in batteries:
        level = _read(bat / "capacity")
        charging = _read(bat / "status") in ("Charging", "Full")
        if level.isdigit() and int(level) < MIN_BATTERY and not charging:
            return True
    return False


def parse_metered(out: str) -> bool:
    """`busctl get-property … Metered` çıktısı ("u 4"): 1 = evet, 3 = tahminen evet."""
    parts = out.split()
    return len(parts) == 2 and parts[0] == "u" and parts[1] in ("1", "3")


def is_metered() -> bool:
    """NetworkManager'a göre bağlantı ölçülü mü (NM yoksa False)."""
    try:
        r = subprocess.run(
            [
                "busctl",
                "get-property",
                "org.freedesktop.NetworkManager",
                "/org/freedesktop/NetworkManager",
                "org.freedesktop.NetworkManager",
                "Metered",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and parse_metered(r.stdout)


def _version_key(text: str) -> list:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def reboot_required(
    running: str | None = None,
    modules_dir: Path = Path("/lib/modules"),
    flag: Path = Path("/run/reboot-required"),
) -> bool:
    """Ubuntu'nun bayrak dosyası ya da çalışan çekirdekten yeni kurulu çekirdek varsa True."""
    if flag.exists():
        return True
    running = running or os.uname().release
    try:
        kernels = [d.name for d in modules_dir.iterdir() if d.is_dir()]
    except OSError:
        return False
    if not kernels or running not in kernels:
        return False
    flavour = running.rsplit("-", 1)[-1] if "-" in running else ""
    same = [k for k in kernels if not flavour or k.endswith("-" + flavour)]
    newest = max(same, key=_version_key)
    return newest != running and Path("/boot", f"vmlinuz-{newest}").exists()


def scheduled_reboot(path: Path = Path("/run/systemd/shutdown/scheduled")) -> datetime | None:
    """`shutdown -r SS:DD` ile planlanmış yeniden başlatma anı (systemd; yoksa None)."""
    fields = dict(line.split("=", 1) for line in _read(path).splitlines() if "=" in line)
    if fields.get("MODE") != "reboot" or not fields.get("USEC", "").isdigit():
        return None
    return datetime.fromtimestamp(int(fields["USEC"]) / 1_000_000, tz=timezone.utc)


# --- Durum ---


@dataclass
class AutoUpdateState:
    last_run: str = ""  # ISO 8601
    result: str = ""  # "updated" | "up_to_date" | "failed" | "skipped"
    reason: str = ""  # atlandıysa: "disabled" | "paused" | "battery" | "metered"
    packages: list[list[str]] = field(default_factory=list)  # [ad, eski, yeni]
    error: str = ""
    snapshot: str = ""


def load_state(path: Path = STATE_FILE) -> AutoUpdateState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AutoUpdateState()
    if not isinstance(data, dict):
        return AutoUpdateState()
    known = AutoUpdateState.__dataclass_fields__
    return AutoUpdateState(**{k: v for k, v in data.items() if k in known})


def _save_state(state: AutoUpdateState) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o755)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(STATE_FILE)


# --- Çalıştırma (root) ---


def _run(cmd: list[str], timeout: int = 3600) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env={**os.environ, **_APT_ENV},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def parse_timeshift_list(out: str) -> list[tuple[str, str]]:
    """`timeshift --list` → [(anlık görüntü adı, açıklama)] (eskiden yeniye)."""
    result = []
    for line in out.splitlines():
        m = re.match(r"^\s*\d+\s+>\s+(\S+)\s+(?:[A-Z]+\s+)?(.*)$", line)
        if m:
            result.append((m.group(1), m.group(2).strip()))
    return result


def _snapshot() -> str:
    ok, _ = _run(["timeshift", "--create", "--comments", SNAPSHOT_COMMENT], timeout=7200)
    if not ok:
        return ""
    _, out = _run(["timeshift", "--list"], timeout=120)
    ours = [name for name, desc in parse_timeshift_list(out) if desc == SNAPSHOT_COMMENT]
    for old in ours[:-SNAPSHOTS_TO_KEEP]:
        _run(["timeshift", "--delete", "--snapshot", old], timeout=1800)
    return ours[-1] if ours else ""


def run_once(now: datetime | None = None) -> AutoUpdateState:
    from linwas.backend.packages import list_upgradable

    now = now or datetime.now(timezone.utc)
    state = AutoUpdateState(last_run=now.isoformat(timespec="seconds"))
    cfg = load_config()
    skip = ""
    if not cfg.enabled:
        skip = "disabled"
    elif paused_until(cfg, now):
        skip = "paused"
    elif on_battery():
        skip = "battery"
    elif is_metered():
        skip = "metered"
    if skip:
        state.result, state.reason = "skipped", skip
        return state

    ok, out = _run(["apt-get", "-q", *_APT_OPTS, "update"])
    if not ok:
        state.result, state.error = "failed", out
        return state
    pending = list_upgradable()
    if not pending:
        state.result = "up_to_date"
        return state
    if cfg.snapshot and shutil.which("timeshift"):
        state.snapshot = _snapshot()
    ok, out = _run(["apt-get", "-q", "-y", *_APT_OPTS, "upgrade"])
    state.packages = [[p.name, p.installed_version, p.available_version] for p in pending]
    state.result = "updated" if ok else "failed"
    if not ok:
        state.error = out
    return state


def main() -> int:
    if os.geteuid() != 0:
        print("linwas-autoupdate: root olarak çalışmalı", file=sys.stderr)
        return 2
    with open(LOCK_FILE, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0  # başka bir çalıştırma sürüyor
        state = run_once()
        _save_state(state)
    print(f"linwas-autoupdate: {state.result} {state.reason}".strip())
    return 1 if state.result == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
