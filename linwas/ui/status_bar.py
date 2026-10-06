"""Alt durum çubuğu: kuyruk sayısı, ilerleme, Uygula düğmesi."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QWidget,
)


def tr(text: str) -> str:
    return QCoreApplication.translate("StatusBar", text)


class StatusBar(QWidget):
    """Ana pencerenin altındaki özel durum çubuğu."""

    apply_clicked = Signal()
    detail_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self._queue_label = QLabel(tr("Nothing pending"), self)
        layout.addWidget(self._queue_label)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedWidth(140)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        layout.addStretch(1)

        self._detail_btn = QPushButton(tr("Detail"), self)
        self._detail_btn.setVisible(False)
        self._detail_btn.clicked.connect(self.detail_clicked)
        layout.addWidget(self._detail_btn)

        self._apply_btn = QPushButton(tr("Apply"), self)
        self._apply_btn.setProperty("primary", True)
        self._apply_btn.setEnabled(False)
        self._apply_btn.setFixedWidth(120)
        self._apply_btn.clicked.connect(self.apply_clicked)
        layout.addWidget(self._apply_btn)

    def update_queue(self, count: int) -> None:
        """Kuyruktaki görev sayısını günceller."""
        if count == 0:
            self._queue_label.setText(tr("Nothing pending"))
            self._apply_btn.setText(tr("Apply"))
            self._apply_btn.setEnabled(False)
        else:
            self._queue_label.setText(tr("{n} task(s) pending").format(n=count))
            self._apply_btn.setText(tr("Apply ({n})").format(n=count))
            self._apply_btn.setEnabled(True)

    def set_running(self, running: bool, step_label: str = "") -> None:
        """Görev çalışıyor/bitti durumunu gösterir."""
        self._progress.setVisible(running)
        self._detail_btn.setVisible(running)
        self._apply_btn.setEnabled(not running)
        if running:
            self._queue_label.setText(step_label or tr("Running…"))
            self._progress.setRange(0, 0)  # belirsiz ilerleme
        else:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)

    def set_progress(self, current: int, total: int, label: str) -> None:
        self._queue_label.setText(label)
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
