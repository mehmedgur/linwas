"""Gelişmiş ayarlar (Denetim Masası gibi ayrı sayfa; kararlar.md › Ayarlar).

Teknik ayarlar: ayrıntılı gösterim, ayrıntılı günlük, tanılama, otomatik güncelleme hizmeti,
paket sistemi bakımı, ayar ve veri klasörleri.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import diagnostics
from linwas.core import app_settings, logging_setup, user_data
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("AdvancedPage", text)


def _check_name(key: str) -> str:
    return {
        "pkexec": tr("Password prompt for administrator tasks (pkexec)"),
        "polkit": tr("Linwas permission rule (polkit)"),
        "helper": tr("Linwas system helper"),
        "timer": tr("Automatic update service"),
        "notifications": tr("Desktop notifications (gdbus)"),
        "keyring": tr("System keyring for API keys"),
        "disk": tr("Free space on the system disk (at least 2 GB)"),
        "network": tr("Internet connection"),
        "flatpak": tr("Flatpak"),
        "fwupd": tr("Firmware updates (fwupd)"),
        "timeshift": tr("System backups (Timeshift)"),
    }.get(key, key)


class _DiagWorker(QThread):
    done = Signal(object)  # (list[Check], zamanlayıcı satırı)

    def run(self) -> None:
        try:
            self.done.emit((diagnostics.run_checks(), diagnostics.timer_status()))
        except Exception:
            self.done.emit(([], ""))


class AdvancedPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = app_settings.load()
        self._worker: _DiagWorker | None = None
        self._report = ""

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)
        back = QPushButton("‹ " + tr("Settings"), content)
        back.setFlat(True)
        back.clicked.connect(lambda: self.page_requested.emit("settings"))
        outer.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        title = QLabel(tr("Advanced settings"), content)
        title.setObjectName("H1")
        outer.addWidget(title)
        intro = QLabel(
            tr(
                "Technical settings for experienced users. Everyday settings are on the "
                "Settings page."
            ),
            content,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        # Görünüm ve günlük
        card = self._card(content, tr("Details and logs"))
        details = QCheckBox(tr("Show technical details (command output) while tasks run"), card)
        details.setChecked(self._settings.show_details)
        details.toggled.connect(lambda on: self._set("show_details", on))
        card.layout.addWidget(details)
        debug = QCheckBox(tr("Write a detailed log file"), card)
        debug.setChecked(self._settings.debug_log)
        debug.toggled.connect(self._on_debug)
        card.layout.addWidget(debug)
        row = QHBoxLayout()
        logs = QPushButton(tr("Open log folder"), card)
        logs.clicked.connect(lambda: self._open_folder(user_data.log_dir()))
        row.addWidget(logs)
        cfg = QPushButton(tr("Open settings folder"), card)
        cfg.clicked.connect(lambda: self._open_folder(user_data.config_dir()))
        row.addWidget(cfg)
        data = QPushButton(tr("Open data folder"), card)
        data.clicked.connect(lambda: self._open_folder(user_data.data_dir()))
        row.addWidget(data)
        row.addStretch(1)
        card.layout.addLayout(row)
        outer.addWidget(card)

        # Tanılama
        card = self._card(content, tr("Diagnostics"))
        self._diag = QVBoxLayout()
        self._diag.setSpacing(4)
        card.layout.addLayout(self._diag)
        row = QHBoxLayout()
        run = QPushButton(tr("Check again"), card)
        run.clicked.connect(self._run_checks)
        row.addWidget(run)
        copy = QPushButton(tr("Copy results"), card)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._report))
        row.addWidget(copy)
        row.addStretch(1)
        card.layout.addLayout(row)
        outer.addWidget(card)

        # Otomatik güncelleme hizmeti
        card = self._card(content, tr("Automatic update service"))
        self._timer_lbl = QLabel("", card)
        self._timer_lbl.setWordWrap(True)
        self._timer_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.layout.addWidget(self._timer_lbl)
        run_now = QPushButton(tr("Run the automatic update now"), card)
        run_now.setToolTip(tr("Starts linwas-autoupdate.service (asks for your password)."))
        run_now.clicked.connect(self._run_autoupdate)
        card.layout.addWidget(run_now, 0, Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(card)

        # Paket sistemi bakımı
        card = self._card(content, tr("Package system maintenance"))
        row = QHBoxLayout()
        for text, op_id, tip in (
            (
                tr("Refresh package index"),
                "package.update_index",
                tr("Downloads the latest package lists (apt-get update)."),
            ),
            (
                tr("Repair broken packages"),
                "package.fix_broken",
                tr("Finishes interrupted installations and fixes missing dependencies."),
            ),
            (
                tr("Clean package cache"),
                "apt.clean",
                tr("Deletes downloaded package files to free disk space."),
            ),
        ):
            btn = QPushButton(text, card)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, o=op_id, t=text: self._run_op(o, t))
            row.addWidget(btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        outer.addWidget(card)

        outer.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    @staticmethod
    def _card(parent: QWidget, title: str) -> Card:
        card = Card(parent)
        h = QLabel(title, card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        return card

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._run_checks()

    def on_tasks_finished(self) -> None:
        if self.isVisible():
            self._run_checks()

    # --- Ayarlar ---

    def _set(self, attr: str, value: bool) -> None:
        current = app_settings.load()
        setattr(current, attr, value)
        app_settings.save(current)
        self._settings = current

    def _on_debug(self, on: bool) -> None:
        self._set("debug_log", on)
        logging_setup.setup(on)

    @staticmethod
    def _open_folder(path) -> None:  # noqa: ANN001 - Path
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # --- Tanılama ---

    def _run_checks(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = _DiagWorker(self)
        self._worker.done.connect(self._on_checks)
        self._worker.start()

    def _on_checks(self, result: tuple) -> None:
        checks, timer = result
        while self._diag.count():
            w = self._diag.takeAt(0).widget()
            if w:
                w.deleteLater()
        lines = []
        for c in checks:
            if c.ok:
                mark, color = "✓", "Success"
            elif c.optional:
                mark, color = "–", "Secondary"
            else:
                mark, color = "✗", "Warning"
            name = _check_name(c.key)
            lbl = QLabel(f"{mark} {name}" + (f" — {c.detail}" if c.detail else ""), self)
            lbl.setObjectName(color)
            lbl.setWordWrap(True)
            self._diag.addWidget(lbl)
            lines.append(f"{mark} {name}: {c.detail}")
        self._report = "\n".join(lines)
        self._timer_lbl.setText(
            tr("Timer: {status}").format(status=timer)
            if timer
            else tr("The automatic update timer is not installed (it comes with the package).")
        )

    # --- İşlemler ---

    def _run_op(self, op_id: str, label: str) -> None:
        self.task_run_now.emit(Task(label=label, steps=[TaskStep(op_id=op_id, params={})]))

    def _run_autoupdate(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Run the automatic update now"),
                steps=[
                    TaskStep(op_id="service.restart", params={"name": "linwas-autoupdate.service"})
                ],
            )
        )
