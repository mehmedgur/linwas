"""Yedekler ve Geri Alma sayfası."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.backups import BackupEntry, combined_backups, timeshift_available
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("BackupsPage", text)


class _LoadWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(combined_backups())
        except Exception:
            self.done.emit([])


class _BackupCard(Card):
    restore_requested = Signal(object)  # BackupEntry
    delete_requested = Signal(object)

    def __init__(self, entry: BackupEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        # Sol: bilgi
        info = QVBoxLayout()

        title_row = QHBoxLayout()
        title_lbl = QLabel(entry.label, self)
        title_lbl.setObjectName("H2")
        title_row.addWidget(title_lbl)

        # Kaynak rozeti
        if entry.source == "timeshift":
            badge = QLabel("Timeshift", self)
            badge.setStyleSheet(
                "background:#e3f2fd; color:#0067c0; border-radius:4px;"
                " padding:1px 7px; font-size:11px; font-weight:bold;"
            )
        else:
            badge = QLabel(tr("Quick rollback"), self)
            badge.setStyleSheet(
                "background:#e8f5e9; color:#0e7a0e; border-radius:4px;"
                " padding:1px 7px; font-size:11px; font-weight:bold;"
            )
        title_row.addWidget(badge)
        title_row.addStretch(1)
        info.addLayout(title_row)

        date_lbl = QLabel(entry.date, self)
        date_lbl.setObjectName("Secondary")
        info.addWidget(date_lbl)

        if entry.details:
            det_lbl = QLabel(entry.details, self)
            det_lbl.setObjectName("Secondary")
            info.addWidget(det_lbl)

        row.addLayout(info, 1)

        # Boyut
        if entry.size_mb > 0:
            size_lbl = QLabel(_fmt(entry.size_mb), self)
            size_lbl.setObjectName("Secondary")
            row.addWidget(size_lbl)

        # Butonlar
        if entry.source == "timeshift":
            restore_btn = QPushButton(tr("Restore"), self)
            restore_btn.setProperty("primary", True)
            restore_btn.clicked.connect(lambda: self.restore_requested.emit(entry))
            row.addWidget(restore_btn)

        del_btn = QPushButton(tr("Delete"), self)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(entry))
        row.addWidget(del_btn)

        self.layout.addLayout(row)


def _fmt(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class BackupsPage(BasePage):
    """Yedekler ve Geri Alma sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _LoadWorker | None = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        # Başlık + yenile + yeni yedek
        title_row = QHBoxLayout()
        title = QLabel(tr("Backups & Rollback"), content)
        title.setObjectName("H1")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._snapshot_btn = QPushButton(tr("Take full backup"), content)
        self._snapshot_btn.setProperty("primary", True)
        # Her zaman tıklanabilir — Timeshift yoksa kurulum öner
        self._snapshot_btn.clicked.connect(self._take_snapshot)
        title_row.addWidget(self._snapshot_btn)
        refresh_btn = QPushButton(tr("Refresh"), content)
        refresh_btn.clicked.connect(self._load)
        title_row.addWidget(refresh_btn)
        outer.addLayout(title_row)

        # Timeshift yoksa bilgi
        if not timeshift_available():
            info = QLabel(
                tr(
                    "Timeshift is not installed. Full system backups are not available.\n"
                    "You can install Timeshift from the Software page."
                ),
                content,
            )
            info.setWordWrap(True)
            info.setObjectName("Secondary")
            outer.addWidget(info)

        self._status_lbl = QLabel(tr("Loading…"), content)
        self._status_lbl.setObjectName("H2")
        outer.addWidget(self._status_lbl)

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

        self._load()

    def _load(self) -> None:
        self._status_lbl.setText(tr("Loading…"))
        self._clear_cards()

        self._worker = _LoadWorker()
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _clear_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_done(self, entries: object) -> None:
        entry_list: list[BackupEntry] = entries  # type: ignore[assignment]
        if not entry_list:
            self._status_lbl.setText(tr("No backups found."))
            return

        total_mb = sum(e.size_mb for e in entry_list)
        self._status_lbl.setText(
            tr("{n} backup(s) — total {size}").format(
                n=len(entry_list),
                size=_fmt(total_mb) if total_mb else "—",
            )
        )
        for entry in entry_list:
            card = _BackupCard(entry, self._cards_widget)
            card.restore_requested.connect(self._on_restore)
            card.delete_requested.connect(self._on_delete)
            self._cards_layout.addWidget(card)
            sep = QFrame(self._cards_widget)
            sep.setFrameShape(QFrame.Shape.HLine)
            self._cards_layout.addWidget(sep)

    def _take_snapshot(self) -> None:
        if not timeshift_available():
            reply = QMessageBox.question(
                self,
                tr("Timeshift not installed"),
                tr(
                    "Full system backups require Timeshift, which is not installed.\n\n"
                    "Install Timeshift now?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                task = Task(
                    label=tr("Install Timeshift"),
                    steps=[TaskStep(op_id="package.install", params={"name": "timeshift"})],
                )
                self.task_run_now.emit(task)
            return

        task = Task(
            label=tr("Take full system backup (Timeshift)"),
            steps=[TaskStep(op_id="snapshot.timeshift_create", params={})],
        )
        self.task_run_now.emit(task)

    def _on_restore(self, entry: BackupEntry) -> None:
        if entry.source != "timeshift":
            return
        snap_name = entry.id.split(":", 1)[1]
        reply = QMessageBox.warning(
            self,
            tr("Restore backup"),
            tr(
                "Restore snapshot '{name}'?\n\n"
                "The system will be reverted to this state. "
                "This requires a reboot."
            ).format(name=snap_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        task = Task(
            label=tr("Restore snapshot: {name}").format(name=snap_name),
            steps=[TaskStep(op_id="snapshot.timeshift_restore", params={"name": snap_name})],
        )
        self.task_run_now.emit(task)

    def _on_delete(self, entry: BackupEntry) -> None:
        reply = QMessageBox.question(
            self,
            tr("Delete backup"),
            tr("Delete '{label}'? This cannot be undone.").format(label=entry.label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if entry.source == "timeshift":
            snap_name = entry.id.split(":", 1)[1]
            task = Task(
                label=tr("Delete snapshot: {name}").format(name=snap_name),
                steps=[TaskStep(op_id="snapshot.timeshift_delete", params={"name": snap_name})],
            )
            self.task_run_now.emit(task)
        else:
            # Linwas rollback kaydı → kullanıcı alanı, direkt sil
            rec_id = entry.id.split(":", 1)[1]
            self._delete_linwas_record(rec_id)

    def _delete_linwas_record(self, rec_id: str) -> None:
        import shutil

        from linwas.core.rollback import ROLLBACK_DIR

        rec_dir = ROLLBACK_DIR / rec_id
        try:
            if rec_dir.exists():
                shutil.rmtree(rec_dir)
        except OSError:
            pass
        self._load()
