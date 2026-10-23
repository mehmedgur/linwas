"""Tema modeli ve renk yardımcıları (PySide6 gerektirmez)."""

from __future__ import annotations

from pathlib import Path

import pytest

from linwas.core import theme
from linwas.core.color import blend, contrast_ratio, parse_color, to_qss

ROOT = Path(__file__).resolve().parent.parent
FIELDS = list(theme.Palette.__dataclass_fields__)


def test_parse_color_hex_and_rgba():
    assert parse_color("#2F6F73") == (47, 111, 115, 1.0)
    assert parse_color("rgba(0,0,0,0.894)") == (0, 0, 0, 0.894)
    with pytest.raises(ValueError):
        parse_color("mavi")
    with pytest.raises(ValueError):
        parse_color("rgba(0,0,0,2)")


def test_to_qss_uses_0_255_alpha():
    # Qt alfayı 0-255 ister; 0.5 yazılırsa neredeyse saydam çıkar
    assert to_qss("rgba(255,255,255,0.5)") == "rgba(255,255,255,128)"
    assert to_qss("#112233") == "rgba(17,34,51,255)"


def test_blend_and_contrast():
    assert blend("rgba(0,0,0,0.5)", "#FFFFFF") == (128, 128, 128)
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)


@pytest.mark.parametrize("edition", theme.EDITIONS)
@pytest.mark.parametrize("mode", theme.MODES)
def test_palette_complete_and_parsable(edition, mode):
    pal = theme.palette(edition, mode)
    for name in FIELDS:
        parse_color(getattr(pal, name))


def test_eco_overrides_linwas():
    assert theme.palette("eco", "acik").accent == "#2F6F73"
    assert theme.palette("linwas", "acik").accent == "#005FB8"
    # Eco'nun tanımlamadığı durum rengi Linwas'tan gelir
    assert theme.palette("eco", "acik").error == theme.palette("linwas", "acik").error


def test_eco_fonts_and_weights():
    assert theme.font_families("eco")[0] == "Figtree"
    assert theme.font_style("bodyStrong", "eco").weight == 500
    assert theme.font_style("title", "eco").weight == 700
    assert theme.font_style("body", "eco").weight == 400  # eco'da gövde Linwas'tan gelir
    assert theme.font_style("title", "linwas").weight == 600


def test_unknown_edition_or_mode():
    with pytest.raises(ValueError):
        theme.palette("nope", "acik")
    with pytest.raises(ValueError):
        theme.palette("eco", "nope")


def test_load_tokens_returns_copy():
    tokens = theme.load_tokens("eco")
    tokens["renk"]["acik"]["vurgu"] = "#000000"
    assert theme.palette("eco", "acik").accent == "#2F6F73"


@pytest.mark.parametrize("mode", theme.MODES)
def test_eco_text_contrast_aa(mode):
    pal = theme.palette("eco", mode)
    for fg in (pal.text, pal.text_secondary, pal.text_tertiary, pal.accent):
        assert contrast_ratio(fg, pal.window_bg) >= 4.5, (mode, fg)
        assert contrast_ratio(fg, pal.surface) >= 4.5, (mode, fg)
    assert contrast_ratio(pal.accent_text, pal.accent) >= 4.5


def test_packaged_tokens_match_docs():
    # Paketteki kopya docs'takinden farklıysa: scripts/sync-tokens.sh çalıştır
    for name in ("tokens.json", "tokens-eco.json"):
        docs = (ROOT / "docs" / "tasarim" / name).read_text(encoding="utf-8")
        packaged = (theme.TOKENS_DIR / name).read_text(encoding="utf-8")
        assert docs == packaged, name
