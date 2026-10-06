"""Güncellemeler sayfası."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.distro import detect_distro
from linwas.backend.installed_apps import AppUpdate, pending_app_updates
from linwas.backend.packages import UpgradablePackage, apt_cache_age_hours, list_upgradable
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("UpdatesPage", text)


class _CheckWorker(QThread):
    done = Signal(list)  # list[UpgradablePackage]
    error = Signal(str)

    def run(self) -> None:
        try:
            self.done.emit(list_upgradable())
        except Exception as exc:
            self.error.emit(str(exc))


class _AppWorker(QThread):
    done = Signal(list)  # list[AppUpdate]

    def run(self) -> None:
        try:
            # Linux Mint'te Snap gösterilmez (karar belgesi)
            self.done.emit(pending_app_updates(detect_distro().id != "linuxmint"))
        except Exception:
            self.done.emit([])


class _PackageRow(QWidget):
    def __init__(self, pkg: UpgradablePackage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)

        name_lbl = QLabel(pkg.name, self)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(name_lbl)

        ver_lbl = QLabel(f"{pkg.installed_version} → {pkg.available_version}", self)
        ver_lbl.setObjectName("Secondary")
        row.addWidget(ver_lbl)

        if pkg.is_security:
            badge = QLabel(tr("Security"), self)
            badge.setStyleSheet(
                "background-color: #c42b1c; color: white; border-radius: 4px;"
                " padding: 1px 6px; font-size: 11px;"
            )
            row.addWidget(badge)


class UpdatesPage(BasePage):
    """Güncellemeler sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._packages: list[UpgradablePackage] = []
        self._worker: _CheckWorker | None = None
        self._app_worker: _AppWorker | None = None
        self._app_updates: list[AppUpdate] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        # Başlık
        title = QLabel(tr("Updates"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Cache yaşı + Refresh index butonu
        cache_row = QHBoxLayout()
        self._cache_lbl = QLabel("", content)
        self._cache_lbl.setObjectName("Secondary")
        cache_row.addWidget(self._cache_lbl)
        cache_row.addStretch(1)
        self._refresh_index_btn = QPushButton(tr("Refresh index"), content)
        self._refresh_index_btn.setToolTip(
            tr("Runs apt-get update to fetch latest package information (requires password)")
        )
        self._refresh_index_btn.clicked.connect(self._queue_refresh_index)
        cache_row.addWidget(self._refresh_index_btn)
        self._check_btn = QPushButton(tr("Check now"), content)
        self._check_btn.clicked.connect(self._check)
        cache_row.addWidget(self._check_btn)
        outer.addLayout(cache_row)

        sep0 = QFrame(content)
        sep0.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep0)

        # Özet kartı
        self._summary_card = Card(content)
        self._summary_lbl = QLabel(tr("Checking for updates…"), self._summary_card)
        self._summary_lbl.setObjectName("H2")
        self._summary_card.layout.addWidget(self._summary_lbl)
        self._security_lbl = QLabel("", self._summary_card)
        self._security_lbl.setObjectName("Secondary")
        self._security_lbl.setVisible(False)
        self._summary_card.layout.addWidget(self._security_lbl)
        outer.addWidget(self._summary_card)

        # Tümünü güncelle
        self._update_btn = QPushButton(tr("Update all packages"), content)
        self._update_btn.setProperty("primary", True)
        self._update_btn.setEnabled(False)
        self._update_btn.clicked.connect(self._queue_update)
        outer.addWidget(self._update_btn)

        # Paket listesi
        self._list_card = Card(content)
        self._list_label = QLabel(tr("Available updates"), self._list_card)
        self._list_label.setObjectName("H2")
        self._list_card.layout.addWidget(self._list_label)

        sep = QFrame(self._list_card)
        sep.setFrameShape(QFrame.Shape.HLine)
        self._list_card.layout.addWidget(sep)

        self._pkg_container = QWidget(self._list_card)
        self._pkg_layout = QVBoxLayout(self._pkg_container)
        self._pkg_layout.setContentsMargins(0, 0, 0, 0)
        self._pkg_layout.setSpacing(0)
        self._list_card.layout.addWidget(self._pkg_container)
        self._list_card.setVisible(False)
        outer.addWidget(self._list_card)

        # Flatpak ve Snap uygulamaları
        self._apps_card = Card(content)
        h = QLabel(tr("App updates (Flatpak and Snap)"), self._apps_card)
        h.setObjectName("H2")
        self._apps_card.layout.addWidget(h)
        self._apps_lbl = QLabel(tr("Checking…"), self._apps_card)
        self._apps_lbl.setWordWrap(True)
        self._apps_card.layout.addWidget(self._apps_lbl)
        self._apps_btn = QPushButton(tr("Update apps"), self._apps_card)
        self._apps_btn.setProperty("primary", True)
        self._apps_btn.setEnabled(False)
        self._apps_btn.clicked.connect(self._queue_app_updates)
        self._apps_card.layout.addWidget(self._apps_btn)
        outer.addWidget(self._apps_card)

        outer.addStretch(1)
        scroll.setWidget(content)

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

        self._update_cache_label()
        self._check()

    def _update_cache_label(self) -> None:
        age = apt_cache_age_hours()
        if age is None:
            self._cache_lbl.setText(tr("Package index: unknown"))
        elif age < 1:
            self._cache_lbl.setText(tr("Package index: up to date"))
        elif age < 24:
            self._cache_lbl.setText(tr("Package index: {h}h old").format(h=int(age)))
        else:
            days = int(age / 24)
            self._cache_lbl.setText(
                tr("Package index: {d} day(s) old — consider refreshing").format(d=days)
            )
            self._cache_lbl.setStyleSheet("color: #9d5d00;")

    def _check(self) -> None:
        self._check_btn.setEnabled(False)
        self._summary_lbl.setText(tr("Checking for updates…"))
        self._update_btn.setEnabled(False)
        self._list_card.setVisible(False)

        self._worker = _CheckWorker()
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(lambda: self._check_btn.setEnabled(True))
        self._worker.start()
        self._check_apps()

    def _on_error(self, msg: str) -> None:
        self._summary_lbl.setText(tr("Check failed: {error}").format(error=msg))

    def _on_done(self, packages: list) -> None:
        self._packages = packages
        total = len(packages)
        security = sum(1 for p in packages if p.is_security)

        if total == 0:
            self._summary_lbl.setText(tr("Your system is up to date"))
            self._security_lbl.setVisible(False)
            self._update_btn.setEnabled(False)
            self._list_card.setVisible(False)
        else:
            self._summary_lbl.setText(tr("{n} update(s) available").format(n=total))
            if security:
                self._security_lbl.setText(tr("{n} security update(s) included").format(n=security))
                self._security_lbl.setVisible(True)
            else:
                self._security_lbl.setVisible(False)
            self._update_btn.setEnabled(True)
            self._build_list(packages)
            self._list_card.setVisible(True)

    def _build_list(self, packages: list[UpgradablePackage]) -> None:
        while self._pkg_layout.count():
            item = self._pkg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        ordered = sorted(packages, key=lambda p: (not p.is_security, p.name))
        for pkg in ordered:
            row = _PackageRow(pkg, self._pkg_container)
            self._pkg_layout.addWidget(row)
            sep = QFrame(self._pkg_container)
            sep.setFrameShape(QFrame.Shape.HLine)
            self._pkg_layout.addWidget(sep)

    def _check_apps(self) -> None:
        if self._app_worker and self._app_worker.isRunning():
            return
        self._apps_lbl.setText(tr("Checking…"))
        self._apps_btn.setEnabled(False)
        self._app_worker = _AppWorker()
        self._app_worker.done.connect(self._on_apps)
        self._app_worker.start()

    def _on_apps(self, updates: list) -> None:
        self._app_updates = updates
        if not updates:
            self._apps_lbl.setText(tr("All apps are up to date."))
            return
        names = ", ".join(
            f"{u.name} ({'Flatpak' if u.source == 'flatpak' else 'Snap'})" for u in updates
        )
        self._apps_lbl.setText(tr("{n} app update(s): {names}").format(n=len(updates), names=names))
        self._apps_btn.setEnabled(True)

    def _queue_app_updates(self) -> None:
        steps = []
        if any(u.source == "flatpak" for u in self._app_updates):
            steps.append(TaskStep(op_id="flatpak.update_all", params={}))
        if any(u.source == "snap" for u in self._app_updates):
            steps.append(TaskStep(op_id="snap.refresh_all", params={}))
        if steps:
            self.task_requested.emit(Task(label=tr("Update apps"), steps=steps))

    def on_tasks_finished(self) -> None:
        self._check_apps()

    def _queue_update(self) -> None:
        task = Task(
            label=tr("Update all packages"),
            steps=[
                TaskStep(op_id="package.update_index", params={}),
                TaskStep(op_id="package.update_all", params={}),
            ],
        )
        self.task_requested.emit(task)

    def _queue_refresh_index(self) -> None:
        task = Task(
            label=tr("Refresh package index"),
            steps=[TaskStep(op_id="package.update_index", params={})],
        )
        # Hemen çalıştır — kullanıcı ayrıca Uygula'ya basmak zorunda kalmasın
        self.task_run_now.emit(task)
