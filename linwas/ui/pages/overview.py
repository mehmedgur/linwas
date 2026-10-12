"""Genel Bakış sayfası: hızlı işlemler ve sistem durum kartları."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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
                tr("Import from Windows"),
                tr("Bring bookmarks, settings and files from Windows"),
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
