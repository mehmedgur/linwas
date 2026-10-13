"""Ana pencere — aşama 2/3: gerçek düzen, gezinme, kuyruk akışı, AI paneli."""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.desktop import Desktop
from linwas.backend.distro import SupportStatus, detect_distro, evaluate_support
from linwas.core import app_settings
from linwas.core.history import HistoryDB, HistoryEntry
from linwas.core.rollback import RollbackRecord, now_iso, records_since, undo_ops
from linwas.core.tasks import Task, TaskQueue, TaskStatus, TaskStep
from linwas.ui import icons
from linwas.ui.ai_dock import AIDock, make_content_splitter
from linwas.ui.dialogs.confirm import BackupChoice, ConfirmDialog
from linwas.ui.dialogs.progress import ProgressDialog
from linwas.ui.dialogs.result import ResultDialog
from linwas.ui.pages.ai_chat import AIChatPage
from linwas.ui.pages.all_settings import AllSettingsPage
from linwas.ui.pages.backups import BackupsPage
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.guide import GuidePage
from linwas.ui.pages.interface import DisplayPage, FontsPage, ThemePage
from linwas.ui.pages.network import NetworkPage
from linwas.ui.pages.overview import OverviewPage
from linwas.ui.pages.settings import SettingsPage
from linwas.ui.pages.software import SoftwarePage
from linwas.ui.pages.stub import StubPage
from linwas.ui.pages.troubleshoot import TroubleshootPage
from linwas.ui.pages.update_center import UpdateCenterPage
from linwas.ui.sidebar import Sidebar
from linwas.ui.status_bar import StatusBar
from linwas.ui.theme.stylesheet import build as build_qss
from linwas.ui.theme.tokens import Theme, UiStyle, colors

ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "linwas.svg"


logger = logging.getLogger("linwas.ui")


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
    "network": "Wi-Fi & Bluetooth",
    "backups": "Backups & Rollback",
    "hardware": "Hardware & Printers",
    "taskmgr": "Task Manager",
    "cleanup": "Disk Cleanup",
    "personal_backup": "Personal Backup",
    "power": "Power & Battery",
    "migrate": "Transfer",
    "all_settings": "All Settings",
    "theme": "Theme & Wallpaper",
    "fonts": "Fonts",
    "display": "Display & Scaling",
    "software": "Software",
    "troubleshoot": "Troubleshooting",
    "settings": "Settings",
}


class MainWindow(QMainWindow):
    """Linwas ana penceresi."""

    def __init__(self, background: bool = False) -> None:
        super().__init__()
        # background: oturum açılışında penceresiz başlatıldı (yalnızca bildirimler)
        self._background = background
        self.setWindowTitle("Linwas")
        self.setWindowIcon(QIcon.fromTheme("linwas", QIcon(str(ICON_PATH))))
        self.setMinimumSize(960, 620)
        # Büyük yazıya uygun açılış boyutu; küçük ekranda ekranın %90'ını aşmaz
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        width, height = 1320, 860
        if avail is not None:
            width = min(width, int(avail.width() * 0.9))
            height = min(height, int(avail.height() * 0.9))
        self.resize(width, height)

        self._queue = TaskQueue()
        self._running_tasks: list[Task] = []
        self._settings = app_settings.load()
        self._current_theme = self._resolve_theme(self._settings.theme)
        self._tray = None
        self._quitting = False

        # Stil uygula (simge renkleri de temadan)
        self._ui_style = self._resolve_style(self._settings.ui_style)
        self._accent = self._settings.accent_color
        icons.set_palette(colors(self._current_theme, self._ui_style, self._accent))
        self.setStyleSheet(build_qss(self._current_theme, self._ui_style, self._accent))
        self._sync_taskbar_palette()

        # Merkezi widget
        central = QWidget(self)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Uyarı bandı (desteklenmeyen / güvenlik desteği biten sistem)
        from PySide6.QtWidgets import QFrame, QLabel, QPushButton

        self._banner = QFrame(central)
        self._banner.setStyleSheet(
            "QFrame { background-color: #fff3cc; border-bottom: 1px solid #e0c060; }"
            " QLabel { color: #5c4300; background: transparent; }"
        )
        banner_row = QHBoxLayout(self._banner)
        banner_row.setContentsMargins(12, 6, 8, 6)
        self._banner_lbl = QLabel("", self._banner)
        self._banner_lbl.setWordWrap(True)
        banner_row.addWidget(self._banner_lbl, 1)
        banner_close = QPushButton("✕", self._banner)
        banner_close.setFixedSize(28, 28)
        banner_close.setStyleSheet("padding: 0px;")
        banner_close.setAccessibleName(tr("Close"))
        banner_close.clicked.connect(self._banner.hide)
        banner_row.addWidget(banner_close)
        self._banner.hide()
        main_layout.addWidget(self._banner)

        # İçerik alanı (sidebar + sayfalar)
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar(central)
        self._sidebar.set_style(self._ui_style)
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
        self._ai_dock.collapsed_changed.connect(lambda _c: self._check_ai_panel())
        self._ai_panel.task_add_requested.connect(self._on_ai_task_requested)
        self._ai_panel.settings_changed.connect(self._on_ai_settings_changed)
        self._ai_panel.settings_requested.connect(lambda: self.open_settings_section("ai"))
        self._ai_dock.setVisible(False)  # _check_ai_panel() görünürlüğü ayarlar

        main_layout.addLayout(content_row, 1)

        # Alt durum çubuğu
        self._status_bar = StatusBar(central)
        self._status_bar.apply_clicked.connect(self._on_apply)
        self._status_bar.detail_clicked.connect(self._show_progress)
        main_layout.addWidget(self._status_bar)

        self.setCentralWidget(central)

        # Sayfaları oluştur
        self._pages: dict[str, QWidget] = {}
        self._build_pages()

        # Başlangıç sayfası
        self._show_page("overview")

        # İlk açılış sihirbazı (pencere göründükten sonra; arka planda başlatıldıysa
        # pencere ilk açıldığında)
        if not self._settings.onboarding_done and not background:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(300, self.run_onboarding)

        # .exe/.msi çift tıklanınca Linwas açılsın (kurulu pakette, bir kez)
        if not self._settings.exe_handler_set:
            from linwas.backend.wine import set_default_exe_handler

            if set_default_exe_handler():
                self._update_settings(exe_handler_set=True)

        # Oturumla başlatma dosyası ayara uyar (varsayılan: açık); eski AI sohbetleri silinir
        from linwas.ai.chat_history import ChatHistoryDB
        from linwas.backend import autostart

        if autostart.is_enabled() != self._settings.autostart:
            autostart.set_enabled(self._settings.autostart)
        with contextlib.suppress(Exception):
            ChatHistoryDB().apply_retention(self._settings.ai_retention)

        # Arka plan bildirimleri (pencere açıkken de çalışır)
        from linwas.ui.notifier import Notifier

        self._notifier = Notifier(self)
        self._notifier.open_requested.connect(self._open_from_notification)
        self._notifier.start()
        if background:
            self._ensure_background()

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

    @staticmethod
    def _resolve_style(name: str) -> UiStyle:
        try:
            return UiStyle(name)
        except ValueError:
            return UiStyle.MACOS

    def _apply_look(self) -> None:
        icons.set_palette(colors(self._current_theme, self._ui_style, self._accent))
        self.setStyleSheet(build_qss(self._current_theme, self._ui_style, self._accent))
        self._sidebar.set_style(self._ui_style)
        self._sync_taskbar_palette()

    def _sync_taskbar_palette(self) -> None:
        """Linwas görev çubuğu eklentisi de aynı vurgu ve temayı kullanır."""
        from linwas.backend import taskbar

        def palette(theme: Theme) -> dict[str, str]:
            c = colors(theme, self._ui_style, self._accent)
            return {"panel": c.sidebar_bg, "card": c.surface, "accent": c.accent}

        # Eklenti ayarı yazılamasa da tema uygulanır
        with contextlib.suppress(Exception):
            taskbar.sync_palette(
                palette(Theme.LIGHT),
                palette(Theme.DARK),
                colors(self._current_theme, self._ui_style, self._accent).accent,
            )

    def apply_accent(self, color: str) -> None:
        """Linwas vurgu rengi ("" = varsayılan)."""
        self._accent = color
        self._apply_look()

    def apply_style(self, name: str) -> None:
        """Linwas düzeni: macOS havası ya da Windows görünümü."""
        self._ui_style = self._resolve_style(name)
        self._apply_look()

    def apply_theme(self, name: str) -> None:
        self._current_theme = self._resolve_theme(name)
        self._apply_look()

    def _update_settings(self, **changes: object) -> None:
        """Ayarları diskten yeniden okuyup yalnızca verilen alanları yazar.

        Ayarlar sayfası da aynı dosyaya yazar; eski kopyayla üzerine yazılmasın.
        """
        current = app_settings.load()
        for name, value in changes.items():
            setattr(current, name, value)
        app_settings.save(current)
        self._settings = current

    # --- Pencere kapatma, arka plan ve sistem tepsisi ---

    def _tray_wanted(self) -> bool:
        from PySide6.QtWidgets import QSystemTrayIcon

        return self._settings.keep_running and QSystemTrayIcon.isSystemTrayAvailable()

    def _ensure_background(self) -> None:
        """Pencere gizliyken uygulama çalışmayı sürdürür; tepsi varsa simge gösterilir."""
        from PySide6.QtWidgets import QApplication

        QApplication.instance().setQuitOnLastWindowClosed(False)
        if self._tray_wanted():
            self._ensure_tray()
            self._tray.show()

    def _open_from_notification(self, page_id: str) -> None:
        self._show_from_tray()
        if page_id:
            self._show_page(page_id)

    @property
    def is_background(self) -> bool:
        return self._background

    def show_window(self) -> None:
        """İkinci kez başlatılınca (tek kopya) ya da bildirimden: pencereyi öne getirir."""
        self._show_from_tray()
        if not self._settings.onboarding_done:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(300, self.run_onboarding)

    def on_instance_message(self, message: str) -> None:
        """Tek kopya iletileri: "show", "deb:<yol>", "exe:<yol>"."""
        if message == "background":
            return
        self.show_window()
        if message.startswith("deb:"):
            self.open_deb(message[4:])
        elif message.startswith("exe:"):
            self.open_exe(message[4:])

    def open_settings_section(self, key: str) -> None:
        self._show_page("settings")
        page = self._pages.get("settings")
        if page is not None and hasattr(page, "open_section"):
            page.open_section(key)

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
        self._notifier.stop()
        QApplication.instance().quit()

    def _on_close_action_changed(self, action: str) -> None:
        self._settings = app_settings.load()
        if not self._tray_wanted() and self._tray is not None:
            from PySide6.QtWidgets import QApplication

            self._tray.hide()
            self._tray = None
            QApplication.instance().setQuitOnLastWindowClosed(True)

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        self._settings = app_settings.load()
        if not self._quitting and self._settings.ask_on_close:
            choice = self._ask_close_action()
            if choice == "cancel":
                event.ignore()  # type: ignore[attr-defined]
                return
            if choice == "quit":
                event.ignore()  # type: ignore[attr-defined]
                self._quit()
                return
            self._hide_to_background()
            event.ignore()  # type: ignore[attr-defined]
            return
        if not self._quitting and self._settings.keep_running:
            self._hide_to_background()
            event.ignore()  # type: ignore[attr-defined]
            return
        super().closeEvent(event)  # type: ignore[arg-type]

    def _ask_close_action(self) -> str:
        """Küçültme / tamamen kapatma sorusu: "tray" | "quit" | "cancel".

        "Seçimimi hatırla" işaretlenirse karar ayarlara yazılır (Ayarlar › Genel'den değişir).
        """
        from PySide6.QtWidgets import QCheckBox, QMessageBox

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(tr("Close Linwas"))
        box.setText(tr("Keep Linwas running in the background, or quit it completely?"))
        box.setInformativeText(
            tr(
                "In the background Linwas keeps checking for updates and problems and notifies "
                "you. Quitting stops it until you open it again."
            )
        )
        keep = box.addButton(tr("Minimize to background"), QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton(tr("Quit completely"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        remember = QCheckBox(tr("Remember my choice"), box)
        box.setCheckBox(remember)
        box.exec()
        clicked = box.clickedButton()
        if clicked is keep:
            choice = "tray"
        elif clicked is quit_btn:
            choice = "quit"
        else:
            return "cancel"
        if remember.isChecked():
            self._update_settings(close_action=choice)
            self._on_close_action_changed(choice)
        return choice

    def _hide_to_background(self) -> None:
        # Tepsi olmasa da arka planda kalır (bildirimler); menüden yeniden açılır
        self._ensure_background()
        self.hide()
        if not self._tray_wanted():
            self._notifier.send(
                tr("Linwas is still running"),
                tr(
                    "It will notify you about updates and problems. Open it again from the "
                    "application menu, or quit it in Settings › General."
                ),
            )

    def _add_page(self, page_id: str, page: QWidget) -> None:
        """Sayfayı yığına ekler; BasePage sinyallerini bağlar."""
        self._stack.addWidget(page)
        self._pages[page_id] = page
        if isinstance(page, BasePage):
            page.task_requested.connect(self.add_task)
            page.task_run_now.connect(self._run_task_now)
            page.page_requested.connect(self._show_page)
            page.ai_help_requested.connect(self._ask_ai_about_page_error)

    def _build_pages(self) -> None:
        overview = OverviewPage(self._stack)
        overview.page_requested.connect(self._show_page)
        self._stack.addWidget(overview)
        self._pages["overview"] = overview

        # Aşama 4a + 4b + 4c: gerçek sayfalar
        # Güncelleme merkezi: Güncellemeler + Sürücüler + Firmware ("drivers" bölüme yönlenir)
        self._add_page("updates", UpdateCenterPage(self._stack))
        self._add_page("software", SoftwarePage(self._stack))
        self._add_page("backups", BackupsPage(self._stack))
        self._add_page("network", NetworkPage(self._stack))
        self._add_page("all_settings", AllSettingsPage(self._stack))
        self._add_page("theme", ThemePage(self._stack))
        self._add_page("fonts", FontsPage(self._stack))
        self._add_page("display", DisplayPage(self._stack))
        self._add_page("troubleshoot", TroubleshootPage(self._stack))
        guide = GuidePage(self._stack)
        guide.search_software.connect(self._search_software)
        self._add_page("guide", guide)
        self._sidebar.guide_search.connect(self._open_guide)
        self._sidebar.assistant_toggled.connect(self._toggle_assistant)
        # F1: yardımcı panelini aç/kapat
        assistant_key = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        assistant_key.activated.connect(self._toggle_assistant)
        settings_page = SettingsPage(self._stack)
        settings_page.theme_changed.connect(self.apply_theme)
        settings_page.style_changed.connect(self.apply_style)
        settings_page.accent_changed.connect(self.apply_accent)
        settings_page.close_action_changed.connect(self._on_close_action_changed)
        settings_page.onboarding_requested.connect(self.run_onboarding)
        settings_page.ai_settings_changed.connect(self._on_ai_settings_changed)
        settings_page.quit_requested.connect(self._quit)
        settings_page.notifications_test_requested.connect(
            lambda: self._notifier.send(
                tr("Linwas notifications work"),
                tr("This is how Linwas tells you about updates and problems."),
                "settings",
            )
        )
        self._add_page("settings", settings_page)
        # Gelişmiş ayarlar: menüde yok, Ayarlar sayfasındaki bağlantıyla açılır
        from linwas.ui.pages.advanced import AdvancedPage

        self._add_page("advanced", AdvancedPage(self._stack))
        self._ai_page = AIChatPage(self._stack)
        self._ai_page._panel.settings_changed.connect(self._on_ai_settings_changed)
        self._ai_page._panel.settings_requested.connect(lambda: self.open_settings_section("ai"))
        self._add_page("ai_chat", self._ai_page)
        # Eklenti sayfaları: yerleşik özellikler + kurulu resmi eklentiler
        self._load_plugins()

        for page_id, label in _STUB_PAGES.items():
            if page_id in self._pages:
                continue  # gerçek sayfa zaten eklendi
            stub = StubPage(label, self._stack)
            self._stack.addWidget(stub)
            self._pages[page_id] = stub

    def _show_page(self, page_id: str) -> None:
        if page_id == "appearance":  # eski "Windows görünümü" sayfası görev çubuğuna katıldı
            page_id = "taskbar"
        if page_id == "drivers":
            page_id = "updates"
            center = self._pages.get("updates")
            if isinstance(center, UpdateCenterPage):
                center.open_section("drivers")
        page = self._pages.get(page_id)
        if page:
            self._stack.setCurrentWidget(page)
            self._sidebar.set_active("settings" if page_id == "advanced" else page_id)

        # AI sayfasında yan panel gereksiz
        self._check_ai_panel()

    def _check_support(self) -> None:
        distro = detect_distro()
        status = evaluate_support(distro)
        if status in (SupportStatus.UNSUPPORTED, SupportStatus.END_OF_LIFE):
            self._banner_lbl.setText("⚠ " + support_message(status))
            self._banner.show()

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
        self._start_progress(temp)

    def _load_plugins(self) -> None:
        """Yerleşik ve kurulu eklentileri yükler, sayfalarını ekler.

        Bir eklentinin sayfası açılamazsa uygulama çalışmaya devam eder; hata
        Ayarlar › Eklentiler'de görünür.
        """
        from linwas.core.plugins.loader import PluginLoader
        from linwas.plugins.builtin import BUILTIN_PLUGINS

        loader = PluginLoader()
        for cls in BUILTIN_PLUGINS:
            loader.load_class(cls)
        loader.discover()
        self.plugin_loader = loader

        offered = set()
        for plugin in loader.plugins():
            for spec in plugin.pages():
                try:
                    page = plugin.create_page(spec.id, self._stack)
                except Exception as exc:  # bozuk eklenti uygulamayı düşürmesin
                    loader.add_error(plugin.meta.id, str(exc))
                    page = None
                if page is None or spec.id in self._pages:
                    continue
                self._add_page(spec.id, page)
                offered.add(spec.id)
                if not self._sidebar.has_item(spec.id):
                    self._sidebar.add_item(spec.id, spec.label)
        # Yerleşik eklentisi bu sistemde sayfa sunmayan menü öğeleri gizlenir (ör. Güç ve Pil)
        for cls in BUILTIN_PLUGINS:
            spec = getattr(cls, "page", None)  # sayfasız eklentiler (ör. donanım bilgisi) atlanır
            if spec is not None and spec.id not in offered:
                self._sidebar.hide_item(spec.id)

    def open_deb(self, path: str) -> None:
        """Programlar sayfasında .deb risk analizini başlatır."""
        self._show_page("software")
        self._pages["software"].open_deb(path)

    def open_exe(self, path: str) -> None:
        """Programlar sayfasında .exe/.msi analizini başlatır (Wine ile açma)."""
        self._show_page("software")
        self._pages["software"].open_exe(path)

    def _open_guide(self, text: str) -> None:
        if text:
            self._pages["guide"].set_query(text)
            self._show_page("guide")

    def _search_software(self, text: str) -> None:
        page = self._pages["software"]
        page._tabs.setCurrentIndex(0)
        page._search.setText(text)
        self._show_page("software")

    def run_onboarding(self) -> None:
        from linwas.ui.dialogs.onboarding import OnboardingWizard

        wizard = OnboardingWizard(self)
        finished = wizard.exec() == OnboardingWizard.DialogCode.Accepted
        # Atlansa da bir daha kendiliğinden açılmaz (Ayarlar'dan yeniden açılabilir)
        self._update_settings(onboarding_done=True)
        self._on_ai_settings_changed()
        if not finished:
            return
        if wizard.open_page:
            self._show_page(wizard.open_page)
        for task in wizard.tasks:
            self.add_task(task)
        if wizard.tasks:
            self._on_apply()

    def _start_progress(self, queue: TaskQueue) -> None:
        dlg = ProgressDialog(queue, self)
        dlg.done.connect(self._on_tasks_done)
        dlg.step_progress.connect(self._status_bar.set_progress)
        self._progress_dlg = dlg
        # Engellemeden aç: "Arka planda devam et" pencereyi gizler ama işlem ve pencere sürer;
        # durum çubuğundaki "Detay" aynı pencereyi geri getirir. Bitince _on_tasks_done temizler.
        dlg.show()

    def _show_progress(self) -> None:
        dlg = getattr(self, "_progress_dlg", None)
        if dlg is not None:
            dlg.show()
            dlg.raise_()

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
        self._start_progress(self._queue)

    def _on_tasks_done(self, success: bool, error: str) -> None:
        dlg = getattr(self, "_progress_dlg", None)
        self._progress_dlg = None
        if dlg is not None:
            dlg.deleteLater()
        self._status_bar.set_running(False)
        self._status_bar.update_queue(len(self._queue.pending))

        # Bu çalıştırmada helper'ın yazdığı geri alma kayıtları
        started = getattr(self, "_run_started", None)
        self._last_records: list[RollbackRecord] = records_since(started) if started else []
        has_rollback = any(undo_ops(r) for r in self._last_records)
        self._last_tasks = list(self._running_tasks)
        self._last_error = error
        labels = ", ".join(t.label for t in self._last_tasks)
        if success:
            logger.info("Görevler tamamlandı: %s", labels)
        else:
            logger.warning("Görev başarısız: %s — %s", labels, error)
        self._record_history()
        result = ResultDialog(success, error, has_rollback=has_rollback, parent=self)
        result.undo_requested.connect(self._on_undo_requested)
        result.retry_requested.connect(self._retry_failed)
        result.help_requested.connect(self._ask_ai_about_error)
        result.report_requested.connect(self._report_error)

        for page in self._pages.values():
            if isinstance(page, BasePage):
                page.on_tasks_finished()

        result.exec()

    # --- Hata akışı ---

    def _failed_tasks(self) -> list[Task]:
        return [t for t in getattr(self, "_last_tasks", []) if t.status != TaskStatus.DONE]

    def _retry_failed(self) -> None:
        failed = self._failed_tasks()
        if not failed:
            return
        # Yeni kimlikli kopyalar (aynı adımlar)
        copies = [
            Task(
                label=t.label,
                steps=[
                    TaskStep(op_id=s.op_id, params=dict(s.params), label=s.label) for s in t.steps
                ],
            )
            for t in failed
        ]
        if len(copies) == 1:
            self._run_task_now(copies[0])
            return
        for task in copies:
            self.add_task(task)
        self._on_apply()

    def _error_context(self) -> tuple[str, list[str]]:
        labels = [t.label for t in self._failed_tasks()] or [
            t.label for t in getattr(self, "_last_tasks", [])
        ]
        return getattr(self, "_last_error", ""), labels

    def _ask_ai_about_page_error(self, label: str, error: str) -> None:
        """Kuyruk dışı işlemlerin (ör. Bottles) hatası için AI'a sorma akışı."""
        self._ask_ai_about_error(error, [label])

    def _ask_ai_about_error(
        self, error: str | None = None, labels: list[str] | None = None
    ) -> None:
        from PySide6.QtWidgets import QCheckBox, QMessageBox

        from linwas.ai.manager import available_providers
        from linwas.core.sanitizer import sanitize

        # AI kapalıysa Sorun Giderme'deki hazır adımlara düşülür
        if not available_providers():
            self._show_page("troubleshoot")
            return
        self._settings = app_settings.load()  # Ayarlar sayfasında değişmiş olabilir
        if self._settings.send_errors_to_ai == "no":
            self._show_page("troubleshoot")
            return
        if self._settings.send_errors_to_ai == "ask":
            box = QMessageBox(
                QMessageBox.Icon.Question,
                tr("Send error details?"),
                tr(
                    "Send the error details to the assistant? Personal information such as "
                    "user names and addresses is hidden first."
                ),
                parent=self,
            )
            yes = box.addButton(tr("Send"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(tr("Don't send"), QMessageBox.ButtonRole.RejectRole)
            remember = QCheckBox(tr("Remember my choice"), box)
            box.setCheckBox(remember)
            box.exec()
            allowed = box.clickedButton() is yes
            if remember.isChecked():
                self._update_settings(send_errors_to_ai="yes" if allowed else "no")
            if not allowed:
                self._show_page("troubleshoot")
                return

        if error is None:
            error, labels = self._error_context()
        question = tr(
            "This Linwas task failed: {tasks}\n\nError output:\n{error}\n\n"
            "What went wrong and how can I fix it?"
        ).format(tasks=", ".join(labels or []), error=sanitize(error)[-3000:])
        self._ai_dock.expand()
        if not self._ai_dock.isVisible():
            self._check_ai_panel()
        if not self._ai_panel.ask(question):
            self._show_page("troubleshoot")

    def _report_error(self) -> None:
        from linwas import __version__
        from linwas.backend.desktop import detect_desktop, detect_session_type
        from linwas.core.error_report import build_report
        from linwas.ui.dialogs.report import ReportDialog

        error, labels = self._error_context()
        desktop = f"{detect_desktop(os.environ).value} ({detect_session_type(os.environ)})"
        report = build_report(error, labels, __version__, detect_distro().display_name, desktop)
        title = "Linwas: " + (labels[0] if labels else "error")
        ReportDialog(title, report, self).exec()

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
        self._ai_dock.setVisible(
            bool(available_providers()) and not on_ai_page and not self._ai_dock.collapsed
        )

    def _toggle_assistant(self) -> None:
        """Yardımcı panelini açar/kapatır; yapay zekâ ayarlı değilse AI sayfası açılır."""
        from linwas.ai.manager import available_providers

        on_ai_page = self._stack.currentWidget() is self._pages.get("ai_chat")
        if not available_providers() or on_ai_page:
            self._show_page("ai_chat")
            return
        self._ai_dock.toggle()

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
