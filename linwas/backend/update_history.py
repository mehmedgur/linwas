# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Güncelleme geçmişi: APT'nin kendi kaydından okunur (salt okunur, root gerekmez).

/var/log/apt/history.log (ve döndürülmüş .gz kopyaları) herkesçe okunabilir. Biçim:

    Start-Date: 2026-10-07  11:38:02
    Commandline: apt-get upgrade -y ...
    Upgrade: foo:amd64 (1.0, 1.1), bar:amd64 (2.0, 2.1)
    Error: ...
    End-Date: 2026-10-07  11:38:40

Linwas'ın otomatik güncellemesi apt'ye `-o Linwas::Auto=1` verir; komut satırında görünür ve
kayıt "otomatik" diye işaretlenir.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path

APT_LOG_DIR = Path("/var/log/apt")
AUTO_MARKER = "Linwas::Auto=1"

# "ad:mimari (sürüm[, sürüm])" öğeleri
_ITEM = re.compile(r"([^\s,()]+) \(([^)]*)\)")


@dataclass
class PackageChange:
    name: str
    old: str = ""
    new: str = ""


@dataclass
class HistoryRecord:
    start: str  # "YYYY-MM-DD HH:MM:SS"
    commandline: str = ""
    upgraded: list[PackageChange] = field(default_factory=list)
    installed: list[PackageChange] = field(default_factory=list)
    removed: list[PackageChange] = field(default_factory=list)
    error: str = ""

    @property
    def automatic(self) -> bool:
        return AUTO_MARKER in self.commandline

    @property
    def kind(self) -> str:
        """Ağırlıklı işlem: "upgrade" | "install" | "remove"."""
        if self.upgraded:
            return "upgrade"
        if self.installed:
            return "install"
        return "remove"


def _items(text: str, kind: str) -> list[PackageChange]:
    result = []
    for name, inner in _ITEM.findall(text):
        name = name.split(":", 1)[0]  # mimari soneki atılır
        parts = [p.strip() for p in inner.split(",")]
        if kind == "upgrade":
            result.append(PackageChange(name, parts[0], parts[1] if len(parts) > 1 else ""))
        elif kind == "install":
            result.append(PackageChange(name, "", parts[0]))
        else:
            result.append(PackageChange(name, parts[0], ""))
    return result


def parse_history(text: str) -> list[HistoryRecord]:
    records: list[HistoryRecord] = []
    current: HistoryRecord | None = None
    for line in text.splitlines():
        key, sep, value = line.partition(": ")
        if not sep:
            continue
        value = value.strip()
        if key == "Start-Date":
            current = HistoryRecord(start=" ".join(value.split()))
            records.append(current)
        elif current is None:
            continue
        elif key == "Commandline":
            current.commandline = value
        elif key == "Upgrade":
            current.upgraded += _items(value, "upgrade")
        elif key in ("Install", "Reinstall", "Downgrade"):
            current.installed += _items(value, "install")
        elif key in ("Remove", "Purge"):
            current.removed += _items(value, "remove")
        elif key == "Error":
            current.error = value
    return [r for r in records if r.upgraded or r.installed or r.removed or r.error]


def _read(path: Path) -> str:
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_history(log_dir: Path = APT_LOG_DIR, limit: int = 200) -> list[HistoryRecord]:
    """En yeniden eskiye geçmiş kayıtları."""
    files = [log_dir / "history.log"]
    rotated = [p for p in log_dir.glob("history.log.*.gz") if p.name.split(".")[2].isdigit()]
    files += sorted(rotated, key=lambda p: int(p.name.split(".")[2]))
    records: list[HistoryRecord] = []
    for path in files:  # history.log en yeni, .1.gz ondan eski…
        if not path.is_file():
            continue
        records += reversed(parse_history(_read(path)))
        if len(records) >= limit:
            break
    return records[:limit]
