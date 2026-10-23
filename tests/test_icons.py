"""Simge kümesi: biçim kuralları (Qt'siz) ve boyama (Qt'li, atlanabilir)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ICONS = Path(__file__).resolve().parent.parent / "linwas" / "resources" / "icons"
SVG_FILES = sorted(ICONS.glob("*.svg"))
NS = "{http://www.w3.org/2000/svg}"


def test_icon_set_not_empty():
    names = {p.stem for p in SVG_FILES}
    # Eco "Hakkında" ayar sayfasındaki gezinme + pencere düğmeleri
    for needed in (
        "appearance",
        "display",
        "network",
        "sound",
        "storage",
        "users",
        "security",
        "apps",
        "accessibility",
        "about",
        "search",
        "back",
        "window-close",
    ):
        assert needed in names, needed


@pytest.mark.parametrize("path", SVG_FILES, ids=lambda p: p.stem)
def test_svg_follows_design_rules(path):
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    assert root.tag == f"{NS}svg"
    assert root.get("viewBox") == "0 0 16 16"
    assert root.get("stroke") == "currentColor"
    assert root.get("stroke-width") == "1"  # tokens-eco.json: simge.cizgi
    assert root.get("stroke-linecap") == "round"
    assert root.get("stroke-linejoin") == "round"
    text = path.read_text(encoding="utf-8")
    # Renk yalnızca currentColor olabilir (tema rengiyle boyanacak)
    assert "#" not in text
    assert "rgb" not in text


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    return QApplication.instance() or QApplication([])


def test_icons_render_in_requested_color(qapp):
    from linwas.ui.theme.icons import icon_names, load_icon

    want = (0x2F, 0x6F, 0x73)
    for name in icon_names():
        image = load_icon(name, "#2F6F73", 16).pixmap(16, 16).toImage()
        opaque = [
            image.pixelColor(x, y)
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() >= 100
        ]
        assert opaque, f"{name}: boş çizildi"
        # Premultiplied alfa yüzünden kenarlarda ±8 sapma olabilir
        for color in opaque:
            got = (color.red(), color.green(), color.blue())
            assert all(abs(a - b) <= 8 for a, b in zip(got, want, strict=True)), (name, got)


def test_unknown_icon_raises(qapp):
    from linwas.ui.theme.icons import load_icon

    with pytest.raises(KeyError):
        load_icon("yok", "#000000")
