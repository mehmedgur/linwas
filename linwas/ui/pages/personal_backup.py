# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kişisel dosya yedeği sayfası: klasörleri harici diske / USB'ye kopyalar."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import personal_backup as pb
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("PersonalBackupPage", text)


def _size(n: int) -> str:
    return QLocale().formattedDataSize(n, 1)


class _ScanWorker(QThread):
    """Klasörleri, boyutlarını ve takılı diskleri bulur."""

    done = Signal(object, object)  # (list[(SourceFolder, boyut)], list[Destination])

    def run(self) -> None:
        folders = [(f, pb.folder_size(f.path)) for f in pb.user_folders()]
        self.done.emit(folders, pb.list_destinations())


class _BackupWorker(QThread):
    progress = Signal(int, int, int)  # (klasör sırası, klasör sayısı, yüzde)
    finished_ok = Signal(bool, str, str)  # (başarılı, yedek klasörü, hata)

    def __init__(self, sources: list[Path], destination: Path) -> None:
        super().__init__()
        self._sources = sources
        self._destination = destination

    def run(self) -> None:
        ok, target, err = pb.run_backup(
            self._sources, self._destination, lambda i, n, p: self.progress.emit(i, n, p)
        )
        self.finished_ok.emit(ok, str(target), err)


class _RestoreWorker(QThread):
    progress = Signal(int, int, int)
    finished_ok = Signal(bool, str, str)

    def __init__(self, backup: pb.BackupSet, mode: str) -> None:
        super().__init__()
        self._backup = backup
        self._mode = mode

    def run(self) -> None:
        ok, target, err = pb.run_restore(
            self._backup, self._mode, lambda i, n, p: self.progress.emit(i, n, p)
        )
        self.finished_ok.emit(ok, str(target), err)


class _RestoreDialog(QDialog):
    """Geri yükleme yeri seçimi."""

    def __init__(self, backup: pb.BackupSet, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Restore to this computer"))
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(tr("Folders: {names}").format(names=", ".join(backup.folders)), self)
        )
        self._separate = QRadioButton(
            tr("Into a new folder (Linwas-Geri-Yukleme in your home folder) — safest"), self
        )
        self._separate.setChecked(True)
        self._original = QRadioButton(
            tr("Back to the original folders — files you already have are not overwritten"),
            self,
        )
        layout.addWidget(self._separate)
        layout.addWidget(self._original)
        buttons = QDialogButtonBox(self)
        ok = buttons.addButton(tr("Restore"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setProperty("primary", True)
        buttons.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def mode(self) -> str:
        return "original" if self._original.isChecked() else "separate"


class PersonalBackupPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scan: _ScanWorker | None = None
        self._backup: _BackupWorker | None = None
        self._loaded = False
        self._checks: list[tuple[QCheckBox, pb.SourceFolder, int]] = []
        self._running: list[Path] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        title = QLabel(tr("Personal Backup"), content)
        title.setObjectName("H1")
        outer.addWidget(title)
        hint = QLabel(
            tr(
                "Copy your personal folders to an external disk or USB stick. Your files are "
                "copied as they are; nothing is deleted from your computer."
            ),
            content,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # 1. Klasörler
        folders_card = Card(content)
        h = QLabel(tr("1. What to back up"), folders_card)
        h.setObjectName("H2")
        folders_card.layout.addWidget(h)
        self._folders_box = QVBoxLayout()
        folders_card.layout.addLayout(self._folders_box)
        outer.addWidget(folders_card)

        # 2. Hedef
        dest_card = Card(content)
        h = QLabel(tr("2. Where to save it"), dest_card)
        h.setObjectName("H2")
        dest_card.layout.addWidget(h)
        row = QHBoxLayout()
        self._dest = QComboBox(dest_card)
        self._dest.currentIndexChanged.connect(self._update_state)
        row.addWidget(self._dest, 1)
        refresh = QPushButton(tr("Refresh"), dest_card)
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        dest_card.layout.addLayout(row)
        self._space_lbl = QLabel("", dest_card)
        self._space_lbl.setObjectName("Secondary")
        self._space_lbl.setWordWrap(True)
        dest_card.layout.addWidget(self._space_lbl)
        outer.addWidget(dest_card)

        # 3. Başlat
        run_card = Card(content)
        row = QHBoxLayout()
        self._start_btn = QPushButton(tr("Start backup"), run_card)
        self._start_btn.setProperty("primary", True)
        self._start_btn.clicked.connect(self._start_backup)
        row.addWidget(self._start_btn)
        row.addStretch(1)
        run_card.layout.addLayout(row)
        self._progress = QProgressBar(run_card)
        self._progress.setRange(0, 100)
        self._progress.hide()
        run_card.layout.addWidget(self._progress)
        self._result_lbl = QLabel("", run_card)
        self._result_lbl.setWordWrap(True)
        run_card.layout.addWidget(self._result_lbl)
        outer.addWidget(run_card)

        # Önceki yedekler
        prev_card = Card(content)
        h = QLabel(tr("Previous backups on this disk"), prev_card)
        h.setObjectName("H2")
        prev_card.layout.addWidget(h)
        self._prev_box = QVBoxLayout()
        prev_card.layout.addLayout(self._prev_box)
        outer.addWidget(prev_card)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    # --- Yükleme ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        if (self._scan and self._scan.isRunning()) or (self._backup and self._backup.isRunning()):
            return
        self._loaded = True
        self._start_btn.setEnabled(False)
        self._space_lbl.setText(tr("Looking for folders and disks…"))
        self._scan = _ScanWorker()
        self._scan.done.connect(self._on_scanned)
        self._scan.start()

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _on_scanned(self, folders: list, destinations: list) -> None:
        checked = {f.key for c, f, _ in self._checks if c.isChecked()} or {"DOCUMENTS", "PICTURES"}
        self._clear(self._folders_box)
        self._checks = []
        for folder, size in folders:
            box = QCheckBox(f"{folder.path.name}  ({_size(size)})", self)
            box.setChecked(folder.key in checked)
            box.toggled.connect(self._update_state)
            self._folders_box.addWidget(box)
            self._checks.append((box, folder, size))

        current = self._dest.currentData()
        self._dest.blockSignals(True)
        self._dest.clear()
        for d in destinations:
            text = f"{d.label} — {d.size}" + (f" ({d.fstype})" if d.fstype else "")
            self._dest.addItem(text, str(d.mountpoint))
        if current:
            self._dest.setCurrentIndex(max(self._dest.findData(current), 0))
        self._dest.blockSignals(False)
        self._update_state()

    # --- Durum ---

    def _selected(self) -> tuple[list[Path], int]:
        chosen = [(f.path, size) for box, f, size in self._checks if box.isChecked()]
        return [p for p, _ in chosen], sum(s for _, s in chosen)

    def _update_state(self) -> None:
        dest = self._dest.currentData()
        sources, total = self._selected()
        if not dest:
            self._space_lbl.setText(
                tr("No external disk found. Plug in a USB stick or disk, then press Refresh.")
            )
            self._start_btn.setEnabled(False)
            self._show_previous(None)
            return
        free = pb.free_bytes(Path(dest))
        enough = total < free
        text = tr("Selected: {total} · Free space on disk: {free}").format(
            total=_size(total), free=_size(free)
        )
        if not enough:
            text += "\n" + tr("Not enough free space. Choose fewer folders or another disk.")
        self._space_lbl.setText(text)
        busy = bool(self._backup and self._backup.isRunning())
        self._start_btn.setEnabled(bool(sources) and enough and not busy)
        self._show_previous(Path(dest))

    def _show_previous(self, dest: Path | None) -> None:
        self._clear(self._prev_box)
        sets = pb.list_backups(dest) if dest else []
        if not sets:
            lbl = QLabel(tr("No backups yet."), self)
            lbl.setObjectName("Secondary")
            self._prev_box.addWidget(lbl)
            return
        locale = QLocale()
        for s in sets[:10]:
            row = QWidget(self)
            row.setObjectName("CardRow")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            created = QDateTime.fromSecsSinceEpoch(int(s.created.timestamp()))
            when = locale.toString(created, QLocale.FormatType.ShortFormat)
            lay.addWidget(QLabel(f"<b>{when}</b> — {html.escape(', '.join(s.folders))}", row), 1)
            restore_btn = QPushButton(tr("Restore to this computer"), row)
            restore_btn.clicked.connect(lambda _=None, b=s: self._restore(b))
            lay.addWidget(restore_btn)
            open_btn = QPushButton(tr("Open"), row)
            open_btn.clicked.connect(
                lambda _=None, p=s.path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )
            lay.addWidget(open_btn)
            self._prev_box.addWidget(row)

    # --- Yedekleme ---

    def _start_backup(self) -> None:
        sources, _ = self._selected()
        dest = self._dest.currentData()
        if not sources or not dest:
            return
        self._running = sources
        self._start_btn.setEnabled(False)
        self._progress.setValue(0)
        self._progress.show()
        self._result_lbl.setText(tr("Backing up…"))
        self._backup = _BackupWorker(sources, Path(dest))
        self._backup.progress.connect(self._on_progress)
        self._backup.finished_ok.connect(self._on_finished)
        self._backup.start()

    def _restore(self, backup: pb.BackupSet) -> None:
        if self._backup and self._backup.isRunning():
            return
        dialog = _RestoreDialog(backup, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._running = [backup.path / name for name in backup.folders]
        self._start_btn.setEnabled(False)
        self._progress.setValue(0)
        self._progress.show()
        self._result_lbl.setStyleSheet("")
        self._result_lbl.setText(tr("Restoring…"))
        self._backup = _RestoreWorker(backup, dialog.mode)  # type: ignore[assignment]
        self._backup.progress.connect(self._on_progress)
        self._backup.finished_ok.connect(self._on_restored)
        self._backup.start()

    def _on_restored(self, ok: bool, target: str, error: str) -> None:
        self._progress.hide()
        if ok:
            self._result_lbl.setStyleSheet("color:#0e7a0e;")
            self._result_lbl.setText(tr("✓ Restored to: {path}").format(path=target))
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))
        else:
            self._result_lbl.setStyleSheet("color:#c42b1c;")
            self._result_lbl.setText(tr("Restore failed: {error}").format(error=error))
        self._update_state()

    def _on_progress(self, index: int, count: int, percent: int) -> None:
        # Her klasör toplam ilerlemenin eşit bir payı
        self._progress.setValue(int((index + percent / 100) * 100 / max(count, 1)))
        name = self._running[index].name if index < len(self._running) else ""
        text = (
            tr("Restoring {name} ({i} of {n})…")
            if isinstance(self._backup, _RestoreWorker)
            else tr("Backing up {name} ({i} of {n})…")
        )
        self._result_lbl.setText(text.format(name=name, i=index + 1, n=count))

    def _on_finished(self, ok: bool, target: str, error: str) -> None:
        self._progress.hide()
        if ok:
            self._result_lbl.setStyleSheet("color:#0e7a0e;")
            self._result_lbl.setText(tr("✓ Backup finished: {path}").format(path=target))
        else:
            self._result_lbl.setStyleSheet("color:#c42b1c;")
            self._result_lbl.setText(tr("Backup failed: {error}").format(error=error))
        self._update_state()
