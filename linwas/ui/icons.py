"""Temaya göre renklenen simgeler (theme/icon_data.py çizimlerinden).

`bind()` ile bağlanan düğme/etiketlerin simgesi tema değişince `set_palette()` ile yenilenir.
"""

from __future__ import annotations

import weakref

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

from linwas.ui.theme.icon_data import svg
from linwas.ui.theme.tokens import LIGHT, ColorSet

# Rol → renk alanı (ColorSet)
_ROLES = {
    "normal": "text_primary",
    "secondary": "text_secondary",
    "accent": "accent",
    "on_accent": "text_on_accent",
    "success": "success",
    "warning": "warning",
    "danger": "danger",
}

_palette: ColorSet = LIGHT
_bound: weakref.WeakKeyDictionary[QWidget, tuple[str, str, int]] = weakref.WeakKeyDictionary()


def color_for(role: str) -> str:
    return getattr(_palette, _ROLES.get(role, "text_primary"))


def pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    app = QGuiApplication.instance()
    dpr = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 1.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode()))
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def tile_pixmap(
    name: str, background: str, size: int = 26, glyph: str = "#ffffff", gradient: bool = False
) -> QPixmap:
    """Yuvarlak kare içinde simge (kenar çubuğu).

    gradient: macOS Sistem Ayarları gibi üstten açık, alta koyulaşan renkli kutu.
    """
    app = QGuiApplication.instance()
    dpr = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 1.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    side = float(pm.width())
    if gradient:
        base = QColor(background)
        grad = QLinearGradient(0, 0, 0, side)
        grad.setColorAt(0.0, base.lighter(128))
        grad.setColorAt(1.0, base.darker(108))
        painter.setBrush(grad)
    else:
        painter.setBrush(QColor(background))
    painter.drawRoundedRect(QRectF(0, 0, side, side), side * 0.26, side * 0.26)
    inset = side * 0.2
    renderer = QSvgRenderer(QByteArray(svg(name, glyph, 2.1 if gradient else 1.8).encode()))
    renderer.render(painter, QRectF(inset, inset, side - 2 * inset, side - 2 * inset))
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _tile(name: str, role: str, size: int) -> QPixmap:
    # "tile": nötr kutu; "tile_active": seçili öğede beyaz kutu + vurgu renkli simge;
    # "tile:#rrggbb": o renkte degradeli kutu + beyaz simge (kenar çubuğu)
    if role.startswith("tile:"):
        return tile_pixmap(name, role[5:], size, "#ffffff", gradient=True)
    if role == "tile_active":
        return tile_pixmap(name, "#ffffff", size, _palette.accent)
    return tile_pixmap(name, _palette.tile_bg, size, _palette.tile_fg)


def icon(name: str, role: str = "normal", size: int = 20) -> QIcon:
    if role.startswith("tile"):
        return QIcon(_tile(name, role, size))
    return QIcon(pixmap(name, color_for(role), size))


def _apply(widget: QWidget, name: str, role: str, size: int) -> None:
    if isinstance(widget, QAbstractButton):
        widget.setIcon(icon(name, role, size))
        widget.setIconSize(QSize(size, size))
    elif isinstance(widget, QLabel):
        if role.startswith("tile"):
            widget.setPixmap(_tile(name, role, size))
        else:
            widget.setPixmap(pixmap(name, color_for(role), size))


def bind(widget: QWidget, name: str, role: str = "normal", size: int = 20) -> None:
    """Simgeyi uygular ve tema değişiminde yenilenmek üzere kaydeder."""
    _bound[widget] = (name, role, size)
    _apply(widget, name, role, size)


def set_palette(colors: ColorSet) -> None:
    global _palette
    _palette = colors
    for widget, (name, role, size) in list(_bound.items()):
        try:
            _apply(widget, name, role, size)
        except RuntimeError:  # C++ nesnesi silinmiş
            _bound.pop(widget, None)
