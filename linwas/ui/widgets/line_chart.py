# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Canlı çizgi grafiği: son N ölçüm, bir ya da iki seri (ör. indirme/yükleme)."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from linwas.ui import icons


class LineChart(QWidget):
    """Sağdan sola akan grafik. `maximum` verilmezse ölçek en büyük değere göre ayarlanır."""

    def __init__(
        self,
        roles: tuple[str, ...] = ("accent",),
        maximum: float | None = 100.0,
        points: int = 60,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Renkler çizimde rolden alınır: tema değişince grafik de değişir
        self._roles = roles
        self._maximum = maximum
        self._points = points
        self._series: list[deque[float]] = [deque(maxlen=points) for _ in roles]
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add(self, *values: float) -> None:
        for series, value in zip(self._series, values, strict=False):
            series.append(max(0.0, value))
        self.update()

    def clear(self) -> None:
        for series in self._series:
            series.clear()
        self.update()

    def _scale(self) -> float:
        if self._maximum is not None:
            return self._maximum
        top = max((max(s) for s in self._series if s), default=0.0)
        return top * 1.15 if top > 0 else 1.0

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())

        grid = QColor(icons.color_for("secondary"))
        grid.setAlpha(40)
        painter.setPen(QPen(grid, 1))
        painter.drawRoundedRect(0, 0, int(w) - 1, int(h) - 1, 6, 6)
        for i in (1, 2, 3):
            y = h * i / 4
            painter.drawLine(QPointF(0, y), QPointF(w, y))

        scale = self._scale()
        step = w / max(1, self._points - 1)
        for index, (series, role) in enumerate(zip(self._series, self._roles, strict=True)):
            if len(series) < 2:
                continue
            # Son ölçüm sağ kenarda
            start = w - (len(series) - 1) * step
            line = QPainterPath()
            for i, value in enumerate(series):
                point = QPointF(start + i * step, h - 2 - (h - 4) * min(value, scale) / scale)
                if i == 0:
                    line.moveTo(point)
                else:
                    line.lineTo(point)
            color = QColor(icons.color_for(role))
            if index == 0:
                # Yalnızca ilk serinin altı dolgulu: iki seri üst üste binince okunur kalır
                area = QPainterPath(line)
                area.lineTo(QPointF(w, h))
                area.lineTo(QPointF(start, h))
                area.closeSubpath()
                fill = QColor(color)
                fill.setAlpha(45)
                painter.fillPath(area, fill)
            painter.setPen(QPen(color, 1.8))
            painter.drawPath(line)
        painter.end()
