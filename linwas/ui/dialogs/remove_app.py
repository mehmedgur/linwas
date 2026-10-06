"""Program kaldırma onay penceresi ve akışı.

Akış: Kaldır → plan arka planda hesaplanır (apt-get -s) → bu pencere
(kaldırılacak paketler, artık gerekmeyenler, "Ayarlarımı da sil") → görev
`task_ready` ile sayfaya döner → standart onay/yedek penceresi.
Kritik paket varsa pencere yalnızca nedeni gösterir, kaldırma düğmesi olmaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.installed_apps import is_preinstalled
from linwas.core.package_guard import BlockedPackage, plan_apt_removal, snap_blocked
from linwas.core.tasks import Task, TaskStep


def tr(text: str) -> str:
    return QCoreApplication.translate("RemoveAppDialog", text)


@dataclass
class RemovalRequest:
    """Kaldırılacak program."""

    id: str  # APT paket adı, Flatpak kimliği veya snap adı
    name: str  # görünen ad
    source: str  # "apt" | "third-party" | "flatpak" | "snap"
    preinstalled: bool = False


@dataclass
class RemovalPlan:
    request: RemovalRequest
    removed: list[str] = field(default_factory=list)
    autoremoved: list[str] = field(default_factory=list)
    blocked: list[BlockedPackage] = field(default_factory=list)
    error: str = ""


# Kaynak → (normal işlem, ayarları da silen işlem, parametre adı)
_REMOVE_OPS = {
    "apt": ("app.remove_apt", "app.remove_apt_purge", "name"),
    "third-party": ("app.remove_apt", "app.remove_apt_purge", "name"),
    "flatpak": ("app.remove_flatpak", "app.remove_flatpak_data", "app_id"),
    "snap": ("app.remove_snap", "app.remove_snap_purge", "name"),
}

_UPDATE_OPS = {
    "apt": ("package.upgrade_one", "name"),
    "third-party": ("package.upgrade_one", "name"),
    "flatpak": ("flatpak.update", "app_id"),
    "snap": ("snap.refresh", "name"),
}


def build_removal_task(request: RemovalRequest, delete_settings: bool) -> Task:
    normal, purge, param = _REMOVE_OPS[request.source]
    op_id = purge if delete_settings else normal
    return Task(
        label=tr("Remove {name}").format(name=request.name),
        steps=[TaskStep(op_id=op_id, params={param: request.id})],
    )


def build_update_task(app_id: str, name: str, source: str) -> Task:
    op_id, param = _UPDATE_OPS[source]
    return Task(
        label=tr("Update {name}").format(name=name),
        steps=[TaskStep(op_id=op_id, params={param: app_id})],
    )


def compute_plan(request: RemovalRequest) -> RemovalPlan:
    """Kaldırma planını hesaplar (Qt kullanmaz; iş parçacığında çağrılır)."""
    plan = RemovalPlan(request=request)
    if request.source in ("apt", "third-party"):
        apt = plan_apt_removal(request.id)
        plan.removed, plan.autoremoved = apt.removed, apt.autoremoved
        plan.blocked, plan.error = apt.blocked, apt.error
        # Arama sonuçlarından gelen istekte bu bilgi yoktur
        request.preinstalled = request.preinstalled or is_preinstalled(request.id)
    elif request.source == "snap":
        plan.removed = [request.id]
        plan.blocked = snap_blocked(request.id)
    else:
        plan.removed = [request.id]
    return plan


class _PlanWorker(QThread):
    done = Signal(object)  # RemovalPlan

    def __init__(self, request: RemovalRequest) -> None:
        super().__init__()
        self._request = request

    def run(self) -> None:
        try:
            plan = compute_plan(self._request)
        except Exception as exc:  # kritik liste okunamazsa kaldırma yapılmaz
            plan = RemovalPlan(request=self._request, error=str(exc))
        self.done.emit(plan)


class RemovalFlow(QObject):
    """Kaldır düğmesinden görev oluşturmaya kadar olan akış."""

    task_ready = Signal(Task)
    busy_changed = Signal(bool)

    def __init__(self, parent_widget: QWidget) -> None:
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._worker: _PlanWorker | None = None

    def start(self, request: RemovalRequest) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.busy_changed.emit(True)
        self._worker = _PlanWorker(request)
        self._worker.done.connect(self._on_plan)
        self._worker.start()

    def _on_plan(self, plan: RemovalPlan) -> None:
        self.busy_changed.emit(False)
        dialog = RemoveAppDialog(plan, self._parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.task_ready.emit(build_removal_task(plan.request, dialog.delete_settings))


# --- Pencere ---


def _category_texts() -> dict[str, str]:
    """Kritik paket kategorilerinin sade açıklaması (CATEGORIES sırasıyla)."""
    return {
        "desktop": tr("the desktop (the screen with your windows and menus)"),
        "login": tr("the login screen"),
        "network": tr("internet and network connections"),
        "sound": tr("sound"),
        "system": tr("core parts of the operating system"),
        "linwas": tr("Linwas itself"),
    }


def _settings_hint(source: str) -> str:
    if source == "flatpak":
        return tr(
            "Deletes this program's data and settings in your home folder "
            "(~/.var/app). Your own documents are not touched."
        )
    if source == "snap":
        return tr(
            "The program's data is always removed. Normally a copy is kept so it can be "
            "restored later; with this option no copy is kept."
        )
    return tr(
        "Deletes the program's system-wide settings files. Personal settings in your "
        "home folder can't always be found reliably and stay where they are."
    )


class RemoveAppDialog(QDialog):
    """Kaldırma onayı ya da (kritik paket varsa) engelleme açıklaması."""

    def __init__(self, plan: RemovalPlan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        req = plan.request
        self.setWindowTitle(tr("Remove {name}").format(name=req.name))
        self.setMinimumWidth(480)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._settings_box: QCheckBox | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        if plan.error:
            self._build_error(layout, plan)
        elif plan.blocked:
            self._build_blocked(layout, plan)
        else:
            self._build_confirm(layout, plan)

    @property
    def delete_settings(self) -> bool:
        return bool(self._settings_box and self._settings_box.isChecked())

    def _title(self, layout: QVBoxLayout, text: str) -> None:
        lbl = QLabel(text, self)
        lbl.setObjectName("H2")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

    def _text(self, layout: QVBoxLayout, text: str, secondary: bool = False) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setWordWrap(True)
        if secondary:
            lbl.setObjectName("Secondary")
        layout.addWidget(lbl)
        return lbl

    def _package_list(self, layout: QVBoxLayout, names: list[str]) -> None:
        lst = QListWidget(self)
        lst.addItems(names)
        lst.setMaximumHeight(min(28 + 22 * len(names), 160))
        lst.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        layout.addWidget(lst)

    def _close_only(self, layout: QVBoxLayout) -> None:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_error(self, layout: QVBoxLayout, plan: RemovalPlan) -> None:
        self._title(layout, tr("{name} can't be removed right now").format(name=plan.request.name))
        self._text(layout, tr("Linwas couldn't work out what would be removed."))
        details = self._text(layout, plan.error, secondary=True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._close_only(layout)

    def _build_blocked(self, layout: QVBoxLayout, plan: RemovalPlan) -> None:
        self._title(
            layout, tr("Removing {name} would break your system").format(name=plan.request.name)
        )
        texts = _category_texts()
        categories = sorted({b.category for b in plan.blocked}, key=list(texts).index)
        parts = [texts[c] for c in categories]
        warn = self._text(
            layout,
            tr(
                "The package manager would also remove programs that {parts} need. "
                "Linwas stopped this so your computer keeps working."
            ).format(parts=", ".join(parts)),
        )
        warn.setStyleSheet("color: #c42b1c; font-weight: bold;")
        self._text(layout, tr("Protected packages that would be removed:"), secondary=True)
        self._package_list(layout, [b.name for b in plan.blocked])
        self._close_only(layout)

    def _build_confirm(self, layout: QVBoxLayout, plan: RemovalPlan) -> None:
        req = plan.request
        self._title(layout, tr("Remove {name}?").format(name=req.name))

        if req.preinstalled:
            note = self._text(
                layout,
                tr(
                    "This program came with your system. You can remove it, but other "
                    "parts of the system may expect it to be there."
                ),
            )
            note.setStyleSheet("color: #9d5d00;")

        if len(plan.removed) > 1:
            self._text(layout, tr("These packages will be removed:"))
            self._package_list(layout, plan.removed)
        if plan.autoremoved:
            self._text(
                layout,
                tr("No longer needed — these will also be removed:"),
            )
            self._package_list(layout, plan.autoremoved)
        if req.source == "flatpak":
            self._text(
                layout,
                tr("Runtimes that no other program uses will also be removed."),
                secondary=True,
            )

        self._settings_box = QCheckBox(tr("Also delete my settings"), self)
        self._settings_box.setChecked(False)
        layout.addWidget(self._settings_box)
        self._text(layout, _settings_hint(req.source), secondary=True)
        undo = self._text(
            layout,
            tr("You can reinstall it with “Undo changes” afterwards."),
            secondary=True,
        )
        self._settings_box.toggled.connect(
            lambda on: undo.setText(
                tr("“Undo changes” reinstalls the program, but deleted settings don't come back.")
                if on
                else tr("You can reinstall it with “Undo changes” afterwards.")
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        remove_btn = buttons.addButton(tr("Remove"), QDialogButtonBox.ButtonRole.AcceptRole)
        remove_btn.setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setFocus()
