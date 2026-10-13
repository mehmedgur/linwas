"""Program klasörleri sayfası (Arayüz altında): klasör oluştur, masaüstünde göster, görev
çubuğuna sabitle, sil. Klasör içeriği açılır pencereden düzenlenir (ui/app_folder_popup.py)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSize, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import app_folders
from linwas.backend.app_folders import AppFolder
from linwas.core.tasks import Task, TaskStep
from linwas.ui.app_folder_popup import AppPicker, FolderPopup, save_and_refresh
from linwas.ui.folder_actions import install_menu_actions
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("AppFoldersPage", text)


class _StateWorker(QThread):
    done = Signal(str, bool)  # (masaüstü simgeleri durumu, paket depoda var mı)

    def run(self) -> None:
        state = app_folders.desktop_icons_state()
        available = state == "missing" and app_folders.ding_package_available()
        self.done.emit(state, available)


class AppFoldersPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[QThread] = []
        self._ding_state = ""
        self._ding_available = False
        self._popup: FolderPopup | None = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        title = QLabel(tr("App Folders"), content)
        title.setObjectName("H1")
        outer.addWidget(title)
        desc = QLabel(
            tr(
                "Put several programs into one folder, like on a phone home screen. The folder "
                "sits on the desktop and the taskbar; click it to see its programs. Drop a "
                "desktop shortcut on the folder to add it."
            ),
            content,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        # Masaüstü simgeleri kapalıysa
        self._ding_card = Card(content)
        self._ding_lbl = QLabel("", self._ding_card)
        self._ding_lbl.setObjectName("Warning")
        self._ding_lbl.setWordWrap(True)
        self._ding_card.layout.addWidget(self._ding_lbl)
        self._ding_btn = QPushButton("", self._ding_card)
        self._ding_btn.clicked.connect(self._fix_desktop_icons)
        row = QHBoxLayout()
        row.addWidget(self._ding_btn)
        row.addStretch(1)
        self._ding_card.layout.addLayout(row)
        self._ding_card.hide()
        outer.addWidget(self._ding_card)

        row = QHBoxLayout()
        new_btn = QPushButton(tr("New folder…"), content)
        new_btn.clicked.connect(self._new_folder)
        row.addWidget(new_btn)
        row.addStretch(1)
        outer.addLayout(row)

        self._list = QVBoxLayout()
        outer.addLayout(self._list)
        self._empty = QLabel(tr("You have no folders yet."), content)
        self._empty.setObjectName("Secondary")
        outer.addWidget(self._empty)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._reload()

    def on_tasks_finished(self) -> None:
        # Masaüstü simgeleri yeni kurulduysa sonraki oturumda açık gelsin
        if self._ding_state == "missing" and app_folders.ding_installed():
            app_folders.enable_desktop_icons()
        self._check_desktop_icons()

    def _keep(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.start()

    # --- Liste ---

    def _reload(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        folders = app_folders.load_folders()
        app_folders.refresh_launchers(folders)
        install_menu_actions()  # masaüstü sağ tık: grupla / klasöre ekle / klasörü çöz
        self._empty.setVisible(not folders)
        for folder in folders:
            self._list.addWidget(self._folder_card(folder))
        self._check_desktop_icons()

    def _folder_card(self, folder: AppFolder) -> Card:
        card = Card(self)
        row = QHBoxLayout()
        icon = QLabel(card)
        icon.setPixmap(QIcon(str(app_folders.icon_path(folder.id))).pixmap(QSize(48, 48)))
        row.addWidget(icon)
        names = [e.name for e in app_folders.folder_entries(folder)]
        text = QVBoxLayout()
        name = QLabel(folder.name, card)
        name.setObjectName("H2")
        text.addWidget(name)
        summary = QLabel(
            tr("{n} programs: {names}").format(n=len(names), names=", ".join(names[:6]))
            + ("…" if len(names) > 6 else ""),
            card,
        )
        summary.setObjectName("Secondary")
        summary.setWordWrap(True)
        text.addWidget(summary)
        row.addLayout(text, 1)
        open_btn = QPushButton(tr("Open"), card)
        open_btn.clicked.connect(lambda _c=False, f=folder: self._open(f))
        row.addWidget(open_btn)
        delete_btn = QPushButton(tr("Delete"), card)
        delete_btn.clicked.connect(lambda _c=False, f=folder: self._delete(f))
        row.addWidget(delete_btn)
        card.layout.addLayout(row)

        opts = QHBoxLayout()
        desk = QCheckBox(tr("Show on the desktop"), card)
        desk.setChecked(folder.on_desktop)
        desk.toggled.connect(lambda on, f=folder: self._set_option(f, "on_desktop", on))
        opts.addWidget(desk)
        pin = QCheckBox(tr("Pin to the taskbar"), card)
        pin.setChecked(folder.pinned)
        pin.setEnabled(app_folders.can_pin())
        if not app_folders.can_pin():
            pin.setToolTip(tr("Not yet supported on this desktop (GNOME only for now)"))
        pin.toggled.connect(lambda on, f=folder: self._set_option(f, "pinned", on))
        opts.addWidget(pin)
        opts.addStretch(1)
        card.layout.addLayout(opts)
        return card

    # --- Eylemler ---

    def _new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New folder"), tr("Folder name:"))
        name = " ".join(name.split())
        if not ok or not name:
            return
        picker = AppPicker(set(), self)
        picker.setWindowTitle(tr("Choose at least two programs"))
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        refs = picker.selected()
        if len(refs) < 2:
            QMessageBox.information(
                self, tr("New folder"), tr("A folder needs at least two programs.")
            )
            return
        folder = app_folders.new_folder(name, refs)
        folder.pinned = app_folders.can_pin()
        save_and_refresh(folder)
        self._reload()
        if self._ding_state in ("missing", "disabled"):
            self._offer_desktop_icons()

    def _open(self, folder: AppFolder) -> None:
        current = app_folders.get_folder(folder.id)
        if current is None:
            return
        self._popup = FolderPopup(current)
        self._popup.destroyed.connect(self._reload)
        self._popup.show_near_cursor()

    def _delete(self, folder: AppFolder) -> None:
        answer = QMessageBox.question(
            self,
            tr("Delete folder"),
            tr(
                'Delete the folder "{name}"? The programs are not removed; shortcuts moved '
                "into the folder go back to the desktop."
            ).format(name=folder.name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            app_folders.delete_folder(folder.id)
            self._reload()

    def _set_option(self, folder: AppFolder, attr: str, value: bool) -> None:
        current = app_folders.get_folder(folder.id)
        if current is None:
            return
        setattr(current, attr, value)
        app_folders.update_folder(current)
        app_folders.write_launchers(current)

    # --- Masaüstü simgeleri ---

    def _check_desktop_icons(self) -> None:
        worker = _StateWorker()
        worker.done.connect(self._on_state)
        self._keep(worker)

    def _on_state(self, state: str, available: bool) -> None:
        self._ding_state, self._ding_available = state, available
        has_folders = bool(app_folders.load_folders())
        if state == "disabled":
            self._ding_lbl.setText(
                tr("Desktop icons are turned off, so folders on the desktop are not visible.")
            )
            self._ding_btn.setText(tr("Turn on desktop icons"))
        elif state == "missing" and available:
            self._ding_lbl.setText(
                tr(
                    "Desktop icons are not installed, so folders on the desktop are not "
                    "visible. After installing, log out and back in."
                )
            )
            self._ding_btn.setText(tr("Install desktop icons"))
        self._ding_card.setVisible(
            has_folders and (state == "disabled" or (state == "missing" and available))
        )

    def _offer_desktop_icons(self) -> None:
        if self._ding_state == "missing" and not self._ding_available:
            return
        answer = QMessageBox.question(
            self,
            tr("Desktop icons"),
            tr(
                "Desktop icons are off, so the folder will not appear on the desktop. Turn them on?"
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._fix_desktop_icons()

    def _fix_desktop_icons(self) -> None:
        if self._ding_state == "disabled":
            app_folders.enable_desktop_icons()
            self._check_desktop_icons()
        elif self._ding_state == "missing":
            self.task_run_now.emit(
                Task(
                    label=tr("Install desktop icons"),
                    steps=[
                        TaskStep(op_id="package.install", params={"name": app_folders.DING_PACKAGE})
                    ],
                )
            )
