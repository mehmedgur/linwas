"""Genel Bakış sayfası: sistem sağlığı özeti, hızlı işlemler ve sistem durum kartları."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import health
from linwas.ui import icons
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("OverviewPage", text)


def _icon_label(name: str, parent: QWidget) -> QLabel:
    """Kart simgesi: vurgu renginde simge, yumuşak renkli kare zemin üzerinde."""
    from PySide6.QtCore import Qt

    lbl = QLabel(parent)
    lbl.setObjectName("CardIcon")
    lbl.setFixedSize(40, 40)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icons.bind(lbl, name, "accent", 22)
    return lbl


class _QuickActionCard(Card):
    """Hızlı işlem kartı: büyük ikon + başlık + kısa açıklama."""

    clicked = Signal()

    def __init__(
        self, title: str, description: str, icon: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        from PySide6.QtCore import Qt

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("clickable", True)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(_icon_label(icon, self), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        lbl_title = QLabel(title, self)
        lbl_title.setObjectName("H2")
        texts.addWidget(lbl_title)

        lbl_desc = QLabel(description, self)
        lbl_desc.setObjectName("Secondary")
        lbl_desc.setWordWrap(True)
        texts.addWidget(lbl_desc)
        row.addLayout(texts, 1)
        self.layout.addLayout(row)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)  # type: ignore[misc]


class _StatusCard(Card):
    """Sistem durum kartı: simge + başlık + durum metni; tıklanınca ilgili sayfa açılır."""

    clicked = Signal()

    def __init__(self, title: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import Qt

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("clickable", True)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_icon_label(icon, self), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        self._title = QLabel(title, self)
        self._title.setObjectName("H2")
        texts.addWidget(self._title)

        self._status = QLabel(tr("Checking…"), self)
        self._status.setObjectName("Secondary")
        self._status.setWordWrap(True)
        texts.addWidget(self._status)
        row.addLayout(texts, 1)
        self.layout.addLayout(row)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)  # type: ignore[misc]

    def set_status(self, text: str) -> None:
        self._status.setText(text)


def _size(n: int) -> str:
    return QLocale().formattedDataSize(n, 1, QLocale.DataSizeFormat.DataSizeSIFormat)


# Durum → (metin, yazı rengi, zemin); renkler açık ve koyu temada okunur
_STATE_STYLE = {
    health.OK: ("#1e7b34", "#e3f5e1"),
    health.WARN: ("#8a5300", "#fff1cc"),
    health.BAD: ("#a4161a", "#fde2e4"),
}


def _state_text(state: str) -> str:
    return {
        health.OK: tr("Good"),
        health.WARN: tr("Check"),
        health.BAD: tr("Needs attention"),
    }[state]


class _HealthCard(Card):
    """Sistem sağlığı: her satırda ad, doluluk çubuğu, değer ve durum rozeti."""

    page_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(12)
        self._grid.setColumnStretch(1, 1)
        self.layout.addLayout(self._grid)
        self._rows = 0

    def refresh(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = 0

        root = health.disk_usage(Path("/"))
        if root:
            self._add(
                tr("System disk"),
                root.percent,
                tr("%1 free of %2")
                .replace("%1", _size(root.total - root.used))
                .replace("%2", _size(root.total)),
                health.state_for(root.percent, 80, 90),
                "cleanup",
            )
        if health.home_is_separate():
            home = health.disk_usage(Path.home())
            if home:
                self._add(
                    tr("Personal files disk"),
                    home.percent,
                    tr("%1 free of %2")
                    .replace("%1", _size(home.total - home.used))
                    .replace("%2", _size(home.total)),
                    health.state_for(home.percent, 80, 90),
                    "cleanup",
                )
        mem = health.memory_usage()
        if mem:
            self._add(
                tr("Memory (RAM)"),
                mem.percent,
                tr("%1 of %2 in use")
                .replace("%1", _size(mem.used))
                .replace("%2", _size(mem.total)),
                health.state_for(mem.percent, 80, 92),
                "taskmgr",
            )
        from linwas.backend.power import list_batteries

        for bat in list_batteries():
            if bat.health is None:
                continue
            self._add(
                tr("Battery health"),
                bat.health,
                tr("%1% of its original capacity").replace("%1", str(bat.health)),
                health.battery_state(bat.health),
                "power",
            )

    def _add(self, name: str, percent: int, detail: str, state: str, page_id: str) -> None:
        r = self._rows
        label = QLabel(name, self)
        label.setMinimumWidth(170)
        self._grid.addWidget(label, r, 0)
        bar = QProgressBar(self)
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, percent)))
        bar.setTextVisible(False)
        bar.setAccessibleName(name)
        self._grid.addWidget(bar, r, 1, Qt.AlignmentFlag.AlignVCenter)
        value = QLabel(detail, self)
        value.setObjectName("Secondary")
        self._grid.addWidget(value, r, 2)
        fg, bg = _STATE_STYLE[state]
        pill = QLabel(_state_text(state), self)
        pill.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:10px; padding:2px 10px;"
            " font-size: 13px; font-weight: bold;"
        )
        self._grid.addWidget(pill, r, 3)
        more = QPushButton(tr("Open"), self)
        more.setAccessibleName(tr("Open") + " " + name)
        more.clicked.connect(lambda _=False, pid=page_id: self.page_requested.emit(pid))
        self._grid.addWidget(more, r, 4)
        self._rows += 1


class OverviewPage(QWidget):
    """Genel Bakış sayfası."""

    page_requested = Signal(str)  # hızlı işlem tıklandığında sayfa ID'si

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(16)

        # Başlık
        title = QLabel(tr("Overview"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Sistem sağlığı (gerçek değerler; sayfa her açıldığında yenilenir)
        health_label = QLabel(tr("System health"), content)
        health_label.setObjectName("Secondary")
        outer.addWidget(health_label)
        self._health = _HealthCard(content)
        self._health.page_requested.connect(self.page_requested)
        self._health.refresh()
        outer.addWidget(self._health)

        # Hızlı işlemler (2×2 ızgara)
        quick_label = QLabel(tr("Quick actions"), content)
        quick_label.setObjectName("Secondary")
        outer.addWidget(quick_label)

        quick_grid = QGridLayout()
        quick_grid.setSpacing(12)
        quick_actions = [
            ("taskmgr", tr("Task Manager"), tr("View running processes and startup programs")),
            ("cleanup", tr("Disk Cleanup"), tr("Free up space by removing unnecessary files")),
            (
                "personal_backup",
                tr("Back Up My Files"),
                tr("Back up personal files to an external drive"),
            ),
            (
                "migrate",
                tr("Transfer"),
                tr("Bring files and settings from Windows or another Linux"),
            ),
        ]
        for i, (page_id, label, desc) in enumerate(quick_actions):
            card = _QuickActionCard(label, desc, page_id, content)
            card.clicked.connect(lambda pid=page_id: self.page_requested.emit(pid))
            quick_grid.addWidget(card, i // 2, i % 2)
        outer.addLayout(quick_grid)

        # Sistem durum kartları
        status_label = QLabel(tr("System status"), content)
        status_label.setObjectName("Secondary")
        outer.addWidget(status_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self._updates_card = _StatusCard(tr("Updates"), "updates", content)
        self._drivers_card = _StatusCard(tr("Drivers"), "drivers", content)
        self._wifi_card = _StatusCard(tr("Wi-Fi & Bluetooth"), "network", content)
        for page_id, card in (
            ("updates", self._updates_card),
            ("drivers", self._drivers_card),
            ("network", self._wifi_card),
        ):
            card.clicked.connect(lambda pid=page_id: self.page_requested.emit(pid))
            status_row.addWidget(card)
        outer.addLayout(status_row)

        outer.addStretch(1)
        scroll.setWidget(content)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self._health.refresh()
        super().showEvent(event)  # type: ignore[misc]
