"""Çalışma grupları sayfası (Arayüz altında): her grup bir sanal masaüstü; görev çubuğu yalnızca
o grubun pencerelerini gösterir (backend/workgroups.py). GNOME, XFCE ve Cinnamon."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from linwas.backend import app_folders, workgroups
from linwas.backend.workgroups import WorkGroup
from linwas.core.tasks import Task, TaskStep
from linwas.ui.app_folder_popup import AppPicker
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("WorkGroupsPage", text)


class _StatusWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        control = workgroups.can_control_windows()
        self.done.emit(
            {
                "kind": workgroups.desktop_kind(),
                "x11": workgroups.is_x11(),
                "wmctrl": workgroups.has_wmctrl(),
                "isolated": workgroups.taskbar_isolated(),
                "switcher": workgroups.switcher_state(),
                "windows": workgroups.list_windows() if control else [],
            }
        )


class _ApplyWorker(QThread):
    def __init__(
        self, groups: list[WorkGroup], action: object = None, previous: list[str] | None = None
    ) -> None:
        super().__init__()
        self._groups = groups
        self._action = action
        self._previous = previous

    def run(self) -> None:
        if callable(self._action):
            self._action()
        else:
            workgroups.apply_all(self._groups, self._previous)


class WorkGroupsPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[QThread] = []
        self._groups: list[WorkGroup] = workgroups.load_groups()
        self._status: dict = {}

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        title = QLabel(tr("Work Groups"), content)
        title.setObjectName("H1")
        outer.addWidget(title)
        desc = QLabel(
            tr(
                "Keep different jobs apart: each group (for example Project, E-mail, Games) is a "
                "separate virtual desktop, and the taskbar shows only that group's windows. "
                "Programs you add to a group can always open there."
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
        outer.addWidget(self._setup)

        row = QHBoxLayout()
        self._new_btn = QPushButton(tr("New group…"), content)
        self._new_btn.clicked.connect(self._new_group)
        row.addWidget(self._new_btn)
        row.addStretch(1)
        outer.addLayout(row)
        self._list = QVBoxLayout()
        outer.addLayout(self._list)
        self._empty = QLabel(tr("You have no groups yet."), content)
        self._empty.setObjectName("Secondary")
        outer.addWidget(self._empty)

        # Açık pencereler (X11)
        self._windows_card = Card(content)
        h = QLabel(tr("Open windows"), self._windows_card)
        h.setObjectName("H2")
        self._windows_card.layout.addWidget(h)
        self._windows_box = QVBoxLayout()
        self._windows_card.layout.addLayout(self._windows_box)
        refresh = QPushButton(tr("Refresh"), self._windows_card)
        refresh.clicked.connect(self._refresh)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addStretch(1)
        self._windows_card.layout.addLayout(row)
        self._windows_card.hide()
        outer.addWidget(self._windows_card)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._groups = workgroups.load_groups()
        self._fill_groups()
        self._refresh()

    def on_tasks_finished(self) -> None:
        self._refresh()

    def _keep(self, worker: QThread, then: object = None) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        if callable(then):
            worker.finished.connect(then)
        worker.start()

    def _refresh(self) -> None:
        worker = _StatusWorker()
        worker.done.connect(self._on_status)
        self._keep(worker)

    # --- Durum ---

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                WorkGroupsPage._clear(item.layout())  # type: ignore[arg-type]

    def _on_status(self, status: dict) -> None:
        self._status = status
        kind = status["kind"]
        supported = bool(kind)
        self._new_btn.setEnabled(supported and len(self._groups) < workgroups.MAX_GROUPS)
        notes = []
        if not supported:
            notes.append(tr("Work groups are supported on GNOME, Xfce and Cinnamon for now."))
        elif not status["x11"]:
            notes.append(
                tr(
                    "On Wayland, Linwas cannot switch groups or move windows itself. Use the "
                    "group switcher on the panel, or Super+Page Up / Page Down; Super+Shift+Page "
                    "Up / Page Down moves the window. Programs still open in their group."
                )
            )
        self._note.setText("\n".join(notes))
        self._note.setVisible(bool(notes))
        self._setup.setVisible(supported)
        self._fill_setup(status)
        self._fill_windows(status["windows"])

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
        isolated = s["isolated"]
        if isolated is None:
            self._setup_row(False, tr("No taskbar was found that Linwas can set up."))
        elif isolated:
            self._setup_row(True, tr("The taskbar shows only the current group's windows."))
        else:
            self._setup_row(
                False,
                tr("The taskbar shows the windows of all groups."),
                tr("Fix"),
                lambda: self._run_action(workgroups.isolate_taskbar),
            )
        switcher = s["switcher"]
        if switcher == "enabled":
            self._setup_row(True, tr("The group switcher is on the panel."))
        elif switcher == "available":
            self._setup_row(
                False,
                tr("Add the group switcher to the panel to change groups with one click."),
                tr("Add to panel"),
                lambda: self._run_action(workgroups.add_switcher),
            )
        elif switcher == "missing":
            self._setup_row(
                False,
                tr("The group switcher needs the GNOME Shell extensions package."),
                tr("Install"),
                lambda: self._install(workgroups.GNOME_EXTENSIONS_PACKAGE),
            )
        if s["x11"]:
            if s["wmctrl"]:
                self._setup_row(True, tr("Linwas can switch groups and move windows."))
            else:
                self._setup_row(
                    False,
                    tr("Install wmctrl so Linwas can switch groups and move windows."),
                    tr("Install"),
                    lambda: self._install("wmctrl"),
                )

    # --- Gruplar ---

    def _fill_groups(self) -> None:
        self._clear(self._list)
        self._empty.setVisible(not self._groups)
        for i, group in enumerate(self._groups):
            self._list.addWidget(self._group_card(i, group))
        kind_ok = bool(self._status.get("kind", workgroups.desktop_kind()))
        self._new_btn.setEnabled(kind_ok and len(self._groups) < workgroups.MAX_GROUPS)

    def _group_card(self, index: int, group: WorkGroup) -> Card:
        card = Card(self)
        row = QHBoxLayout()
        name = QLabel(f"{index + 1}. {group.name}", card)
        name.setObjectName("H2")
        row.addWidget(name, 1)
        for text, slot in (
            (tr("Open"), lambda _c=False, g=group: self._open(g)),
            (tr("Programs…"), lambda _c=False, g=group: self._choose_programs(g)),
            (tr("Rename…"), lambda _c=False, g=group: self._rename(g)),
            ("↑", lambda _c=False, i=index: self._move(i, -1)),
            ("↓", lambda _c=False, i=index: self._move(i, 1)),
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
            else tr('No programs yet. Programs you add open together with "Open".'),
            card,
        )
        summary.setObjectName("Secondary")
        summary.setWordWrap(True)
        card.layout.addWidget(summary)
        keep = QCheckBox(tr("Always open these programs in this group"), card)
        keep.setChecked(group.keep_apps_here)
        keep.toggled.connect(lambda on, g=group: self._set_keep(g, on))
        card.layout.addWidget(keep)
        return card

    def _apply(self, previous: list[str] | None = None) -> None:
        groups = [WorkGroup(**vars(g)) for g in self._groups]
        self._keep(_ApplyWorker(groups, previous=previous), self._refresh)
        self._fill_groups()

    def _run_action(self, action: object) -> None:
        self._keep(_ApplyWorker([], action), self._refresh)

    def _install(self, package: str) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install {name}").format(name=package),
                steps=[TaskStep(op_id="package.install", params={"name": package})],
            )
        )

    def _ask_name(self, title: str, text: str = "") -> str:
        name, ok = QInputDialog.getText(self, title, tr("Group name:"), text=text)
        name = " ".join(name.split())[: workgroups.MAX_NAME_LEN]
        return name if ok else ""

    def _new_group(self) -> None:
        if not self._groups:
            answer = QMessageBox.question(
                self,
                tr("Work groups"),
                tr(
                    "Each group becomes a virtual desktop, in order. Windows already open stay "
                    "in the first group. Continue?"
                ),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        name = self._ask_name(tr("New group"))
        if not name:
            return
        workgroups.new_group(self._groups, name)
        self._apply()

    def _choose_programs(self, group: WorkGroup) -> None:
        picker = AppPicker(set(), self, checked=set(group.apps))
        picker.setWindowTitle(tr("Programs in {name}").format(name=group.name))
        if picker.exec() == QDialog.DialogCode.Accepted:
            chosen = picker.selected()
            group.apps = [r for r in group.apps if r in chosen] + [
                r for r in chosen if r not in group.apps
            ]
            self._apply()

    def _rename(self, group: WorkGroup) -> None:
        name = self._ask_name(tr("Rename group"), group.name)
        if name:
            group.name = name
            self._apply()

    def _move(self, index: int, step: int) -> None:
        j = index + step
        if 0 <= j < len(self._groups):
            previous = [g.id for g in self._groups]
            self._groups[index], self._groups[j] = self._groups[j], self._groups[index]
            self._apply(previous)

    def _delete(self, group: WorkGroup) -> None:
        answer = QMessageBox.question(
            self,
            tr("Delete group"),
            tr(
                'Delete the group "{name}"? Its windows move to the first group; programs are '
                "not removed."
            ).format(name=group.name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            previous = [g.id for g in self._groups]
            self._groups = [g for g in self._groups if g.id != group.id]
            self._apply(previous)

    def _set_keep(self, group: WorkGroup, on: bool) -> None:
        group.keep_apps_here = on
        self._apply()

    def _open(self, group: WorkGroup) -> None:
        groups = [WorkGroup(**vars(g)) for g in self._groups]
        self._run_action(lambda: workgroups.open_group(groups, group.id))

    # --- Pencereler ---

    def _move_window(self, window_id: str, index: int) -> None:
        self._run_action(lambda: workgroups.move_window(window_id, index))

    def _fill_windows(self, windows: list) -> None:
        self._clear(self._windows_box)
        visible = bool(windows) and bool(self._groups)
        self._windows_card.setVisible(visible)
        if not visible:
            return
        for window in windows:
            if window.workspace < 0:
                continue  # bütün masaüstlerinde görünen pencere
            row = QHBoxLayout()
            lbl = QLabel(window.title or window.wm_class, self._windows_card)
            lbl.setToolTip(window.wm_class)
            row.addWidget(lbl, 1)
            combo = QComboBox(self._windows_card)
            for i, g in enumerate(self._groups):
                combo.addItem(f"{i + 1}. {g.name}", i)
            if window.workspace >= len(self._groups):
                combo.addItem(tr("Other desktop"), window.workspace)
            combo.setCurrentIndex(max(0, combo.findData(window.workspace)))
            combo.currentIndexChanged.connect(
                lambda _i, w=window, c=combo: self._move_window(w.id, c.currentData())
            )
            row.addWidget(combo)
            self._windows_box.addLayout(row)
