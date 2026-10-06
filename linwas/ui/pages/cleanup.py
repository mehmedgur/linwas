"""Disk Temizliği sayfası."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.disk_cleanup import CleanupItem, clean_user_item, scan_cleanup_items
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("CleanupPage", text)


class _ScanWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(scan_cleanup_items())
        except Exception:
            self.done.emit([])


class _CleanWorker(QThread):
    done = Signal(bool, float)  # (başarılı, freed_mb)

    def __init__(self, item: CleanupItem) -> None:
        super().__init__()
        self._item = item

    def run(self) -> None:
        ok, freed = clean_user_item(self._item)
        self.done.emit(ok, freed)


class _CleanupCard(Card):
    clean_requested = Signal(object)  # CleanupItem

    def __init__(self, item: CleanupItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item = item

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        info = QVBoxLayout()
        title_lbl = QLabel(item.label, self)
        title_lbl.setObjectName("H2")
        info.addWidget(title_lbl)
        desc_lbl = QLabel(item.description, self)
        desc_lbl.setObjectName("Secondary")
        desc_lbl.setWordWrap(True)
        info.addWidget(desc_lbl)
        row.addLayout(info, 1)

        size_lbl = QLabel(_fmt_mb(item.size_mb), self)
        size_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")
        row.addWidget(size_lbl)

        if item.needs_root:
            badge = QLabel(tr("Requires password"), self)
            badge.setStyleSheet(
                "background-color: #fff3cc; color: #9d5d00; border-radius: 4px;"
                " padding: 1px 7px; font-size: 11px;"
            )
            row.addWidget(badge)

        self._clean_btn = QPushButton(tr("Clean"), self)
        self._clean_btn.setProperty("primary", True)
        self._clean_btn.setFixedWidth(80)
        self._clean_btn.clicked.connect(lambda: self.clean_requested.emit(item))
        row.addWidget(self._clean_btn)

        self.layout.addLayout(row)

    def set_cleaning(self) -> None:
        self._clean_btn.setEnabled(False)
        self._clean_btn.setText(tr("Cleaning…"))

    def set_done(self, freed_mb: float) -> None:
        self._clean_btn.setText(tr("Done"))
        self._clean_btn.setEnabled(False)
        self._clean_btn.setProperty("primary", False)
        self._clean_btn.style().unpolish(self._clean_btn)
        self._clean_btn.style().polish(self._clean_btn)


def _fmt_mb(mb: float) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.1f} GB"
    return f"{mb:.0f} MB"


class CleanupPage(BasePage):
    """Disk Temizliği sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scan_worker: _ScanWorker | None = None
        self._clean_workers: list[_CleanWorker] = []
        self._total_freed = 0.0

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        # Başlık + yenile
        title_row = QHBoxLayout()
        title = QLabel(tr("Disk Cleanup"), content)
        title.setObjectName("H1")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._rescan_btn = QPushButton(tr("Scan again"), content)
        self._rescan_btn.clicked.connect(self._scan)
        title_row.addWidget(self._rescan_btn)
        outer.addLayout(title_row)

        self._status_lbl = QLabel(tr("Scanning…"), content)
        self._status_lbl.setObjectName("H2")
        outer.addWidget(self._status_lbl)

        self._freed_lbl = QLabel("", content)
        self._freed_lbl.setObjectName("Secondary")
        self._freed_lbl.setVisible(False)
        outer.addWidget(self._freed_lbl)

        self._cards_widget = QWidget(content)
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        outer.addWidget(self._cards_widget)

        outer.addStretch(1)
        scroll.setWidget(content)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        self._scan()

    def _scan(self) -> None:
        self._rescan_btn.setEnabled(False)
        self._status_lbl.setText(tr("Scanning…"))
        self._clear_cards()
        self._total_freed = 0.0
        self._freed_lbl.setVisible(False)

        self._scan_worker = _ScanWorker()
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.finished.connect(lambda: self._rescan_btn.setEnabled(True))
        self._scan_worker.start()

    def _clear_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_scan_done(self, items: object) -> None:
        item_list: list[CleanupItem] = items  # type: ignore[assignment]
        total_mb = sum(i.size_mb for i in item_list)

        if not item_list:
            self._status_lbl.setText(tr("Nothing to clean — your disk is already tidy!"))
            return

        self._status_lbl.setText(
            tr("{n} item(s) found — {size} can be freed").format(
                n=len(item_list), size=_fmt_mb(total_mb)
            )
        )

        for item in item_list:
            card = _CleanupCard(item, self._cards_widget)
            card.clean_requested.connect(self._on_clean)
            self._cards_layout.addWidget(card)

    def _on_clean(self, item: CleanupItem) -> None:
        # Kart bul
        card = None
        for i in range(self._cards_layout.count()):
            w = self._cards_layout.itemAt(i)
            if w and isinstance(w.widget(), _CleanupCard) and w.widget()._item is item:
                card = w.widget()
                break

        if not item.needs_root:
            # Kullanıcı alanı — doğrudan temizle
            if card:
                card.set_cleaning()
            worker = _CleanWorker(item)
            worker.done.connect(lambda ok, freed, c=card: self._on_clean_done(c, freed))
            worker.start()
            self._clean_workers.append(worker)
        else:
            # Root gerekli → kuyruğa ekle + hemen çalıştır
            if item.id == "apt_cache":
                op = "apt.clean"
            elif item.id == "journal":
                op = "journal.vacuum"
            else:
                return
            task = Task(
                label=tr("Clean: {label}").format(label=item.label),
                steps=[TaskStep(op_id=op, params={})],
            )
            self.task_run_now.emit(task)

    def _on_clean_done(self, card: object, freed_mb: float) -> None:
        if isinstance(card, _CleanupCard):
            card.set_done(freed_mb)
        self._total_freed += freed_mb
        self._freed_lbl.setText(tr("Freed so far: {size}").format(size=_fmt_mb(self._total_freed)))
        self._freed_lbl.setVisible(True)
