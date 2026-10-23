"""Pencere grupları sayfası (Arayüz altında): seçilen programların pencereleri paneldeki tek
düğmede toplanır, tıklayınca önizlemeli liste açılır (backend/window_groups.py). Şimdilik GNOME."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
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

from linwas.backend import app_folders, window_groups
from linwas.backend.window_groups import WindowGroup
from linwas.ui.app_folder_popup import AppPicker
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("WindowGroupsPage", text)


class _StatusWorker(QThread):
    done = Signal(object)

    def __init__(self, action: object = None) -> None:
        super().__init__()
        self._action = action

    def run(self) -> None:
        version = window_groups.shell_version()
        if callable(self._action):
            self._action(version)
        elif window_groups.is_installed() and not window_groups.is_current(version):
            # Linwas güncellenince eklentiyi de güncelle (oturum yeniden açılınca geçerli)
            window_groups.install(version)
        self.done.emit(
            {
                "version": version,
                "supported": window_groups.supported(version),
                "state": window_groups.state(version),
                "dtp": window_groups.dash_to_panel_active(),
            }
        )


class WindowGroupsPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[QThread] = []
        self._groups: list[WindowGroup] = window_groups.load_groups()
        self._status: dict = {}

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        title = QLabel(tr("Window Groups"), content)
        title.setObjectName("H1")
        outer.addWidget(title)
        desc = QLabel(
            tr(
                "Keep the taskbar tidy: the windows of the programs you choose (for example a "
                "browser, a mail program and a chat program) gather under one button on the "
                "panel. Click the button to see the windows with previews and switch between "
                "them."
            ),
            content,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        self._note = QLabel("", content)
        self._note.setObjectName("Warning")
        self._note.setWordWrap(True)
        self._note.hide()
        outer.addWidget(self._note)

        # Hazırlık
        self._setup = Card(content)
        h = QLabel(tr("Setup"), self._setup)
        h.setObjectName("H2")
        self._setup.layout.addWidget(h)
        self._setup_rows = QVBoxLayout()
        self._setup.layout.addLayout(self._setup_rows)
        self._setup.hide()
        outer.addWidget(self._setup)

        row = QHBoxLayout()
        self._new_btn = QPushButton(tr("New group…"), content)
        self._new_btn.clicked.connect(self._new_group)
        self._new_btn.setEnabled(False)
        row.addWidget(self._new_btn)
        row.addStretch(1)
        outer.addLayout(row)
        self._list = QVBoxLayout()
        outer.addLayout(self._list)
        self._empty = QLabel(tr("You have no window groups yet."), content)
        self._empty.setObjectName("Secondary")
        outer.addWidget(self._empty)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._groups = window_groups.load_groups()
        self._fill_groups()
        self._refresh()

    def _refresh(self, action: object = None) -> None:
        worker = _StatusWorker(action)
        worker.done.connect(self._on_status)
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.start()

    # --- Durum ---

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                WindowGroupsPage._clear(item.layout())  # type: ignore[arg-type]

    def _on_status(self, status: dict) -> None:
        self._status = status
        ok = status["supported"]
        if ok:
            self._note.hide()
        else:
            self._note.setText(
                tr("Window groups work on GNOME {low}–{high} for now.").format(
                    low=window_groups.MIN_SHELL, high=window_groups.MAX_SHELL
                )
            )
            self._note.show()
        self._setup.setVisible(ok)
        self._fill_setup(status)
        self._fill_groups()

    def _setup_row(self, ok: bool, text: str, button: str = "", slot: object = None) -> None:
        row = QHBoxLayout()
        mark = QLabel("✓" if ok else "•", self._setup)
        mark.setObjectName("Success" if ok else "Warning")
        row.addWidget(mark)
        lbl = QLabel(text, self._setup)
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        if button and callable(slot):
            btn = QPushButton(button, self._setup)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        self._setup_rows.addLayout(row)

    def _fill_setup(self, s: dict) -> None:
        self._clear(self._setup_rows)
        if not s["supported"]:
            return
        state = s["state"]
        install = lambda: self._refresh(window_groups.install)  # noqa: E731
        if state == "active":
            self._setup_row(True, tr("The window groups extension is running."))
        elif state == "missing":
            self._setup_row(
                False,
                tr("Linwas adds a small GNOME Shell extension that shows the group buttons."),
                tr("Install"),
                install,
            )
        elif state == "off":
            self._setup_row(
                False, tr("The window groups extension is turned off."), tr("Turn on"), install
            )
        elif state == "error":
            self._setup_row(
                False,
                tr("The extension could not start. Reinstall it, then log out and back in."),
                tr("Reinstall"),
                install,
            )
        else:
            self._setup_row(False, tr("Log out and back in to start the window groups extension."))
        if s["dtp"]:
            self._setup_row(
                True,
                tr(
                    "Grouped programs are hidden from the Dash to Panel taskbar. Programs "
                    "pinned to the taskbar stay there."
                ),
            )
        else:
            self._setup_row(
                False,
                tr(
                    "Grouped programs also stay on the taskbar; hiding them works with Dash "
                    "to Panel."
                ),
            )
        if state != "missing":
            row = QHBoxLayout()
            row.addStretch(1)
            btn = QPushButton(tr("Remove extension"), self._setup)
            btn.clicked.connect(self._remove_extension)
            row.addWidget(btn)
            self._setup_rows.addLayout(row)

    def _remove_extension(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Remove extension"),
            tr(
                "Remove the window groups extension? Your groups are kept; the panel buttons "
                "disappear."
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._refresh(lambda _v: window_groups.uninstall())

    # --- Gruplar ---

    def _save(self) -> None:
        window_groups.save_groups(
            self._groups, {"noWindows": tr("No open windows"), "close": tr("Close window")}
        )
        self._fill_groups()

    def _fill_groups(self) -> None:
        self._clear(self._list)
        self._empty.setVisible(not self._groups)
        for group in self._groups:
            self._list.addWidget(self._group_card(group))
        ok = bool(self._status.get("supported"))
        self._new_btn.setEnabled(ok and len(self._groups) < window_groups.MAX_GROUPS)

    def _group_card(self, group: WindowGroup) -> Card:
        card = Card(self)
        row = QHBoxLayout()
        name = QLabel(group.name, card)
        name.setObjectName("H2")
        row.addWidget(name, 1)
        for text, slot in (
            (tr("Programs…"), lambda _c=False, g=group: self._choose_programs(g)),
            (tr("Rename…"), lambda _c=False, g=group: self._rename(g)),
            (tr("Delete"), lambda _c=False, g=group: self._delete(g)),
        ):
            btn = QPushButton(text, card)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        card.layout.addLayout(row)
        names = [e.name for e in (app_folders.app_entry(r) for r in group.apps) if e]
        summary = QLabel(
            tr("Programs: {names}").format(names=", ".join(names))
            if names
            else tr("No programs yet. Choose the programs whose windows go under this button."),
            card,
        )
        summary.setObjectName("Secondary")
        summary.setWordWrap(True)
        card.layout.addWidget(summary)
        return card

    def _ask_name(self, title: str, text: str = "") -> str:
        name, ok = QInputDialog.getText(self, title, tr("Group name:"), text=text)
        name = " ".join(name.split())[: window_groups.MAX_NAME_LEN]
        return name if ok else ""

    def _new_group(self) -> None:
        name = self._ask_name(tr("New window group"))
        if not name:
            return
        group = window_groups.new_group(self._groups, name)
        self._save()
        self._choose_programs(group)
        if self._status.get("state") == "missing":
            self._refresh(window_groups.install)

    def _choose_programs(self, group: WindowGroup) -> None:
        # Bir program yalnızca bir grupta olabilir; masaüstüne taşınmış kısayollar seçilemez
        others = {r for g in self._groups if g.id != group.id for r in g.apps}
        paths = {e.ref for e in app_folders.all_apps() if e.ref.startswith("/")}
        picker = AppPicker(others | paths, self, checked=set(group.apps))
        picker.setWindowTitle(tr("Programs in {name}").format(name=group.name))
        if picker.exec() == QDialog.DialogCode.Accepted:
            chosen = [r for r in picker.selected() if not r.startswith("/")]
            group.apps = [r for r in group.apps if r in chosen] + [
                r for r in chosen if r not in group.apps
            ]
            self._save()

    def _rename(self, group: WindowGroup) -> None:
        name = self._ask_name(tr("Rename group"), group.name)
        if name:
            group.name = name
            self._save()

    def _delete(self, group: WindowGroup) -> None:
        answer = QMessageBox.question(
            self,
            tr("Delete group"),
            tr(
                'Delete the window group "{name}"? Its programs return to the taskbar; they '
                "are not removed."
            ).format(name=group.name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._groups = [g for g in self._groups if g.id != group.id]
            self._save()
