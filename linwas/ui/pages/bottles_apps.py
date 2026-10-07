"""Programlar › Windows programları (Bottles): Linwas'ın oluşturduğu şişeler ve programları."""

from __future__ import annotations

import html

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
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

from linwas.backend import bottles
from linwas.ui.bottles_runner import BottlesRunner
from linwas.ui.widgets.app_card import AppAvatar
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("BottlesAppsView", text)


class _LoadWorker(QThread):
    done = Signal(object)  # (bottles kurulu mu, list[Bottle])

    def run(self) -> None:
        available = bottles.bottles_available()
        items = bottles.list_bottles() if available else []
        for item in items:
            item.programs = bottles.list_programs(item.id)
        self.done.emit((available, items))


class BottlesAppsView(QWidget):
    open_exe_requested = Signal()  # ".exe aç" düğmesi → sayfa dosya seçtirir
    install_bottles_requested = Signal()

    def __init__(self, runner: BottlesRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._worker: _LoadWorker | None = None
        self._stale = True
        runner.finished.connect(self.reload)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(12)

        top = QHBoxLayout()
        intro = QLabel(
            tr(
                "Windows programs run with Bottles; each program gets its own Windows "
                "environment. Prefer a Linux alternative when there is one; it is faster and "
                "gets updates automatically."
            ),
            content,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        open_btn = QPushButton(tr("Open a Windows program…"), content)
        open_btn.clicked.connect(self.open_exe_requested)
        top.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(top)

        self._status = QLabel(tr("Loading…"), content)
        self._status.setObjectName("Secondary")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)
        self._install_btn = QPushButton(tr("Install Bottles"), content)
        self._install_btn.setProperty("primary", True)
        self._install_btn.clicked.connect(self.install_bottles_requested)
        self._install_btn.hide()
        outer.addWidget(self._install_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self._list = QVBoxLayout()
        self._list.setSpacing(10)
        outer.addLayout(self._list)
        outer.addStretch(1)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if self._stale:
            self.reload()

    def mark_stale(self) -> None:
        self._stale = True

    def reload(self) -> None:
        if not self.isVisible():
            self._stale = True
            return
        if self._worker and self._worker.isRunning():
            return
        self._stale = False
        self._worker = _LoadWorker(self)
        self._worker.done.connect(self._on_loaded)
        self._worker.start()

    def _clear(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_loaded(self, result: tuple) -> None:
        available, items = result
        self._clear()
        self._install_btn.setVisible(not available)
        if not available:
            self._status.setText(
                tr(
                    "Bottles is not installed. Linwas installs it from Flathub (and Flatpak "
                    "too if needed); it brings its own Wine."
                )
            )
            self._status.show()
            return
        if not items:
            self._status.setText(
                tr("No Windows programs yet. Open a setup file (.exe or .msi) to install one.")
            )
            self._status.show()
            return
        self._status.hide()
        for item in items:
            self._list.addWidget(self._bottle_card(item))

    def _bottle_card(self, item: bottles.Bottle) -> Card:
        card = Card(self)
        head = QHBoxLayout()
        title = QLabel(html.escape(item.name), card)
        title.setObjectName("AppName")
        head.addWidget(title)
        kind = tr("Game") if item.environment == "gaming" else tr("Application")
        if item.reason == "risk":
            kind += " · " + tr("risky file")
        info = QLabel(kind, card)
        info.setObjectName("Caption")
        head.addWidget(info)
        head.addStretch(1)
        uninstall = QPushButton(tr("Add or remove programs"), card)
        uninstall.clicked.connect(lambda _=False, b=item.id: self._runner.run_uninstaller(b))
        head.addWidget(uninstall)
        delete = QPushButton(tr("Delete"), card)
        delete.clicked.connect(lambda _=False, b=item: self._delete(b))
        head.addWidget(delete)
        card.layout.addLayout(head)

        if not item.programs:
            empty = QLabel(tr("No program found in this environment."), card)
            empty.setObjectName("Secondary")
            card.layout.addWidget(empty)
        for program in item.programs:
            name = program["name"]
            row = QHBoxLayout()
            row.addWidget(AppAvatar(name, "", 32, card))
            row.addWidget(QLabel(html.escape(name), card), 1)
            if not bottles.has_shortcut(item.id, name):
                menu = QPushButton(tr("Add to menu"), card)
                menu.clicked.connect(lambda _=False, b=item, n=name: self._add_shortcut(b, n))
                row.addWidget(menu)
            run = QPushButton(tr("Open"), card)
            run.setProperty("primary", True)
            run.clicked.connect(
                lambda _=False, b=item, n=name: self._runner.run_program(b.id, n, b.read_dir)
            )
            row.addWidget(run)
            card.layout.addLayout(row)
        return card

    def _add_shortcut(self, item: bottles.Bottle, program: str) -> None:
        bottles.write_shortcut(item.id, program, item.read_dir)
        self.reload()

    def _delete(self, item: bottles.Bottle) -> None:
        answer = QMessageBox.question(
            self,
            tr("Delete"),
            tr(
                'Delete "{name}" with its Windows environment? All programs and files in it '
                "will be removed. This can't be undone."
            ).format(name=item.name),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not bottles.remove_bottle(item.id):
            QMessageBox.warning(self, tr("Delete"), tr("It could not be deleted."))
        self.reload()
