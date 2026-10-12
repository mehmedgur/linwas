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
    sidebar_item_active: str  # seçili menü öğesinin zemini (macOS: vurgu rengi)
    status_bar_bg: str
    sidebar_text_active: str = "#ffffff"  # seçili menü öğesinin yazısı
    separator: str = "#e8e8ed"  # kart içi satır ayırıcısı
    field_bg: str = "#dcdce1"  # kenar çubuğundaki arama kutusu
    soft_accent: str = "#e1ecfb"  # simge kutusu, etiket gibi açık vurgu zemini
    segment_bg: str = "#e3e3e8"  # sekme şeridi (segmented control) zemini


# macOS havası (12 Ekim 2026 kararı; kararlar.md › Arayüz tasarımı)
LIGHT = ColorSet(
    accent="#0066d6",
    accent_hover="#0059bb",
    accent_pressed="#004fa8",
    background="#f5f5f7",
    surface="#ffffff",
    surface_hover="#f2f2f5",
    border="#dcdce1",
    text_primary="#1d1d1f",
    text_secondary="#6e6e73",
    text_disabled="#a1a1a6",
    text_on_accent="#ffffff",
    danger="#c4161c",
    danger_bg="#fdecee",
    warning="#8a5300",
    success="#1e7b34",
    sidebar_bg="#ebebef",
    sidebar_item_hover="#dedee3",
    sidebar_item_active="#0066d6",
    status_bar_bg="#ebebef",
    sidebar_text_active="#ffffff",
    separator="#e8e8ed",
    field_bg="#dcdce1",
    soft_accent="#e1ecfb",
    segment_bg="#e3e3e8",
)

DARK = ColorSet(
    accent="#0a84ff",
    accent_hover="#3395ff",
    accent_pressed="#0070dd",
    background="#1e1e1e",
    surface="#2c2c2e",
    surface_hover="#3a3a3c",
    border="#3d3d40",
    text_primary="#f5f5f7",
    text_secondary="#a1a1a6",
    text_disabled="#636366",
    text_on_accent="#ffffff",
    danger="#ff6961",
    danger_bg="#4a1c1c",
    warning="#ffd60a",
    success="#30d158",
    sidebar_bg="#252527",
    sidebar_item_hover="#333336",
    sidebar_item_active="#0a6ad6",
    status_bar_bg="#252527",
    sidebar_text_active="#ffffff",
    separator="#3a3a3c",
    field_bg="#38383b",
    soft_accent="#1c3456",
    segment_bg="#38383b",
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
    sidebar_item_active="#1aebff",
    status_bar_bg="#000000",
    sidebar_text_active="#000000",
    separator="#ffffff",
    field_bg="#000000",
    soft_accent="#003355",
    segment_bg="#000000",
)

THEMES: dict[Theme, ColorSet] = {
    Theme.LIGHT: LIGHT,
    Theme.DARK: DARK,
    Theme.HIGH_CONTRAST: HIGH_CONTRAST,
}

# Yazı tipi tercihi — sistem Noto Sans yüklü değilse sistem yazı tipine düşer
FONT_FAMILY = "Noto Sans, sans-serif"
# Yazı küçük kalmasın (kullanıcı kararı, 12 Ekim 2026): gövde 16 px, başlık 32 px
FONT_SIZE_PX = 16
FONT_SIZE_SECONDARY_PX = 14
FONT_SIZE_CAPTION_PX = 13
FONT_SIZE_H1_PX = 32
FONT_SIZE_H2_PX = 20
CORNER_RADIUS = 8  # düğme, giriş kutusu
CARD_RADIUS = 12
SIDEBAR_WIDTH = 280
SIDEBAR_ICON_SIZE = 26  # renkli simge kutusu
SIDEBAR_COLLAPSED_WIDTH = 48
CARD_PADDING = 16
