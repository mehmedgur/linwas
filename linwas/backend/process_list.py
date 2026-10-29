# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Süreç listesi: ps çıktısını okur, öldürme işlemi yapar.

Root gerekmez — yalnızca kullanıcıya ait süreçler öldürülebilir.
Sistem süreçleri koruma altındadır.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass


@dataclass
class ProcessInfo:
    pid: int
    user: str
    cpu_pct: float
    rss_mb: float
    name: str
    can_kill: bool  # False → sistem/masaüstü süreci, öldürülemez


# Öldürülemez süreç adları (masaüstü ortamı kritik bileşenleri)
_PROTECTED = {
    "systemd",
    "init",
    "kthreadd",
    "gnome-shell",
    "plasmashell",
    "cinnamon",
    "xfce4-session",
    "lxqt-session",
    "xorg",
    "wayland",
    "gdm",
    "sddm",
    "lightdm",
    "pulseaudio",
    "pipewire",
    "dbus-daemon",
    "NetworkManager",
    "systemd-logind",
    "polkitd",
    "linwas",
}


def _run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def list_processes(current_user_only: bool = True) -> list[ProcessInfo]:
    """Çalışan süreçleri döner; CPU kullanımına göre azalan sırada."""
    out = _run(["ps", "-e", "-o", "pid=,user=,pcpu=,rss=,comm=", "--sort=-pcpu"])
    processes: list[ProcessInfo] = []
    my_user = os.environ.get("USER", "")

    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        try:
            pid = int(parts[0])
            user = parts[1]
            cpu = float(parts[2])
            rss_kb = int(parts[3])
            name = parts[4].strip()
        except (ValueError, IndexError):
            continue

        if current_user_only and user != my_user:
            continue

        can_kill = (
            user == my_user and name.lower() not in {p.lower() for p in _PROTECTED} and pid > 1
        )
        processes.append(
            ProcessInfo(
                pid=pid,
                user=user,
                cpu_pct=cpu,
                rss_mb=round(rss_kb / 1024, 1),
                name=name,
                can_kill=can_kill,
            )
        )
    return processes


def kill_process(pid: int, force: bool = True) -> tuple[bool, str]:
    """Süreci öldürür. (başarılı, hata_mesajı) döner."""
    try:
        sig = signal.SIGKILL if force else signal.SIGTERM
        os.kill(pid, sig)
        return True, ""
    except ProcessLookupError:
        return False, "Process already exited"
    except PermissionError:
        return False, "Permission denied"
    except OSError as exc:
        return False, str(exc)
