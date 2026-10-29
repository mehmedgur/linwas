# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Disk temizliği: temizlenebilir alanları tarar ve siler.

Kullanıcı dizinleri doğrudan silinir; APT önbelleği ve journal için
root helper üzerinden işlem yapılır.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanupItem:
    id: str
    label: str
    description: str
    size_mb: float
    available: bool
    needs_root: bool  # True → whitelist üzerinden root helper çalışır
    paths: list[Path]  # temizlenecek yollar (needs_root=False için)


def _dir_size_mb(path: Path) -> float:
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(total / (1024 * 1024), 1)
    except (OSError, PermissionError):
        return 0.0


def _path_size_mb(path: Path) -> float:
    if path.is_file():
        try:
            return round(path.stat().st_size / (1024 * 1024), 1)
        except OSError:
            return 0.0
    return _dir_size_mb(path)


def _run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _apt_cache_size_mb() -> float:
    """APT arşiv önbelleği boyutu."""
    apt_archives = Path("/var/cache/apt/archives")
    if not apt_archives.is_dir():
        return 0.0
    try:
        total = sum(f.stat().st_size for f in apt_archives.iterdir() if f.suffix == ".deb")
        return round(total / (1024 * 1024), 1)
    except (OSError, PermissionError):
        return 0.0


def _journal_size_mb() -> float:
    """journald log boyutu."""
    out = _run(["journalctl", "--disk-usage"])
    for word in out.split():
        for unit, mult in [("G", 1024), ("M", 1), ("K", 1 / 1024)]:
            if word.endswith(unit) and word[:-1].replace(".", "").isdigit():
                try:
                    return round(float(word[:-1]) * mult, 1)
                except ValueError:
                    pass
    return 0.0


def scan_cleanup_items() -> list[CleanupItem]:
    """Temizlenebilir öğeleri listeler; her birinin boyutunu hesaplar."""
    items: list[CleanupItem] = []

    # Kullanıcı dosyaları — root gerekmez

    thumb = Path.home() / ".cache" / "thumbnails"
    items.append(
        CleanupItem(
            id="thumbnails",
            label="Thumbnail Cache",
            description="Cached image previews (rebuilt automatically when needed)",
            size_mb=_dir_size_mb(thumb),
            available=thumb.is_dir(),
            needs_root=False,
            paths=[thumb],
        )
    )

    trash = Path.home() / ".local" / "share" / "Trash"
    trash_size = _dir_size_mb(trash / "files") + _dir_size_mb(trash / "info")
    items.append(
        CleanupItem(
            id="trash",
            label="Trash",
            description="Files you deleted and moved to Trash",
            size_mb=trash_size,
            available=(trash / "files").is_dir(),
            needs_root=False,
            paths=[trash / "files", trash / "info"],
        )
    )

    # ~/.cache içindeki büyük klasörler (tarayıcı önbellekleri)
    cache_root = Path.home() / ".cache"
    browser_caches: list[Path] = []
    for browser_cache in ["google-chrome", "chromium", "mozilla", "BraveSoftware"]:
        bc = cache_root / browser_cache / "Default" / "Cache"
        if not bc.is_dir():
            bc = cache_root / browser_cache
        if bc.is_dir():
            browser_caches.append(bc)

    if browser_caches:
        total = sum(_dir_size_mb(p) for p in browser_caches)
        items.append(
            CleanupItem(
                id="browser_cache",
                label="Browser Cache",
                description="Temporary web data cached by browsers",
                size_mb=total,
                available=True,
                needs_root=False,
                paths=browser_caches,
            )
        )

    # APT önbelleği — root gerekir
    apt_mb = _apt_cache_size_mb()
    items.append(
        CleanupItem(
            id="apt_cache",
            label="Package Cache",
            description="Downloaded .deb packages no longer needed after installation",
            size_mb=apt_mb,
            available=apt_mb > 0,
            needs_root=True,
            paths=[Path("/var/cache/apt/archives")],
        )
    )

    # Journal — root gerekir
    journal_mb = _journal_size_mb()
    items.append(
        CleanupItem(
            id="journal",
            label="System Logs",
            description="Old system journal entries (keeps last 100 MB)",
            size_mb=max(0.0, journal_mb - 100),
            available=journal_mb > 110,
            needs_root=True,
            paths=[],
        )
    )

    return [i for i in items if i.available]


def clean_user_item(item: CleanupItem) -> tuple[bool, float]:
    """Root gerektirmeyen öğeyi temizler. (başarılı, kazanılan_mb) döner."""
    if item.needs_root:
        return False, 0.0
    freed = 0.0
    for path in item.paths:
        size = _path_size_mb(path)
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
            freed += size
        except OSError:
            pass
    return True, freed
