"""Tasarım değerleri: renkler, yazı tipi, boşluk, köşe yarıçapı.

QSS bu değerlerden üretilir; değişiklik yalnızca burada yapılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"
    HIGH_CONTRAST = "high_contrast"
    SYSTEM = "system"


@dataclass(frozen=True)
class ColorSet:
    accent: str
    accent_hover: str
    accent_pressed: str
    background: str  # pencere/sayfa zemini
    surface: str  # kart, panel zemini
    surface_hover: str
    border: str
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_on_accent: str
    danger: str
    danger_bg: str
    warning: str
    success: str
    sidebar_bg: str
    sidebar_item_hover: str
    sidebar_item_active: str
    status_bar_bg: str


LIGHT = ColorSet(
    accent="#0067c0",
    accent_hover="#005ba6",
    accent_pressed="#004e8f",
    background="#f3f3f3",
    surface="#ffffff",
    surface_hover="#f5f5f5",
    border="#e0e3e7",
    text_primary="#1a1a1a",
    text_secondary="#6b6b6b",
    text_disabled="#a0a0a0",
    text_on_accent="#ffffff",
    danger="#c42b1c",
    danger_bg="#fde7e9",
    warning="#9d5d00",
    success="#0e7a0e",
    sidebar_bg="#f3f3f3",
    sidebar_item_hover="#e8eaed",
    sidebar_item_active="#dce6f5",
    status_bar_bg="#eaeaea",
)

DARK = ColorSet(
    accent="#60cdff",
    accent_hover="#4db8f0",
    accent_pressed="#3aa3db",
    background="#202020",
    surface="#2d2d2d",
    surface_hover="#383838",
    border="#404040",
    text_primary="#f5f5f5",
    text_secondary="#a0a0a0",
    text_disabled="#6b6b6b",
    text_on_accent="#000000",
    danger="#ff6b6b",
    danger_bg="#4a1515",
    warning="#ffd700",
    success="#4caf50",
    sidebar_bg="#1c1c1c",
    sidebar_item_hover="#2a2a2a",
    sidebar_item_active="#1d3557",
    status_bar_bg="#181818",
)

HIGH_CONTRAST = ColorSet(
    accent="#1aebff",
    accent_hover="#00ccee",
    accent_pressed="#00aacc",
    background="#000000",
    surface="#000000",
    surface_hover="#1a1a1a",
    border="#ffffff",
    text_primary="#ffffff",
    text_secondary="#ffffff",
    text_disabled="#888888",
    text_on_accent="#000000",
    danger="#ff4444",
    danger_bg="#330000",
    warning="#ffff00",
    success="#00ff00",
    sidebar_bg="#000000",
    sidebar_item_hover="#1a1a1a",
    sidebar_item_active="#003355",
    status_bar_bg="#000000",
)

THEMES: dict[Theme, ColorSet] = {
    Theme.LIGHT: LIGHT,
    Theme.DARK: DARK,
    Theme.HIGH_CONTRAST: HIGH_CONTRAST,
}

# Yazı tipi tercihi — sistem Noto Sans yüklü değilse sistem yazı tipine düşer
FONT_FAMILY = "Noto Sans, sans-serif"
FONT_SIZE_PX = 13
CORNER_RADIUS = 8
SIDEBAR_WIDTH = 220
SIDEBAR_COLLAPSED_WIDTH = 48
CARD_PADDING = 16
