"""Ana pencere — aşama 2/3: gerçek düzen, gezinme, kuyruk akışı, AI paneli."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.desktop import Desktop
from linwas.backend.distro import SupportStatus, detect_distro, evaluate_support
from linwas.backend.power import is_laptop
from linwas.core import app_settings
from linwas.core.history import HistoryDB, HistoryEntry
from linwas.core.rollback import RollbackRecord, now_iso, records_since, undo_ops
from linwas.core.tasks import Task, TaskQueue, TaskStatus, TaskStep
from linwas.ui.ai_dock import AIDock, make_content_splitter
from linwas.ui.dialogs.confirm import BackupChoice, ConfirmDialog
from linwas.ui.dialogs.progress import ProgressDialog
from linwas.ui.dialogs.result import ResultDialog
from linwas.ui.pages.ai_chat import AIChatPage
from linwas.ui.pages.all_settings import AllSettingsPage
from linwas.ui.pages.backups import BackupsPage
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.cleanup import CleanupPage
from linwas.ui.pages.drivers import DriversPage
from linwas.ui.pages.hardware import HardwarePage
from linwas.ui.pages.interface import DisplayPage, FontsPage, ThemePage, WindowsAppearancePage
from linwas.ui.pages.migrate import MigratePage
from linwas.ui.pages.network import NetworkPage
from linwas.ui.pages.overview import OverviewPage
from linwas.ui.pages.personal_backup import PersonalBackupPage
from linwas.ui.pages.power import PowerPage
from linwas.ui.pages.settings import SettingsPage
from linwas.ui.pages.software import SoftwarePage
from linwas.ui.pages.stub import StubPage
from linwas.ui.pages.taskmgr import TaskMgrPage
from linwas.ui.pages.troubleshoot import TroubleshootPage
from linwas.ui.pages.updates import UpdatesPage
from linwas.ui.sidebar import Sidebar
from linwas.ui.status_bar import StatusBar
from linwas.ui.theme.stylesheet import build as build_qss
from linwas.ui.theme.tokens import Theme

ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "linwas.svg"


def tr(text: str) -> str:
    return QCoreApplication.translate("MainWindow", text)


def support_message(status: SupportStatus) -> str:
    messages = {
        SupportStatus.SUPPORTED: tr("Supported"),
        SupportStatus.END_OF_LIFE: tr(
            "Security updates for this system have ended. We recommend upgrading."
        ),
        SupportStatus.UNTESTED_FAMILY: tr(
            "This system is in the Debian/Ubuntu family but has not been tested."
        ),
        SupportStatus.UNSUPPORTED: tr("This system is not officially supported."),
    }
    return messages[status]


def desktop_label(desktop: Desktop) -> str:
    names = {
        Desktop.GNOME: "GNOME",
        Desktop.CINNAMON: "Cinnamon",
        Desktop.XFCE: "XFCE",
        Desktop.KDE: "KDE Plasma",
        Desktop.OTHER: tr("Other"),
        Desktop.UNKNOWN: tr("Unknown"),
    }
    label = names[desktop]
    if desktop not in (Desktop.UNKNOWN,) and not desktop.supported:
        label = f"{label} — {tr('limited support')}"
    return label


# Sayfa ID → (başlık, StubPage) çiftleri; Overview ayrı işlenir
_STUB_PAGES = {
    "ai_chat": "AI Question",
    "updates": "Updates",
    "drivers": "Drivers",
    "network": "Wi-Fi & Bluetooth",
    "backups": "Backups & Rollback",
    "hardware": "Hardware & Printers",
    "taskmgr": "Task Manager",
    "cleanup": "Disk Cleanup",
    "personal_backup": "Personal Backup",
    "power": "Power & Battery",
    "migrate": "Import from Windows",
    "all_settings": "All Settings",
    "appearance": "Windows Appearance",
    "theme": "Theme & Wallpaper",
    "fonts": "Fonts",
    "display": "Display & Scaling",
    "software": "Software",
    "troubleshoot": "Troubleshooting",
    "settings": "Settings",
}


class MainWindow(QMainWindow):
    """Linwas ana penceresi."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Linwas")
        self.setWindowIcon(QIcon.fromTheme("linwas", QIcon(str(ICON_PATH))))
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        self._queue = TaskQueue()
        self._running_tasks: list[Task] = []
        self._settings = app_settings.load()
        self._current_theme = self._resolve_theme(self._settings.theme)
        self._tray = None
        self._quitting = False

        # Stil uygula
        self.setStyleSheet(build_qss(self._current_theme))

        # Merkezi widget
        central = QWidget(self)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # İçerik alanı (sidebar + sayfalar)
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar(central)
        self._sidebar.page_requested.connect(self._show_page)
        content_row.addWidget(self._sidebar)

        # Sayfa yığını ve sağda AI yardımcısı; aradaki ayırıcı sürüklenerek
        # panel genişletilip daraltılabilir
        splitter = make_content_splitter(central)
        self._stack = QStackedWidget(splitter)
        splitter.addWidget(self._stack)
        self._ai_dock = AIDock(splitter, splitter)
        splitter.addWidget(self._ai_dock)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        content_row.addWidget(splitter, 1)

        # AI yardımcı paneli (sağlayıcı yoksa gizli)
        self._ai_panel = self._ai_dock.panel
        self._ai_panel.task_add_requested.connect(self._on_ai_task_requested)
        self._ai_panel.settings_changed.connect(self._on_ai_settings_changed)
        self._ai_dock.setVisible(False)  # _check_ai_panel() görünürlüğü ayarlar

        main_layout.addLayout(content_row, 1)

        # Alt durum çubuğu
        self._status_bar = StatusBar(central)
        self._status_bar.apply_clicked.connect(self._on_apply)
        main_layout.addWidget(self._status_bar)

        self.setCentralWidget(central)

        # Sayfaları oluştur
        self._pages: dict[str, QWidget] = {}
        self._build_pages()

        # Başlangıç sayfası
        self._show_page("overview")

        # Sistem uyarısı (EOL veya desteklenmiyor)
        self._check_support()
        # AI panel görünürlüğü
        self._check_ai_panel()

    @staticmethod
    def _resolve_theme(name: str) -> Theme:
        """Ayardaki tema adını uygulanacak temaya çevirir ("system" → masaüstünün teması)."""
        fixed = {"light": Theme.LIGHT, "dark": Theme.DARK, "high_contrast": Theme.HIGH_CONTRAST}
        if name in fixed:
            return fixed[name]
        if "dark" in os.environ.get("GTK_THEME", "").lower():
            return Theme.DARK
        from linwas.backend import appearance
        from linwas.backend.desktop import detect_desktop

        return Theme.DARK if appearance.is_dark(detect_desktop(os.environ).value) else Theme.LIGHT

    def apply_theme(self, name: str) -> None:
        self._current_theme = self._resolve_theme(name)
        self.setStyleSheet(build_qss(self._current_theme))

    # --- Pencere kapatma ve sistem tepsisi ---

    def _tray_wanted(self) -> bool:
        from PySide6.QtWidgets import QSystemTrayIcon

        action = self._settings.close_action
        if action == "quit":
            return False
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _ensure_tray(self) -> None:
        from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

        if self._tray is not None:
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("Linwas")
        menu = QMenu(self)
        menu.addAction(tr("Open Linwas"), self._show_from_tray)
        menu.addAction(tr("Quit"), self._quit)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda _reason: self._show_from_tray())
        self._tray = tray
        # Pencere gizlenince uygulama kapanmasın; çıkış menüden yapılır
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        from PySide6.QtWidgets import QApplication

        self._quitting = True
        if self._tray is not None:
            self._tray.hide()
        QApplication.instance().quit()

    def _on_close_action_changed(self, action: str) -> None:
        self._settings.close_action = action
        if not self._tray_wanted() and self._tray is not None:
            from PySide6.QtWidgets import QApplication

            self._tray.hide()
            self._tray = None
            QApplication.instance().setQuitOnLastWindowClosed(True)

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        if not self._quitting and self._tray_wanted():
            self._ensure_tray()
            self._tray.show()
            self.hide()
            event.ignore()  # type: ignore[attr-defined]
            return
        super().closeEvent(event)  # type: ignore[arg-type]

    def _add_page(self, page_id: str, page: QWidget) -> None:
        """Sayfayı yığına ekler; BasePage sinyallerini bağlar."""
        self._stack.addWidget(page)
        self._pages[page_id] = page
        if isinstance(page, BasePage):
            page.task_requested.connect(self.add_task)
            page.task_run_now.connect(self._run_task_now)
            page.page_requested.connect(self._show_page)

    def _build_pages(self) -> None:
        overview = OverviewPage(self._stack)
        overview.page_requested.connect(self._show_page)
        self._stack.addWidget(overview)
        self._pages["overview"] = overview

        # Aşama 4a + 4b + 4c: gerçek sayfalar
        self._add_page("updates", UpdatesPage(self._stack))
        self._add_page("drivers", DriversPage(self._stack))
        self._add_page("software", SoftwarePage(self._stack))
        self._add_page("migrate", MigratePage(self._stack))
        self._add_page("taskmgr", TaskMgrPage(self._stack))
        self._add_page("cleanup", CleanupPage(self._stack))
        self._add_page("backups", BackupsPage(self._stack))
        self._add_page("network", NetworkPage(self._stack))
        self._add_page("all_settings", AllSettingsPage(self._stack))
        self._add_page("appearance", WindowsAppearancePage(self._stack))
        self._add_page("theme", ThemePage(self._stack))
        self._add_page("fonts", FontsPage(self._stack))
        self._add_page("display", DisplayPage(self._stack))
        self._add_page("troubleshoot", TroubleshootPage(self._stack))
        settings_page = SettingsPage(self._stack)
        settings_page.theme_changed.connect(self.apply_theme)
        settings_page.close_action_changed.connect(self._on_close_action_changed)
        self._add_page("settings", settings_page)
        self._ai_page = AIChatPage(self._stack)
        self._ai_page._panel.settings_changed.connect(self._on_ai_settings_changed)
        self._add_page("ai_chat", self._ai_page)
        self._add_page("hardware", HardwarePage(self._stack))
        self._add_page("personal_backup", PersonalBackupPage(self._stack))
        # Güç ve pil yalnızca dizüstünde (karar belgesi)
        if is_laptop():
            self._add_page("power", PowerPage(self._stack))
        else:
            self._sidebar.hide_item("power")

        for page_id, label in _STUB_PAGES.items():
            if page_id in self._pages:
                continue  # gerçek sayfa zaten eklendi
            stub = StubPage(label, self._stack)
            self._stack.addWidget(stub)
            self._pages[page_id] = stub

    def _show_page(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        if page:
            self._stack.setCurrentWidget(page)
            self._sidebar.set_active(page_id)

        # AI sayfasında yan panel gereksiz
        self._check_ai_panel()

    def _check_support(self) -> None:
        distro = detect_distro()
        status = evaluate_support(distro)
        if status in (SupportStatus.UNSUPPORTED, SupportStatus.END_OF_LIFE):
            msg = support_message(status)
            self._status_bar.update_queue(0)
            # TODO: Aşama 4'te bildirim banner'ı eklenecek
            _ = msg

    # --- Kuyruk akışı ---

    def _run_task_now(self, task: Task) -> None:
        """Görevi paylaşılan kuyruğa dokunmadan hemen çalıştırır.

        Geçici kuyruk kullanır — her basışta yalnızca bir kez çalışır.
        """
        from linwas.core.tasks import TaskQueue as _TQ

        temp = _TQ()
        temp.add(task)

        confirm = ConfirmDialog([task], self)
        if confirm.exec() != ConfirmDialog.DialogCode.Accepted:
            return

        backup_choice = confirm.backup_choice
        if backup_choice == BackupChoice.TIMESHIFT:
            snap = Task(
                label=tr("Full system backup (Timeshift)"),
                steps=[TaskStep(op_id="snapshot.timeshift_create", params={})],
            )
            temp._tasks.insert(0, snap)

        self._status_bar.set_running(True)
        self._run_started = now_iso()
        self._running_tasks = temp.all_tasks
        progress_dlg = ProgressDialog(temp, self)
        progress_dlg.done.connect(self._on_tasks_done)
        progress_dlg.exec()

    def add_task(self, task: Task) -> None:
        """Kuyruğa görev ekler ve durum çubuğunu günceller."""
        self._queue.add(task)
        self._status_bar.update_queue(len(self._queue.pending))

    def _on_apply(self) -> None:
        tasks = self._queue.pending
        if not tasks:
            return

        confirm = ConfirmDialog(tasks, self)
        if confirm.exec() != ConfirmDialog.DialogCode.Accepted:
            return

        backup_choice = confirm.backup_choice

        # Timeshift yedek görevi kuyruğa başa ekle
        if backup_choice == BackupChoice.TIMESHIFT:
            snapshot_task = Task(
                label=tr("Full system backup (Timeshift)"),
                steps=[TaskStep(op_id="snapshot.timeshift_create", params={})],
            )
            self._queue._tasks.insert(0, snapshot_task)

        self._status_bar.set_running(True)
        self._run_started = now_iso()
        self._running_tasks = list(self._queue.pending)
        progress_dlg = ProgressDialog(self._queue, self)
        progress_dlg.done.connect(self._on_tasks_done)
        progress_dlg.exec()

    def _on_tasks_done(self, success: bool, error: str) -> None:
        self._status_bar.set_running(False)
        self._status_bar.update_queue(len(self._queue.pending))

        # Bu çalıştırmada helper'ın yazdığı geri alma kayıtları
        started = getattr(self, "_run_started", None)
        self._last_records: list[RollbackRecord] = records_since(started) if started else []
        has_rollback = any(undo_ops(r) for r in self._last_records)
        self._record_history()
        result = ResultDialog(success, error, has_rollback=has_rollback, parent=self)
        result.undo_requested.connect(self._on_undo_requested)

        for page in self._pages.values():
            if isinstance(page, BasePage):
                page.on_tasks_finished()

        result.exec()

    def _record_history(self) -> None:
        """Çalışan görevleri işlem geçmişine yazar (Ayarlar › İşlem geçmişi)."""
        rollback_id = self._last_records[0].id if self._last_records else None
        try:
            db = HistoryDB()
            for task in self._running_tasks:
                db.add(
                    HistoryEntry(
                        task_label=task.label,
                        step_labels=[s.label for s in task.steps],
                        result="success" if task.status == TaskStatus.DONE else "failure",
                        rollback_id=rollback_id,
                    )
                )
        except Exception:
            pass  # geçmiş yazılamazsa işlem sonucu yine gösterilir
        self._running_tasks = []

    def _on_undo_requested(self) -> None:
        steps = [
            TaskStep(op_id=op_id, params=params)
            for record in self._last_records
            for op_id, params in undo_ops(record)
        ]
        if not steps:
            return
        self._run_task_now(Task(label=tr("Undo changes"), steps=steps))

    def _check_ai_panel(self) -> None:
        from linwas.ai.manager import available_providers

        on_ai_page = self._stack.currentWidget() is self._pages.get("ai_chat")
        self._ai_dock.setVisible(bool(available_providers()) and not on_ai_page)

    def _on_ai_settings_changed(self) -> None:
        """Anahtarlar bir panelde değişince diğerini de günceller."""
        self._ai_panel.refresh()
        self._ai_page._panel.refresh()
        self._check_ai_panel()

    def _on_ai_task_requested(self, op_id: str, params: dict) -> None:
        """AI panelinden gelen görev önerisini kuyruğa ekler."""
        from linwas.core.whitelist import ValidationError

        try:
            step = TaskStep(op_id=op_id, params={str(k): str(v) for k, v in params.items()})
            task = Task(label=step.label, steps=[step])
            self.add_task(task)
        except ValidationError as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Linwas", str(exc))
