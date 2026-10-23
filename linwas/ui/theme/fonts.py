"""Pakete gömülü yazı tipleri (eco teması: Figtree, SIL OFL 1.1)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase

FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "fonts"
FIGTREE_FILES = ("Figtree-Regular.ttf", "Figtree-Medium.ttf", "Figtree-Bold.ttf")


def load_bundled_fonts() -> list[str]:
    """Gömülü yazı tiplerini Qt'ye yükler; yüklenen ailelerin adlarını döndürür."""
    families: list[str] = []
    for name in FIGTREE_FILES:
        font_id = QFontDatabase.addApplicationFont(str(FONTS_DIR / name))
        if font_id < 0:
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    return families
