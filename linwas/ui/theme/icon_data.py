"""Linwas çizgi simgeleri (24×24, SVG). Qt'ye bağımlı değil.

Simgeler masaüstünün simge temasına bağlı değildir (gömülü Qt'de tema bulunamayabilir);
renk temadan gelir, böylece açık/koyu/yüksek kontrastta okunur kalır.
`{c}` yer tutucusu dolgu gereken yerlerde renkle değiştirilir.
"""

from __future__ import annotations

import os
from pathlib import Path

# Simge adı → SVG içeriği (dış <svg> etiketi olmadan). Adlar çoğunlukla sayfa kimlikleridir.
PATHS: dict[str, str] = {
    "ai_chat": (
        '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>'
        '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>'
    ),
    "system": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "overview": (
        '<rect x="3" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1.5"/>'
    ),
    "updates": (
        '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/>'
        '<path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>'
    ),
    "drivers": (
        '<rect x="6" y="6" width="12" height="12" rx="2"/>'
        '<rect x="9.5" y="9.5" width="5" height="5" rx="1"/>'
        '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>'
    ),
    "network": (
        '<path d="M2 8.5a15 15 0 0 1 20 0"/><path d="M5 12a10 10 0 0 1 14 0"/>'
        '<path d="M8.5 15.5a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1" fill="{c}"/>'
    ),
    "backups": ('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>'),
    "hardware": (
        '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/>'
        '<path d="M6 14h12v7H6z"/>'
    ),
    "taskmgr": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "cleanup": (
        '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>'
        '<path d="M10 11v6M14 11v6"/>'
    ),
    "personal_backup": (
        '<rect x="3" y="13" width="18" height="8" rx="2"/>'
        '<circle cx="7" cy="17" r=".8" fill="{c}"/>'
        '<path d="M12 3v7"/><path d="M8.5 6.5L12 3l3.5 3.5"/>'
    ),
    "power": (
        '<rect x="2" y="7" width="17" height="10" rx="2"/><path d="M22 11v2"/>'
        '<path d="M6 10v4M10 10v4"/>'
    ),
    "migrate": (
        '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/>'
        '<path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>'
    ),
    "all_settings": (
        '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>'
        '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/>'
        '<circle cx="18" cy="18" r="2"/>'
    ),
    "interface": (
        '<path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.6-.9 1.2-1.8-.5-1-.1-2.2 1.1-2.2H17'
        'a4 4 0 0 0 4-4c0-5.5-4-10-9-10z"/>'
        '<circle cx="7.5" cy="11" r="1" fill="{c}"/><circle cx="10" cy="7" r="1" fill="{c}"/>'
        '<circle cx="15" cy="7.5" r="1" fill="{c}"/>'
    ),
    "appearance": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>'
        '<path d="M14 6.5h1M17 6.5h1"/>'
    ),
    "theme": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="{c}"/>',
    "fonts": '<path d="M4 7V5h16v2"/><path d="M12 5v14"/><path d="M9 19h6"/>',
    "display": (
        '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>'
        '<path d="M9 8l-2 2.5L9 13M15 8l2 2.5-2 2.5"/>'
    ),
    "software": '<path d="M5 8h14l-1 12H6z"/><path d="M9 8a3 3 0 0 1 6 0"/>',
    "troubleshoot": (
        '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>'
        '<path d="M5.6 5.6l3.6 3.6M14.8 14.8l3.6 3.6M18.4 5.6l-3.6 3.6M9.2 14.8l-3.6 3.6"/>'
    ),
    "guide": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6"/>'
        '<circle cx="12" cy="17" r=".9" fill="{c}"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="6.5"/>'
        '<path stroke-width="3" d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4'
        'M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>'
    ),
    "accessibility": (
        '<circle cx="12" cy="4.5" r="1.8"/><path d="M4 8.5l8 1.5 8-1.5"/>'
        '<path d="M12 10v5l-3.5 6.5M12 15l3.5 6.5"/>'
    ),
    "privacy": (
        '<path d="M12 3l8 3v6c0 4.5-3.4 8.2-8 9-4.6-.8-8-4.5-8-9V6z"/>'
        '<rect x="9" y="11" width="6" height="5" rx="1"/><path d="M10 11V9.5a2 2 0 0 1 4 0V11"/>'
    ),
    # Tüm Ayarlar bağlantı simgeleri
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "globe": (
        '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/>'
        '<path d="M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9'
        'c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>'
    ),
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "default_apps": (
        '<rect x="3" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1.5"/>'
        '<path d="M17.5 13.5l1.1 2.3 2.4.3-1.8 1.7.5 2.4-2.2-1.2-2.2 1.2.5-2.4-1.8-1.7 2.4-.3z"/>'
    ),
    "sound": (
        '<path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 9a4 4 0 0 1 0 6"/>'
        '<path d="M19 6.5a7.5 7.5 0 0 1 0 11"/>'
    ),
    "mouse": '<rect x="6" y="3" width="12" height="18" rx="6"/><path d="M12 7v4"/>',
    "keyboard": (
        '<rect x="2" y="6" width="20" height="12" rx="2"/>'
        '<path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>'
    ),
    "bluetooth": '<path d="M7 7l10 10-5 4V3l5 4L7 17"/>',
    "ethernet": (
        '<rect x="4" y="8" width="16" height="12" rx="2"/><path d="M8 8V5h8v3"/>'
        '<path d="M8 13v3M12 13v3M16 13v3"/>'
    ),
    "wallpaper": (
        '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9.5" r="1.8"/>'
        '<path d="M3 17l5-5 4 4 3-3 6 6"/>'
    ),
    "camera": (
        '<path d="M3 8a2 2 0 0 1 2-2h2.5l1.5-2h6l1.5 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5'
        'a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.5"/>'
    ),
    "bell": ('<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>'),
    "app_folders": (
        '<rect x="4" y="4" width="7" height="7" rx="2"/>'
        '<rect x="13" y="4" width="7" height="7" rx="2"/>'
        '<rect x="4" y="13" width="7" height="7" rx="2"/>'
        '<rect x="13" y="13" width="7" height="7" rx="2"/>'
    ),
    "plugin": '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M9 12h6M12 9v6"/>',
    "chevron_right": '<path d="M9 6l6 6-6 6"/>',
    "chevron_down": '<path d="M6 9l6 6 6-6"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" stroke-width="3"/>',
    "info": (
        '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/>'
        '<circle cx="12" cy="7.5" r="0.6" fill="{c}"/>'
    ),
}


def svg(name: str, color: str, stroke_width: float = 1.8) -> str:
    """Tam SVG belgesi; bilinmeyen ad → "plugin" simgesi."""
    body = PATHS.get(name, PATHS["plugin"]).replace("{c}", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def _cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "linwas" / "icons"


def asset_path(name: str, color: str) -> str:
    """QSS `image: url(...)` için simge dosyası (önbellekte; yoksa yazılır).

    Yazılamazsa boş dize döner; stil sayfası o zaman simgesiz görünür.
    """
    target = _cache_dir() / f"{name}-{color.lstrip('#')}.svg"
    try:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(svg(name, color), encoding="utf-8")
    except OSError:
        return ""
    return target.as_posix()
