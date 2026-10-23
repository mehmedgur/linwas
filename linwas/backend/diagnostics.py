"""Gelişmiş › Tanılama: Linwas'ın çalışması için gerekenlerin denetimi (salt okunur)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

POLKIT_POLICY = Path("/usr/share/polkit-1/actions/org.linwas.helper.policy")
HELPER = Path("/usr/lib/linwas/linwas-helper")
TIMER = "linwas-autoupdate.timer"


@dataclass
class Check:
    key: str  # arayüzde çevrilen ad için kimlik
    ok: bool
    detail: str = ""
    optional: bool = False  # olmaması hata değil, yalnızca bazı özellikleri kapatır


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return r.returncode, (r.stdout + r.stderr).strip()


def _tool(key: str, name: str, optional: bool = True) -> Check:
    path = shutil.which(name)
    return Check(key, path is not None, path or "", optional)


def timer_status() -> str:
    """`systemctl list-timers` satırı (sonraki çalışma zamanı) ya da boş."""
    _, out = _run(["systemctl", "list-timers", TIMER, "--all", "--no-pager"])
    lines = [x for x in out.splitlines() if TIMER in x]
    return lines[0].strip() if lines else ""


def _network() -> Check:
    try:
        with socket.create_connection(("deb.debian.org", 443), timeout=5):
            return Check("network", True, "deb.debian.org:443")
    except OSError as exc:
        return Check("network", False, str(exc))


def run_checks() -> list[Check]:
    from linwas.ai.keystore import keyring_available

    code, enabled = _run(["systemctl", "is-enabled", TIMER])
    free = shutil.disk_usage("/").free
    return [
        _tool("pkexec", "pkexec", optional=False),
        Check("polkit", POLKIT_POLICY.is_file(), str(POLKIT_POLICY)),
        Check("helper", HELPER.is_file(), str(HELPER)),
        Check("timer", code == 0 and enabled == "enabled", enabled or TIMER),
        _tool("notifications", "gdbus"),
        Check("keyring", keyring_available(), "", optional=True),
        Check("disk", free > 2 * 1024**3, f"{free // 1024**2} MB"),
        _network(),
        _tool("flatpak", "flatpak"),
        _tool("fwupd", "fwupdmgr"),
        _tool("timeshift", "timeshift"),
    ]
