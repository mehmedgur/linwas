# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Program › Kurulu programlar sekmesi (Windows'taki "Programlar ve Özellikler")."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QDate, QLocale, Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.distro import detect_distro
from linwas.backend.installed_apps import (
    SOURCE_ORDER,
    InstalledApp,
    filter_apps,
    list_installed_apps,
    sort_apps,
)
from linwas.core.tasks import Task
from linwas.ui.dialogs.remove_app import RemovalFlow, RemovalRequest, build_update_task


def tr(text: str) -> str:
    return QCoreApplication.translate("InstalledAppsView", text)


def source_badge_text(source: str) -> str:
    return {
        "apt": "APT",
        "flatpak": "Flatpak",
        "snap": "Snap",
        "third-party": tr("3rd party"),
    }.get(source, source)


_BADGE_COLORS = {
    "apt": ("#0067c0", "#e3f2fd"),
    "flatpak": ("#5c35cc", "#ede7f6"),
    "snap": ("#a33e00", "#fde9dc"),
    "third-party": ("#9d5d00", "#fff3cc"),
}


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    return QLocale().formattedDataSize(size_bytes, 1, QLocale.DataSizeFormat.DataSizeSIFormat)


def format_date(day: date | None) -> str:
    if day is None:
        return "—"
    return QLocale().toString(QDate(day.year, day.month, day.day), QLocale.FormatType.ShortFormat)


def _icon(name: str) -> QIcon:
    if name.startswith("/"):
        return QIcon(name) if Path(name).exists() else QIcon.fromTheme("application-x-executable")
    icon = QIcon.fromTheme(name) if name else QIcon()
    return icon if not icon.isNull() else QIcon.fromTheme("application-x-executable")


class _ListWorker(QThread):
    done = Signal(list)

    def run(self) -> None:
        # Linux Mint'te Snap gösterilmez (karar belgesi)
        include_snap = detect_distro().id != "linuxmint"
        try:
            apps = list_installed_apps(include_snap=include_snap)
        except Exception:
            apps = []
        self.done.emit(apps)


class _AppRow(QWidget):
    remove_clicked = Signal(object)  # InstalledApp
    update_clicked = Signal(object)

    def __init__(self, app: InstalledApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(10)

        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(_icon(app.icon).pixmap(32, 32))
        icon_lbl.setFixedSize(32, 32)
        row.addWidget(icon_lbl)

        info = QVBoxLayout()
        info.setSpacing(0)
        name_lbl = QLabel(app.name, self)
        name_lbl.setStyleSheet("font-weight: bold;")
        info.addWidget(name_lbl)
        installed_on = (
            tr("Installed on {date}").format(date=format_date(app.installed_on))
            if app.installed_on
            else tr("Install date unknown")
        )
        sub = QLabel(f"{app.id} · {installed_on}", self)
        sub.setObjectName("Secondary")
        info.addWidget(sub)
        row.addLayout(info, 1)

        fg, bg = _BADGE_COLORS.get(app.source, ("#555", "#eee"))
        badge = QLabel(source_badge_text(app.source), self)
        badge.setStyleSheet(
            f"background-color:{bg}; color:{fg}; border-radius:4px;"
            " padding:1px 7px; font-size: 13px; font-weight:bold;"
        )
        row.addWidget(badge)

        size_lbl = QLabel(format_size(app.size_bytes), self)
        size_lbl.setObjectName("Secondary")
        size_lbl.setMinimumWidth(70)
        size_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        size_lbl.setToolTip(tr("Space used"))
        row.addWidget(size_lbl)

        if app.update_available:
            upd = QPushButton(tr("Update"), self)
            upd.setProperty("primary", True)
            upd.setAccessibleName(tr("Update {name}").format(name=app.name))
            upd.clicked.connect(lambda: self.update_clicked.emit(self.app))
            row.addWidget(upd)

        remove = QPushButton(tr("Remove"), self)
        remove.setAccessibleName(tr("Remove {name}").format(name=app.name))
        if app.user_install:
            remove.setEnabled(False)
            remove.setToolTip(
                tr("Installed only for your user account; Linwas can't remove it yet.")
            )
        remove.clicked.connect(lambda: self.remove_clicked.emit(self.app))
        row.addWidget(remove)


class InstalledAppsView(QWidget):
    """Kurulu programlar: arama, sıralama, güncelle ve kaldır."""

    task_run_now = Signal(Task)
    apps_loaded = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apps: list[InstalledApp] = []
        self._worker: _ListWorker | None = None
        self._loaded = False
        self._removal = RemovalFlow(self)
        self._removal.task_ready.connect(self.task_run_now)
        self._removal.busy_changed.connect(self._on_removal_busy)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)

        tools = QHBoxLayout()
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText(tr("Search installed programs…"))
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._render)
        tools.addWidget(self._filter, 1)

        source_lbl = QLabel(tr("Source:"), self)
        tools.addWidget(source_lbl)
        self._source = QComboBox(self)
        self._source.addItem(tr("All"), "")
        self._source.currentIndexChanged.connect(self._render)
        source_lbl.setBuddy(self._source)
        tools.addWidget(self._source)

        sort_lbl = QLabel(tr("Sort by:"), self)
        tools.addWidget(sort_lbl)
        self._sort = QComboBox(self)
        self._sort.addItem(tr("Name (A–Z)"), "name")
        self._sort.addItem(tr("Source (APT, Flatpak, Snap…)"), "source")
        self._sort.addItem(tr("Size (largest first)"), "size")
        self._sort.addItem(tr("Install date (newest first)"), "newest")
        self._sort.addItem(tr("Install date (oldest first)"), "oldest")
        self._sort.currentIndexChanged.connect(self._render)
        sort_lbl.setBuddy(self._sort)
        tools.addWidget(self._sort)

        self._refresh_btn = QPushButton(tr("Refresh"), self)
        self._refresh_btn.clicked.connect(self.reload)
        tools.addWidget(self._refresh_btn)
        outer.addLayout(tools)

        self._status = QLabel(tr("Loading installed programs…"), self)
        self._status.setObjectName("Secondary")
        outer.addWidget(self._status)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)
        scroll.setWidget(self._list_widget)
        outer.addWidget(scroll, 1)

    # --- Yükleme ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if not self._loaded:
            self.reload()

    def mark_stale(self) -> None:
        """Sekme bir sonraki gösterilişinde yeniden yüklensin."""
        self._loaded = False

    def reload(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._loaded = True
        self._refresh_btn.setEnabled(False)
        self._status.setText(tr("Loading installed programs…"))
        self._worker = _ListWorker()
        self._worker.done.connect(self._on_loaded)
        self._worker.start()

    def _on_loaded(self, apps: list[InstalledApp]) -> None:
        self._apps = apps
        self._refresh_btn.setEnabled(True)
        self._fill_sources()
        self._render()
        self.apps_loaded.emit()

    # --- Görüntüleme ---

    @property
    def apps(self) -> list[InstalledApp]:
        return list(self._apps)

    @property
    def is_loaded(self) -> bool:
        return self._loaded and not (self._worker and self._worker.isRunning())

    def _sorted_filtered(self) -> list[InstalledApp]:
        apps = filter_apps(self._apps, self._source.currentData() or "", self._filter.text())
        return sort_apps(apps, self._sort.currentData() or "name")

    def _fill_sources(self) -> None:
        """Kaynak filtresine yalnızca listede bulunan kaynakları koyar."""
        current = self._source.currentData()
        present = {a.source for a in self._apps}
        self._source.blockSignals(True)
        self._source.clear()
        self._source.addItem(tr("All"), "")
        for src in SOURCE_ORDER:
            if src in present:
                self._source.addItem(source_badge_text(src), src)
        index = self._source.findData(current)
        self._source.setCurrentIndex(max(index, 0))
        self._source.blockSignals(False)

    def _update_status(self, shown: list[InstalledApp]) -> None:
        if not self._apps:
            self._status.setText(tr("No installed programs found."))
            return
        text = tr("{n} program(s)").format(n=len(shown))
        updates = sum(1 for a in shown if a.update_available)
        if updates:
            text += " · " + tr("{n} update(s) available").format(n=updates)
        self._status.setText(text)

    def _clear(self) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _render(self) -> None:
        if not self._loaded or (self._worker and self._worker.isRunning()):
            return
        self._clear()
        apps = self._sorted_filtered()
        self._update_status(apps)

        pos = 0
        for app in apps:
            row = _AppRow(app, self._list_widget)
            row.remove_clicked.connect(self._on_remove)
            row.update_clicked.connect(self._on_update)
            self._list_layout.insertWidget(pos, row)
            sep = QFrame(self._list_widget)
            sep.setFrameShape(QFrame.Shape.HLine)
            self._list_layout.insertWidget(pos + 1, sep)
            pos += 2

    # --- İşlemler ---

    def _on_remove(self, app: InstalledApp) -> None:
        self._removal.start(
            RemovalRequest(
                id=app.id, name=app.name, source=app.source, preinstalled=app.preinstalled
            )
        )

    def _on_update(self, app: InstalledApp) -> None:
        self.task_run_now.emit(build_update_task(app.id, app.name, app.source))

    def _on_removal_busy(self, busy: bool) -> None:
        self._list_widget.setEnabled(not busy)
        if busy:
            self._status.setText(tr("Checking what will be removed…"))
        else:
            self._update_status(self._sorted_filtered())
