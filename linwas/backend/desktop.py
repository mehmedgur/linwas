"""Masaüstü ortamı ve oturum türü algılama.

`XDG_CURRENT_DESKTOP` ve `XDG_SESSION_TYPE` ortam değişkenlerine bakar. Qt'ye bağımlı değildir.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum


class Desktop(Enum):
    """Linwas'ın tanıdığı masaüstü ortamları."""

    GNOME = "gnome"
    CINNAMON = "cinnamon"
    XFCE = "xfce"
    KDE = "kde"
    OTHER = "other"
    UNKNOWN = "unknown"

    @property
    def supported(self) -> bool:
        """2.0'da tam desteklenen masaüstleri: GNOME, Cinnamon, XFCE."""
        return self in (Desktop.GNOME, Desktop.CINNAMON, Desktop.XFCE)


# XDG_CURRENT_DESKTOP içinde görülebilen adlar (büyük/küçük harf duyarsız).
# Ör. Ubuntu: "ubuntu:GNOME", Mint: "X-Cinnamon", XFCE: "XFCE".
_DESKTOP_TOKENS: tuple[tuple[str, Desktop], ...] = (
    ("cinnamon", Desktop.CINNAMON),
    ("gnome", Desktop.GNOME),
    ("xfce", Desktop.XFCE),
    ("kde", Desktop.KDE),
)


def detect_desktop(env: Mapping[str, str]) -> Desktop:
    """Ortam değişkenlerinden masaüstünü algılar."""
    raw = env.get("XDG_CURRENT_DESKTOP", "") or env.get("DESKTOP_SESSION", "")
    if not raw:
        return Desktop.UNKNOWN
    tokens = [t.strip().lower() for t in raw.replace(";", ":").split(":") if t.strip()]
    # Cinnamon bazen GNOME ile birlikte bildirilir; önce daha özel olanı ara.
    for name, desktop in _DESKTOP_TOKENS:
        if any(name in token for token in tokens):
            return desktop
    return Desktop.OTHER


def detect_session_type(env: Mapping[str, str]) -> str:
    """'wayland', 'x11' ya da boş metin döndürür."""
    value = env.get("XDG_SESSION_TYPE", "").strip().lower()
    if value in ("wayland", "x11"):
        return value
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return ""
