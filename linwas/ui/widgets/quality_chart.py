"""Bağlantı kalitesi çizelgesi: her dilim bir çubuk, renk durumu gösterir (son 24 saat)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from linwas.core.netlog import Bucket
from linwas.ui import icons


def tr(text: str) -> str:
    return QCoreApplication.translate("QualityChart", text)


# Durum → simge rengi rolü (icons._ROLES)
_STATE_ROLE = {
    "good": "success",
    "fair": "warning",
    "bad": "danger",
    "offline": "danger",
    "unknown": "secondary",
    "nodata": "secondary",
}


def state_text(state: str) -> str:
    return {
        "good": tr("Good"),
        "fair": tr("Slow"),
        "bad": tr("Poor"),
        "offline": tr("Disconnected"),
        "unknown": tr("Connected (no delay data)"),
        "nodata": tr("No data"),
    }.get(state, "")


def bucket_tooltip(bucket: Bucket, seconds: int) -> str:
    """Dilimin saat aralığı, durumu, ortanca gecikmesi ve sinyali."""
    start = datetime.fromtimestamp(bucket.start)
    end = datetime.fromtimestamp(bucket.start + seconds)
    parts = [f"{start:%H:%M}–{end:%H:%M}", state_text(bucket.state)]
    if bucket.rtt_ms is not None:
        parts.append(tr("{ms} ms").format(ms=round(bucket.rtt_ms)))
    if bucket.signal is not None:
        parts.append(tr("signal {percent}%").format(percent=bucket.signal))
    return " · ".join(parts)


class QualityChart(QWidget):
    """Çubuk başına bir zaman dilimi; renk durumu, "bağlantı yok" boş çubuk olarak çizilir."""

    LABEL_HEIGHT = 18
    GAP = 1.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buckets: list[Bucket] = []
        self._seconds = 900
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("Connection quality over the last 24 hours"))

    @property
    def buckets(self) -> list[Bucket]:
        return list(self._buckets)

    def set_buckets(self, buckets: list[Bucket], seconds: int, summary: str = "") -> None:
        self._buckets = list(buckets)
        self._seconds = seconds
        name = tr("Connection quality over the last 24 hours")
        self.setAccessibleName(f"{name}. {summary}" if summary else name)
        self.update()

    def _bar_width(self) -> float:
        n = len(self._buckets)
        return max(1.0, (self.width() - self.GAP * (n - 1)) / n) if n else 0.0

    def bucket_at(self, x: float) -> int | None:
        n = len(self._buckets)
        if not n or x < 0 or x >= self.width():
            return None
        step = self._bar_width() + self.GAP
        return min(n - 1, int(x // step)) if step > 0 else None

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        n = len(self._buckets)
        if not n:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_w = self._bar_width()
        area_h = self.height() - self.LABEL_HEIGHT
        text_color = QColor(icons.color_for("secondary"))
        painter.setFont(self.font())
        for i, bucket in enumerate(self._buckets):
            x = i * (bar_w + self.GAP)
            color = QColor(icons.color_for(_STATE_ROLE.get(bucket.state, "secondary")))
            if bucket.state == "nodata":
                color.setAlpha(60)
                painter.fillRect(QRectF(x, area_h - 3, bar_w, 3), color)
            elif bucket.state == "offline":
                # Bağlantı yok: içi boş çubuk (renk körlüğünde de ayırt edilir)
                painter.setPen(QPen(color, 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(x + 0.6, 0.6, max(bar_w - 1.2, 0.5), area_h - 1.2))
            else:
                if bucket.state == "unknown":
                    color.setAlpha(120)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(QRectF(x, 0, bar_w, area_h), 1.5, 1.5)
            # Saat etiketi: 6 saatte bir (yerel saat, dilim başında)
            start = datetime.fromtimestamp(bucket.start)
            if start.minute == 0 and start.hour % 6 == 0:
                label = f"{start:%H:%M}"
                width = painter.fontMetrics().horizontalAdvance(label)
                painter.setPen(text_color)
                # Sağ kenara taşan etiket içeri kaydırılır
                painter.drawText(QPointF(min(x, self.width() - width), self.height() - 3), label)
        painter.end()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        index = self.bucket_at(event.position().x())
        if index is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                bucket_tooltip(self._buckets[index], self._seconds),
                self,
            )
        super().mouseMoveEvent(event)
