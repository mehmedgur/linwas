# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sistem sağlığı özeti (Genel bakış): disk, bellek, pil.

Yalnızca okuma; root gerekmez. Metinler arayüzde çevrilir, burada yalnızca sayılar ve durum var.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

OK = "ok"
WARN = "warn"
BAD = "bad"


@dataclass
class Usage:
    used: int  # bayt
    total: int  # bayt

    @property
    def percent(self) -> int:
        return round(self.used * 100 / self.total) if self.total else 0


def state_for(percent: int, warn: int, bad: int) -> str:
    """Doluluk yüzdesine göre durum (yüksek = kötü)."""
    if percent >= bad:
        return BAD
    if percent >= warn:
        return WARN
    return OK


def disk_usage(path: Path) -> Usage | None:
    try:
        du = shutil.disk_usage(path)
    except OSError:
        return None
    return Usage(used=du.total - du.free, total=du.total)


def home_is_separate(home: Path | None = None) -> bool:
    """/home ayrı bir bölümde mi (ayrıysa ikinci disk satırı gösterilir)."""
    home = home or Path.home()
    try:
        return os.stat(home).st_dev != os.stat("/").st_dev
    except OSError:
        return False


def parse_meminfo(text: str) -> Usage | None:
    """/proc/meminfo → kullanılan bellek (MemTotal - MemAvailable)."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key.strip()] = int(parts[0]) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    return Usage(used=total - available, total=total)


def memory_usage(path: Path = Path("/proc/meminfo")) -> Usage | None:
    try:
        return parse_meminfo(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def battery_state(health: int | None) -> str:
    """Pil sağlığı (tasarım kapasitesine göre yüzde; düşük = kötü)."""
    if health is None:
        return OK
    if health < 60:
        return BAD
    if health < 80:
        return WARN
    return OK
