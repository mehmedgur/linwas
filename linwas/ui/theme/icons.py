"""SVG simgeleri: tek renk (currentColor), tema rengiyle boyanıp QIcon yapılır."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from linwas.core.color import parse_color

ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "icons"
_SCALES = (1, 2)  # HiDPI için 1x ve 2x


def icon_names() -> list[str]:
    return sorted(path.stem for path in ICONS_DIR.glob("*.svg"))


def _render(svg: str, size: int, scale: int, alpha: float) -> QPixmap:
    image = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(alpha)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(
        painter, QRectF(0, 0, size * scale, size * scale)
    )
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(scale)
    return pixmap


@lru_cache(maxsize=512)
def load_icon(name: str, color: str, size: int = 16) -> QIcon:
    """`color`: '#RRGGBB' ya da 'rgba(...)' (alfa boyama sırasında uygulanır)."""
    path = ICONS_DIR / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"Simge yok: {name!r}")
    r, g, b, alpha = parse_color(color)
    svg = path.read_text(encoding="utf-8").replace("currentColor", f"#{r:02x}{g:02x}{b:02x}")
    icon = QIcon()
    for scale in _SCALES:
        icon.addPixmap(_render(svg, size, scale, alpha))
    return icon
