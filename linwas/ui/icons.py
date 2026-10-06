"""Temaya göre renklenen simgeler (theme/icon_data.py çizimlerinden).

`bind()` ile bağlanan düğme/etiketlerin simgesi tema değişince `set_palette()` ile yenilenir.
"""

from __future__ import annotations

import weakref

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
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


def icon(name: str, role: str = "normal", size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color_for(role), size))


def _apply(widget: QWidget, name: str, role: str, size: int) -> None:
    if isinstance(widget, QAbstractButton):
        widget.setIcon(icon(name, role, size))
        widget.setIconSize(QSize(size, size))
    elif isinstance(widget, QLabel):
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
