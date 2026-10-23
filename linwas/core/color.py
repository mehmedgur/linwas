"""Renk yardımcıları (Qt'siz): ayrıştırma, QSS biçimi, kontrast oranı."""

from __future__ import annotations

import re

Rgba = tuple[int, int, int, float]  # r, g, b: 0-255, alfa: 0-1

_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")
_RGBA = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([0-9.]+)\s*)?\)$"
)


def parse_color(value: str) -> Rgba:
    """'#RRGGBB' ya da 'rgba(r,g,b,a)' (a: 0-1) metnini (r, g, b, a) yapar."""
    text = value.strip()
    match = _HEX.match(text)
    if match:
        raw = match.group(1)
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16), 1.0
    match = _RGBA.match(text)
    if match:
        r, g, b = (int(match.group(i)) for i in (1, 2, 3))
        alpha = float(match.group(4)) if match.group(4) is not None else 1.0
        if max(r, g, b) > 255 or not 0.0 <= alpha <= 1.0:
            raise ValueError(f"Geçersiz renk: {value!r}")
        return r, g, b, alpha
    raise ValueError(f"Geçersiz renk: {value!r}")


def to_qss(value: str) -> str:
    """QSS için 'rgba(r,g,b,a)' yazar; Qt alfayı 0-255 ister (0-1 ondalık sayı yanlış okunur)."""
    r, g, b, alpha = parse_color(value)
    return f"rgba({r},{g},{b},{round(alpha * 255)})"


def blend(fg: str, bg: str) -> tuple[int, int, int]:
    """Yarı saydam ön rengi opak arka rengin üstüne bindirir."""
    fr, fg_, fb, fa = parse_color(fg)
    br, bg_, bb, _ = parse_color(bg)
    return (
        round(fr * fa + br * (1 - fa)),
        round(fg_ * fa + bg_ * (1 - fa)),
        round(fb * fa + bb * (1 - fa)),
    )


def _luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 kontrast oranı; `bg` opak olmalı, `fg` yarı saydamsa `bg` üstüne bindirilir."""
    lighter, darker = sorted(
        (_luminance(blend(fg, bg)), _luminance(parse_color(bg)[:3])), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)
