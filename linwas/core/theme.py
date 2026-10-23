"""Tema modeli (Qt'siz): token dosyalarını okur, sürüme ve moda göre anlamsal renk paleti üretir.

Tek doğru kaynak docs/tasarim/tokens.json ve tokens-eco.json'dur; paketteki kopyalar
`scripts/sync-tokens.sh` ile güncellenir. Eco sürümü tokens.json üzerine bindirilir.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

EDITION_LINWAS = "linwas"
EDITION_ECO = "eco"
EDITIONS = (EDITION_LINWAS, EDITION_ECO)

MODE_LIGHT = "acik"
MODE_DARK = "koyu"
MODES = (MODE_LIGHT, MODE_DARK)

TOKENS_DIR = Path(__file__).resolve().parent.parent / "resources" / "tokens"


@dataclass(frozen=True)
class Palette:
    """Bileşenlerin kullandığı anlamsal renkler (hepsi '#RRGGBB' ya da 'rgba(...)' metni)."""

    window_bg: str
    surface: str
    surface_alt: str
    border: str
    divider: str
    text: str
    text_secondary: str
    text_tertiary: str
    text_disabled: str
    accent: str
    accent_bg: str
    accent_text: str
    selected_bg: str
    success: str
    warning: str
    error: str


@dataclass(frozen=True)
class FontStyle:
    size: int
    line_height: int
    weight: int


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read(name: str) -> dict[str, Any]:
    return json.loads((TOKENS_DIR / name).read_text(encoding="utf-8"))


@cache
def _tokens(edition: str) -> dict[str, Any]:
    if edition not in EDITIONS:
        raise ValueError(f"Bilinmeyen sürüm: {edition!r}")
    base = _read("tokens.json")
    if edition == EDITION_LINWAS:
        return base
    return _deep_merge(base, _read("tokens-eco.json"))


def load_tokens(edition: str = EDITION_LINWAS) -> dict[str, Any]:
    """Sürümün birleştirilmiş token sözlüğü (kopya; değiştirmek güvenlidir)."""
    return copy.deepcopy(_tokens(edition))


def _pick(colors: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = colors.get(key)
        if isinstance(value, str):
            return value
    raise KeyError(f"Renk bulunamadı: {keys}")


def palette(edition: str = EDITION_LINWAS, mode: str = MODE_LIGHT) -> Palette:
    """Sürüm ve moda göre anlamsal paleti çözer.

    Eco anahtarları (zemin, yuzey, kenar...) önce aranır; yoksa Linwas (Microsoft) anahtarlarına
    düşülür. Böylece eco'nun tanımlamadığı değerler (başarılı/hata) Linwas'tan gelir.
    """
    if mode not in MODES:
        raise ValueError(f"Bilinmeyen mod: {mode!r}")
    colors = _tokens(edition)["renk"][mode]
    return Palette(
        window_bg=_pick(colors, "zemin", "mica_zemin"),
        surface=_pick(colors, "yuzey", "kart"),
        surface_alt=_pick(colors, "yuzey_2", "kontrol_alternatif"),
        border=_pick(colors, "kenar", "kart_kenar"),
        divider=_pick(colors, "ayirici"),
        text=_pick(colors, "metin"),
        text_secondary=_pick(colors, "metin_ikincil"),
        text_tertiary=_pick(colors, "metin_ucuncul", "metin_ikincil"),
        text_disabled=_pick(colors, "metin_pasif"),
        accent=_pick(colors, "vurgu"),
        accent_bg=_pick(colors, "vurgu_zemin", "sade_uzerinde"),
        accent_text=_pick(colors, "vurgu_ustu_metin"),
        selected_bg=_pick(colors, "secili_oge_zemin", "sade_uzerinde"),
        success=_pick(colors, "basarili"),
        warning=_pick(colors, "uyari"),
        error=_pick(colors, "hata"),
    )


def font_families(edition: str = EDITION_LINWAS) -> list[str]:
    return list(_tokens(edition)["font"]["aile"])


def font_style(name: str, edition: str = EDITION_LINWAS) -> FontStyle:
    """'caption', 'body', 'bodyStrong', 'bodyLarge', 'subtitle', 'title', 'titleLarge'."""
    style = _tokens(edition)["yazi"][name]
    return FontStyle(size=style["boyut"], line_height=style["satir"], weight=style["agirlik"])
