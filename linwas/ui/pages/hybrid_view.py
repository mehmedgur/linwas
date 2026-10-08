"""Sürücüler › Hibrit grafik kartı: Dengeli kip + programı güçlü kartla açma (+ Ubuntu kipi)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import hybrid_gpu
from linwas.backend.hardware_cards import short_name
from linwas.core.tasks import Task, TaskStep
from linwas.ui import icons
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("HybridGraphics", text)


def _app_icon(name: str) -> QIcon:
    if name and Path(name).is_absolute():
        return QIcon(name)
    return QIcon.fromTheme(name) if name else QIcon()


def _language() -> str:
    from linwas.core import app_settings

    return app_settings.load().language


class _AppPicker(QDialog):
    """Güçlü kartla açılacak programı seçme penceresi."""

    def __init__(self, apps: list[hybrid_gpu.DesktopApp], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Add a program"))
        self.resize(460, 520)
        self.selected: hybrid_gpu.DesktopApp | None = None
        lay = QVBoxLayout(self)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(tr("Search programs"))
        self._search.setAccessibleName(tr("Search programs"))
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)
        self._list = QListWidget(self)
        self._list.setIconSize(QSize(24, 24))
        for app in apps:
            item = QListWidgetItem(_app_icon(app.icon), app.name)
            item.setData(Qt.ItemDataRole.UserRole, app)
            self._list.addItem(item)
        self._list.itemDoubleClicked.connect(lambda _: self._accept())
        lay.addWidget(self._list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _accept(self) -> None:
        item = self._list.currentItem()
        if item is None or item.isHidden():
            return
        self.selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class HybridCard(Card):
    task_run_now = Signal(object)  # Task

    def __init__(self, info: hybrid_gpu.HybridInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info = info
        self.layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(14)
        ico = QLabel(self)
        ico.setObjectName("CategoryIcon")
        ico.setFixedSize(48, 48)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icons.bind(ico, "display", "on_accent", 28)
        head.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(tr("Hybrid graphics"), self)
        title.setObjectName("H2")
        text.addWidget(title)
        sub = QLabel(
            tr(
                "Your computer has two graphics cards. To save power, {integrated} draws the "
                "desktop; {discrete} is used for the programs you choose below."
            ).format(
                integrated=short_name(info.integrated.name),
                discrete=short_name(info.discrete.name),
            ),
            self,
        )
        sub.setObjectName("Secondary")
        sub.setWordWrap(True)
        text.addWidget(sub)
        head.addLayout(text, 1)
        self.layout.addLayout(head)

        if info.prime_select:
            self.layout.addLayout(self._mode_row())

        h = QLabel(tr("Programs that use the powerful card"), self)
        h.setObjectName("AppName")
        self.layout.addWidget(h)
        self._apps_box = QVBoxLayout()
        self._apps_box.setSpacing(4)
        self.layout.addLayout(self._apps_box)

        row = QHBoxLayout()
        add = QPushButton(tr("Add a program…"), self)
        add.clicked.connect(self._add)
        row.addWidget(add)
        row.addStretch(1)
        self.layout.addLayout(row)
        tip = QLabel(
            tr(
                "The program opens on the powerful card from the application menu. In GNOME you "
                "can also right-click a program in the app grid to start it on the powerful card "
                "once."
            ),
            self,
        )
        tip.setObjectName("Secondary")
        tip.setWordWrap(True)
        self.layout.addWidget(tip)
        self._refresh()

    # --- Ubuntu prime-select kipi ---

    def _mode_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Mode:"), self))
        self._mode = QComboBox(self)
        for value, label in (
            ("intel", tr("Power saving (only the built-in card)")),
            ("on-demand", tr("Balanced (recommended)")),
            ("nvidia", tr("Performance (always the powerful card)")),
        ):
            self._mode.addItem(label, value)
        index = self._mode.findData(self._info.mode or "on-demand")
        self._mode.setCurrentIndex(max(index, 0))
        row.addWidget(self._mode)
        apply = QPushButton(tr("Apply"), self)
        apply.clicked.connect(self._apply_mode)
        row.addWidget(apply)
        note = QLabel(tr("Takes effect after you log out or restart."), self)
        note.setObjectName("Secondary")
        row.addWidget(note)
        row.addStretch(1)
        return row

    def _apply_mode(self) -> None:
        mode = self._mode.currentData()
        if mode == self._info.mode:
            return
        self.task_run_now.emit(
            Task(
                label=tr("Change the graphics mode"),
                steps=[
                    TaskStep(
                        op_id="prime.select",
                        label=tr("Change the graphics mode"),
                        params={"mode": mode},
                    )
                ],
            )
        )

    # --- Programlar ---

    def _refresh(self) -> None:
        while self._apps_box.count():
            item = self._apps_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._apps = hybrid_gpu.list_apps(_language())
        chosen = [a for a in self._apps if a.gpu]
        if not chosen:
            empty = QLabel(
                tr("None yet. Games and 3D, video or photo editing programs benefit most."), self
            )
            empty.setObjectName("Secondary")
            empty.setWordWrap(True)
            self._apps_box.addWidget(empty)
            return
        for app in chosen:
            self._apps_box.addWidget(self._app_row(app))

    def _app_row(self, app: hybrid_gpu.DesktopApp) -> QWidget:
        row = QWidget(self)
        row.setObjectName("CardRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        ico = QLabel(row)
        ico.setPixmap(_app_icon(app.icon).pixmap(24, 24))
        ico.setFixedSize(28, 28)
        lay.addWidget(ico)
        lay.addWidget(QLabel(app.name, row), 1)
        remove = QPushButton(tr("Remove"), row)
        remove.setAccessibleName(tr("Remove {name}").format(name=app.name))
        remove.clicked.connect(lambda: self._remove(app))
        lay.addWidget(remove)
        return row

    def _add(self) -> None:
        candidates = [a for a in self._apps if not a.gpu]
        dialog = _AppPicker(candidates, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected is None:
            return
        try:
            hybrid_gpu.enable(dialog.selected, self._info.env)
        except OSError as exc:
            QMessageBox.warning(self, tr("Add a program"), str(exc))
            return
        self._refresh()

    def _remove(self, app: hybrid_gpu.DesktopApp) -> None:
        hybrid_gpu.disable(app)
        self._refresh()
