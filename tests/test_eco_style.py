# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Eco düzeni: renkler docs/tasarim/tokens-eco.json ile uyumlu, okunur ve QSS üretiliyor."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from linwas.core import app_settings
from linwas.ui.theme.stylesheet import build
from linwas.ui.theme.tokens import (
    ECO_DARK,
    ECO_LIGHT,
    METRICS,
    Theme,
    UiStyle,
    colors,
    contrast,
)

TOKENS = json.loads(
    (Path(__file__).resolve().parent.parent / "docs" / "tasarim" / "tokens-eco.json").read_text(
        encoding="utf-8"
    )
)
MODES = {"acik": ECO_LIGHT, "koyu": ECO_DARK}


@pytest.mark.parametrize("mode", MODES)
def test_colorset_matches_docs(mode):
    """tokens.py'deki eco renkleri belgedeki (tek doğru kaynak) değerlerle aynı olmalı."""
    doc = TOKENS["renk"][mode]
    mapping = TOKENS["colorset_eslesmesi"]
    for field, key in mapping.items():
        if field == "not":
            continue
        value = doc[key]
        if value.startswith("rgba"):  # koyu temada saydam renkler opak karşılığıyla tutulur
            continue
        assert getattr(MODES[mode], field) == value.lower(), (mode, field)


@pytest.mark.parametrize("mode", MODES)
def test_text_contrast_aa(mode):
    c = MODES[mode]
    for fg in (c.text_primary, c.text_secondary, c.accent):
        assert contrast(fg, c.background) >= 4.5, (mode, fg, "background")
        assert contrast(fg, c.surface) >= 4.5, (mode, fg, "surface")
    assert contrast(c.text_on_accent, c.accent) >= 4.5
    assert contrast(c.sidebar_text_active, c.sidebar_item_active) >= 4.5


def test_eco_is_selectable_style():
    assert "eco" in app_settings.UI_STYLES
    assert UiStyle("eco") is UiStyle.ECO
    assert colors(Theme.LIGHT, UiStyle.ECO) is ECO_LIGHT
    assert colors(Theme.DARK, UiStyle.ECO) is ECO_DARK
    # Yüksek kontrast her düzende aynı kalır
    assert colors(Theme.HIGH_CONTRAST, UiStyle.ECO) is colors(Theme.HIGH_CONTRAST, UiStyle.MACOS)


def test_eco_metrics_follow_docs():
    m = METRICS[UiStyle.ECO]
    assert (m.radius, m.card_radius) == (TOKENS["kose"]["kontrol"], TOKENS["kose"]["katman"])
    assert m.semibold == TOKENS["yazi"]["agirliklar"]["orta"]
    assert m.font_family.startswith('"Figtree"')
    assert not m.sidebar_tiles and not m.segmented_tabs


@pytest.mark.parametrize("theme", (Theme.LIGHT, Theme.DARK))
@pytest.mark.parametrize("style", list(UiStyle))
def test_stylesheet_has_no_leftover_placeholders(theme, style):
    css = build(theme, style)
    assert "{m." not in css and "{c." not in css


def test_eco_stylesheet_uses_figtree_and_medium_weight():
    css = build(Theme.LIGHT, UiStyle.ECO)
    assert 'font-family: "Figtree"' in css
    assert "font-weight: 500" in css and "font-weight: 600" not in css
    assert ECO_LIGHT.accent in css


def test_other_styles_unchanged_weights():
    # macOS/Windows görünümü eskisi gibi: Noto Sans ve 600
    for style in (UiStyle.MACOS, UiStyle.WINDOWS):
        css = build(Theme.LIGHT, style)
        assert 'font-family: "Noto Sans"' in css and "font-weight: 600" in css


def test_bundled_figtree_has_turkish_glyphs():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtGui import QFont, QRawFont
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # sistem kütüphanesi (ör. libEGL) eksik
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    from linwas.ui.theme.fonts import load_bundled_fonts

    app = QApplication.instance() or QApplication([])
    assert "Figtree" in load_bundled_fonts()
    raw = QRawFont.fromFont(QFont("Figtree", 14))
    for ch in "ğĞşŞıİçÖü":
        assert raw.supportsCharacter(ord(ch)), ch
    assert app is not None
