"""Qt tema katmanı (PySide6 yoksa atlanır; ekransız 'offscreen' platformunda çalışır)."""

from __future__ import annotations

import os
import re

import pytest

from linwas.core import theme
from linwas.ui.theme.qss import build_stylesheet


@pytest.mark.parametrize("edition", theme.EDITIONS)
@pytest.mark.parametrize("mode", theme.MODES)
def test_stylesheet_is_valid_text(edition, mode):
    css = build_stylesheet(edition, mode)
    assert css.count("{") == css.count("}")
    # Qt alfayı 0-255 ister; ondalık alfa (rgba(0,0,0,0.5)) yanlış okunur
    assert not re.search(r"rgba\([^)]*\.\d", css)
    assert (
        theme.palette(edition, mode).window_bg.lstrip("#").upper() in css.upper() or "rgba(" in css
    )


def test_eco_stylesheet_uses_teal_and_radius():
    css = build_stylesheet("eco", "acik")
    assert "rgba(47,111,115,255)" in css  # #2F6F73
    assert "border-radius: 7px" in css


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # sistem kütüphanesi (ör. libEGL) eksik
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")

    return QApplication.instance() or QApplication([])


def test_manager_applies_eco_theme(qapp):
    from linwas.ui.theme.manager import PREFERENCE_DARK, PREFERENCE_LIGHT, ThemeManager

    manager = ThemeManager(qapp, "eco")
    manager.set_preference(PREFERENCE_LIGHT)
    assert manager.mode == theme.MODE_LIGHT
    assert "rgba(47,111,115,255)" in qapp.styleSheet()
    assert qapp.font().pixelSize() == 14

    seen = []
    manager.modeChanged.connect(seen.append)
    manager.set_preference(PREFERENCE_DARK)
    assert manager.mode == theme.MODE_DARK
    assert seen == [theme.MODE_DARK]
    assert qapp.palette().window().color().name().upper() == "#0D1117"


def test_bundled_figtree_has_turkish_glyphs(qapp):
    from PySide6.QtGui import QFont, QFontDatabase, QRawFont

    from linwas.ui.theme.fonts import load_bundled_fonts

    assert "Figtree" in load_bundled_fonts()
    assert "Figtree" in QFontDatabase.families()
    raw = QRawFont.fromFont(QFont("Figtree", 14))
    for ch in "ğĞşŞıİçÖü":
        assert raw.supportsCharacter(ord(ch)), ch
