# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Tasarım değerleri: renkler, yazı tipi, boşluk, köşe yarıçapı.

QSS bu değerlerden üretilir; değişiklik yalnızca burada yapılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UiStyle(Enum):
    """Linwas'ın kendi düzeni (tema = açık/koyu; düzen = macOS / Windows görünümü)."""

    MACOS = "macos"
    WINDOWS = "windows"
    ECO = "eco"  # Linux Ekosistemi (eco) görünümü: teal vurgu, Figtree yazı tipi


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
    tile_bg: str = "#d1d1d6"  # kenar çubuğu simge kutusu (nötr; yalnızca seçili öğe renkli)
    tile_fg: str = "#3a3a3c"


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
    tile_bg="#3a3a3c",
    tile_fg="#e5e5ea",
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
    tile_bg="#000000",
    tile_fg="#ffffff",
)

# Windows düzeni (12 Ekim 2026 öncesi görünüm; Ayarlar › Görünüm › Düzen ile seçilir)
WINDOWS_LIGHT = ColorSet(
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
    sidebar_text_active="#0067c0",
    separator="#ebebeb",
    field_bg="#ffffff",
    soft_accent="#dce6f5",
    segment_bg="#e8eaed",
)

WINDOWS_DARK = ColorSet(
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
    sidebar_text_active="#60cdff",
    separator="#383838",
    field_bg="#2d2d2d",
    soft_accent="#1d3557",
    segment_bg="#2a2a2a",
)

# Eco düzeni (23 Ekim 2026). Değerlerin kaynağı docs/tasarim/tokens-eco.json; açık renkler eco
# "Hakkında" ayar sayfası görselinden ölçüldü, koyu renkler eco masaüstü mockup v5'ten.
# Hover/basılı tonları ve koyu temadaki saydam renklerin opak karşılıkları türetilmiştir.
ECO_LIGHT = ColorSet(
    accent="#2f6f73",
    accent_hover="#2a6468",
    accent_pressed="#26595c",
    background="#f7f7f4",
    surface="#ecefe9",
    surface_hover="#e5e8e2",
    border="#d7dad5",
    text_primary="#1e272a",
    text_secondary="#5c6e72",
    text_disabled="#7a8e92",
    text_on_accent="#ffffff",
    danger="#c42b1c",
    danger_bg="#fde7e9",
    warning="#9d5d00",
    success="#0f7b0f",
    sidebar_bg="#ecefe9",
    sidebar_item_hover="#e0e3dd",
    sidebar_item_active="#e8f2f2",
    status_bar_bg="#ecefe9",
    sidebar_text_active="#2f6f73",
    separator="#d7dad5",
    field_bg="#ecefe9",
    soft_accent="#dce9e9",
    segment_bg="#dee1db",
)

ECO_DARK = ColorSet(
    accent="#5cb7bc",
    accent_hover="#6cbec3",
    accent_pressed="#53a5a9",
    background="#0d1117",
    surface="#161b22",
    surface_hover="#1c2333",
    border="#292d34",
    text_primary="#e6edf3",
    text_secondary="#7d8590",
    text_disabled="#484f58",
    text_on_accent="#0d1117",
    danger="#ff99a4",
    danger_bg="#442726",
    warning="#d29922",
    success="#6ccb5f",
    sidebar_bg="#161b22",
    sidebar_item_hover="#1c2333",
    sidebar_item_active="#1d2b31",
    status_bar_bg="#161b22",
    sidebar_text_active="#5cb7bc",
    separator="#22262d",
    field_bg="#1c2333",
    soft_accent="#203239",
    segment_bg="#21262d",
    tile_bg="#21262d",
    tile_fg="#e6edf3",
)

THEMES: dict[Theme, ColorSet] = {
    Theme.LIGHT: LIGHT,
    Theme.DARK: DARK,
    Theme.HIGH_CONTRAST: HIGH_CONTRAST,
}

WINDOWS_THEMES: dict[Theme, ColorSet] = {
    Theme.LIGHT: WINDOWS_LIGHT,
    Theme.DARK: WINDOWS_DARK,
    Theme.HIGH_CONTRAST: HIGH_CONTRAST,
}

ECO_THEMES: dict[Theme, ColorSet] = {
    Theme.LIGHT: ECO_LIGHT,
    Theme.DARK: ECO_DARK,
    Theme.HIGH_CONTRAST: HIGH_CONTRAST,
}

_COLOR_TABLES: dict[UiStyle, dict[Theme, ColorSet]] = {
    UiStyle.MACOS: THEMES,
    UiStyle.WINDOWS: WINDOWS_THEMES,
    UiStyle.ECO: ECO_THEMES,
}


def colors(theme: Theme, style: UiStyle = UiStyle.MACOS, accent: str = "") -> ColorSet:
    table = _COLOR_TABLES[style]
    base = table.get(theme, table[Theme.LIGHT])
    if not accent or theme is Theme.HIGH_CONTRAST:
        return base
    return with_accent(base, accent, style)


# Ayarlar › Görünüm'deki hazır vurgu renkleri (kimlik → renk)
ACCENT_PRESETS: dict[str, str] = {
    "blue": "#0066d6",
    "purple": "#7d4cdb",
    "pink": "#c2185b",
    "red": "#c62828",
    "orange": "#c25400",
    "green": "#1e7b34",
    "teal": "#00796b",
    "graphite": "#5a5a5f",
}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _luminance(hex_color: str) -> float:
    def lin(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def mix(a: str, b: str, amount: float) -> str:
    """a'dan b'ye doğru `amount` (0–1) kadar karışım."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * amount for x, y in zip(ra, rb, strict=True)))


def readable_accent(accent: str, text: str = "#ffffff", ratio: float = 4.5) -> str:
    """Vurgu rengi üzerindeki yazı okunur olsun diye gerekirse rengi koyulaştırır."""
    color = accent
    # Açık yazıda renk koyulaşır, koyu yazıda açılır
    toward = "#000000" if _luminance(text) > 0.5 else "#ffffff"
    for _ in range(20):
        if contrast(color, text) >= ratio:
            return color
        color = mix(color, toward, 0.08)
    return color


def with_accent(base: ColorSet, accent: str, style: UiStyle = UiStyle.MACOS) -> ColorSet:
    """Renk setine kullanıcının vurgu rengini uygular (Linwas içi; sistem rengi değişmez)."""
    from dataclasses import replace

    a = readable_accent(accent, base.text_on_accent)
    soft = mix(base.surface, a, 0.16)
    active = a if style is UiStyle.MACOS else mix(base.surface, a, 0.2)
    return replace(
        base,
        accent=a,
        accent_hover=mix(a, "#000000", 0.1),
        accent_pressed=mix(a, "#000000", 0.2),
        sidebar_item_active=active,
        sidebar_text_active="#ffffff" if style is UiStyle.MACOS else a,
        soft_accent=soft,
    )


@dataclass(frozen=True)
class Metrics:
    """Düzene göre ölçüler (yazı, köşe, kenar çubuğu)."""

    font_px: int
    secondary_px: int
    caption_px: int
    h1_px: int
    h2_px: int
    radius: int  # düğme, giriş kutusu
    card_radius: int
    sidebar_width: int
    sidebar_icon: int
    sidebar_tiles: bool  # renkli simge kutuları (macOS)
    active_bar: bool  # seçili öğenin solunda vurgu çizgisi (Windows)
    segmented_tabs: bool  # sekmeler segmented control gibi (macOS)
    font_family: str = '"Noto Sans", sans-serif'
    semibold: int = 600  # "yarı kalın" yazı ağırlığı (eco: Figtree 500)


# Yazı küçük kalmasın (kullanıcı kararı, 12 Ekim 2026)
METRICS: dict[UiStyle, Metrics] = {
    UiStyle.MACOS: Metrics(
        font_px=16,
        secondary_px=14,
        caption_px=13,
        h1_px=32,
        h2_px=20,
        radius=8,
        card_radius=12,
        sidebar_width=280,
        sidebar_icon=26,
        sidebar_tiles=True,
        active_bar=False,
        segmented_tabs=True,
    ),
    UiStyle.WINDOWS: Metrics(
        font_px=15,
        secondary_px=13,
        caption_px=13,
        h1_px=28,
        h2_px=19,
        radius=6,
        card_radius=8,
        sidebar_width=270,
        sidebar_icon=20,
        sidebar_tiles=False,
        active_bar=True,
        segmented_tabs=False,
    ),
    UiStyle.ECO: Metrics(
        font_px=15,
        secondary_px=13,
        caption_px=13,
        h1_px=28,
        h2_px=19,
        radius=7,
        card_radius=10,
        sidebar_width=270,
        sidebar_icon=20,
        sidebar_tiles=False,
        active_bar=False,
        segmented_tabs=False,
        font_family='"Figtree", "Noto Sans", sans-serif',
        semibold=500,
    ),
}

# Yazı tipi tercihi — sistem Noto Sans yüklü değilse sistem yazı tipine düşer
FONT_FAMILY = "Noto Sans, sans-serif"
SIDEBAR_COLLAPSED_WIDTH = 48
CARD_PADDING = 16
