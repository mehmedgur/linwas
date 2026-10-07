"""Linwas'ın kendi ayarları: solda kategoriler, üstte arama, sağda seçili bölüm.

Değişiklikler anında kaydedilir ve uygulanır (kararlar.md › Ayarlar). Teknik ayarlar burada
değil, ayrı "Gelişmiş" sayfasında olacak.
"""

from __future__ import annotations

import contextlib
from datetime import datetime

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import autostart, notify
from linwas.core import app_settings
from linwas.core.history import HistoryDB
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.settings_ai import AISettingsSection
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("SettingsPage", text)


def _when(iso: str) -> str:
    try:
        ts = int(datetime.fromisoformat(iso).timestamp())
    except ValueError:
        return iso
    return QLocale().toString(QDateTime.fromSecsSinceEpoch(ts), QLocale.FormatType.ShortFormat)


class _Section(QWidget):
    """Sağdaki bölüm: başlık + kartlar. Arama için içindeki metinleri toplar."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(20, 0, 8, 20)
        self.body.setSpacing(12)
        heading = QLabel(title, content)
        heading.setObjectName("H1")
        self.body.addWidget(heading)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        self._content = content

    def card(self, title: str) -> Card:
        card = Card(self._content)
        h = QLabel(title, card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        self.body.addWidget(card)
        return card

    def finish(self) -> None:
        self.body.addStretch(1)

    def search_text(self) -> str:
        """Bölümdeki bütün etiket, düğme ve seçim metinleri (küçük harf)."""
        parts = [self.title]
        for w in self._content.findChildren(QWidget):
            if isinstance(w, (QLabel, QPushButton, QCheckBox)):
                parts.append(w.text())
            elif isinstance(w, QComboBox):
                parts += [w.itemText(i) for i in range(w.count())]
        return " ".join(parts).casefold()


class SettingsPage(BasePage):
    theme_changed = Signal(str)  # app_settings.THEMES değerlerinden biri
    close_action_changed = Signal(str)
    consent_changed = Signal(str)
    onboarding_requested = Signal()
    ai_settings_changed = Signal()
    quit_requested = Signal()
    notifications_test_requested = Signal()

    SECTIONS = (
        "general",
        "appearance",
        "ai",
        "notifications",
        "privacy",
        "backup",
        "plugins",
        "about",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = app_settings.load()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 0)
        outer.setSpacing(12)
        head = QHBoxLayout()
        title = QLabel(tr("Settings"), self)
        title.setObjectName("H1")
        head.addWidget(title)
        head.addStretch(1)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(tr("Search settings…"))
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(260)
        self._search.textChanged.connect(self._filter)
        head.addWidget(self._search)
        outer.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(0)
        nav_box = QVBoxLayout()
        nav_box.setContentsMargins(0, 0, 0, 12)
        self._nav = QListWidget(self)
        self._nav.setObjectName("SettingsNav")
        self._nav.setFixedWidth(210)
        self._nav.setFrameShape(QFrame.Shape.NoFrame)
        nav_box.addWidget(self._nav, 1)
        # Teknik ayarlar ayrı sayfada (Denetim Masası gibi; kararlar.md › Ayarlar)
        advanced = QPushButton(tr("Advanced settings") + " ›", self)
        advanced.setFlat(True)
        advanced.setToolTip(tr("Technical settings, diagnostics and logs"))
        advanced.clicked.connect(lambda: self.page_requested.emit("advanced"))
        nav_box.addWidget(advanced, 0, Qt.AlignmentFlag.AlignLeft)
        body.addLayout(nav_box)
        self._stack = QStackedWidget(self)
        body.addWidget(self._stack, 1)
        outer.addLayout(body, 1)

        self._sections: dict[str, _Section] = {}
        self._nav.currentRowChanged.connect(self._on_nav)
        self._build_sections()

    def _build_sections(self, current: str = "general") -> None:
        builders = {
            "general": (tr("General"), self._build_general),
            "appearance": (tr("Appearance"), self._build_appearance),
            "ai": (tr("AI assistant"), self._build_ai),
            "notifications": (tr("Notifications and startup"), self._build_notifications),
            "privacy": (tr("Privacy and data"), self._build_privacy),
            "backup": (tr("Backup and reset"), self._build_backup),
            "plugins": (tr("Plugins"), self._build_plugins),
            "about": (tr("About"), self._build_about),
        }
        for key in self.SECTIONS:
            text, build = builders[key]
            section = _Section(text, self)
            build(section)
            section.finish()
            self._sections[key] = section
            self._stack.addWidget(section)
            item = QListWidgetItem(text, self._nav)
            item.setData(Qt.ItemDataRole.UserRole, key)
        self.open_section(current)

    def _rebuild(self) -> None:
        """İçe aktarma/sıfırlamadan sonra bütün bölümler yeni ayarlarla yeniden kurulur."""
        current = self._nav.currentItem()
        key = current.data(Qt.ItemDataRole.UserRole) if current else "general"
        self._nav.blockSignals(True)
        self._nav.clear()
        self._nav.blockSignals(False)
        for section in self._sections.values():
            self._stack.removeWidget(section)
            section.deleteLater()
        self._sections.clear()
        self._settings = app_settings.load()
        self._build_sections(key)
        self._load_history()
        self._load_plugins()
        self._load_data()

    # --- Gezinme ve arama ---

    def _on_nav(self, row: int) -> None:
        item = self._nav.item(row)
        if item is not None:
            self._stack.setCurrentWidget(self._sections[item.data(Qt.ItemDataRole.UserRole)])

    def open_section(self, key: str) -> None:
        self._search.clear()
        for row in range(self._nav.count()):
            if self._nav.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self._nav.setCurrentRow(row)
                return

    def _filter(self, text: str) -> None:
        query = text.strip().casefold()
        first_visible = -1
        for row in range(self._nav.count()):
            item = self._nav.item(row)
            section = self._sections[item.data(Qt.ItemDataRole.UserRole)]
            match = not query or query in section.search_text()
            item.setHidden(not match)
            if match and first_visible < 0:
                first_visible = row
        current = self._nav.currentItem()
        if first_visible >= 0 and (current is None or current.isHidden()):
            self._nav.setCurrentRow(first_visible)

    # --- Yardımcılar ---

    @staticmethod
    def _combo(parent: QWidget, items: list[tuple[str, str]], current: str) -> QComboBox:
        combo = QComboBox(parent)
        for value, text in items:
            combo.addItem(text, value)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        return combo

    def _save(self) -> None:
        app_settings.save(self._settings)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._load_history()
        self._load_plugins()
        self._load_data()

    def on_tasks_finished(self) -> None:
        if self.isVisible():
            self._load_history()

    # --- Genel ---

    def _build_general(self, s: _Section) -> None:
        card = s.card(tr("Language and window"))
        form = QFormLayout()
        self._lang = self._combo(
            card, [("tr", "Türkçe"), ("en", "English")], self._settings.language
        )
        self._lang.currentIndexChanged.connect(self._on_lang)
        form.addRow(tr("Language:"), self._lang)
        close = "quit" if self._settings.close_action == "quit" else "tray"
        self._close = self._combo(
            card,
            [
                ("tray", tr("Keep running in the background")),
                ("quit", tr("Quit Linwas")),
            ],
            close,
        )
        self._close.currentIndexChanged.connect(self._on_close)
        form.addRow(tr("When I close the window:"), self._close)
        card.layout.addLayout(form)
        self._lang_note = QLabel(tr("The language changes the next time Linwas starts."), card)
        self._lang_note.setObjectName("Secondary")
        self._lang_note.hide()
        card.layout.addWidget(self._lang_note)
        hint = QLabel(
            tr(
                "In the background Linwas shows notifications about updates and problems. "
                "Open it again from the application menu."
            ),
            card,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        card.layout.addWidget(hint)

        card = s.card(tr("Help"))
        row = QHBoxLayout()
        tour = QPushButton(tr("Show the welcome tour again"), card)
        tour.clicked.connect(self.onboarding_requested)
        row.addWidget(tour)
        quit_btn = QPushButton(tr("Quit Linwas completely"), card)
        quit_btn.setToolTip(tr("Stops Linwas, including the background notifications."))
        quit_btn.clicked.connect(self.quit_requested)
        row.addWidget(quit_btn)
        row.addStretch(1)
        card.layout.addLayout(row)

    def _on_close(self) -> None:
        self._settings.close_action = self._close.currentData()
        self._save()
        self.close_action_changed.emit(self._settings.close_action)

    def _on_lang(self) -> None:
        self._settings.language = self._lang.currentData()
        self._save()
        self._lang_note.show()

    # --- Görünüm ---

    def _build_appearance(self, s: _Section) -> None:
        card = s.card(tr("Theme"))
        form = QFormLayout()
        self._theme = self._combo(
            card,
            [
                ("system", tr("Same as system")),
                ("light", tr("Light")),
                ("dark", tr("Dark")),
                ("high_contrast", tr("High contrast")),
            ],
            self._settings.theme,
        )
        self._theme.currentIndexChanged.connect(self._on_theme)
        form.addRow(tr("Linwas theme:"), self._theme)
        card.layout.addLayout(form)
        note = QLabel(
            tr("The desktop's own theme and wallpaper are under Interface › Theme & Wallpaper."),
            card,
        )
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        card.layout.addWidget(note)

    def _on_theme(self) -> None:
        self._settings.theme = self._theme.currentData()
        self._save()
        self.theme_changed.emit(self._settings.theme)

    # --- Yapay zekâ ---

    def _build_ai(self, s: _Section) -> None:
        self._ai = AISettingsSection(self._settings, s)
        self._ai.changed.connect(self.ai_settings_changed)
        s.body.addWidget(self._ai)

    # --- Bildirimler ve başlangıç ---

    def _build_notifications(self, s: _Section) -> None:
        card = s.card(tr("Startup"))
        self._autostart = QCheckBox(
            tr("Start Linwas in the background when I log in (for notifications)"), card
        )
        self._autostart.setChecked(self._settings.autostart)
        self._autostart.toggled.connect(self._on_autostart)
        card.layout.addWidget(self._autostart)

        card = s.card(tr("Notifications"))
        if not notify.available():
            warn = QLabel(
                tr("Desktop notifications are not available on this system (gdbus is missing)."),
                card,
            )
            warn.setObjectName("Warning")
            warn.setWordWrap(True)
            card.layout.addWidget(warn)
        for attr, text in (
            ("notify_updates", tr("Updates are ready")),
            ("notify_restart", tr("A restart is required")),
            ("notify_autoupdate", tr("Automatic updates were installed or failed")),
            ("notify_devices", tr("A device has no driver")),
        ):
            box = QCheckBox(text, card)
            box.setChecked(getattr(self._settings, attr))
            box.toggled.connect(lambda on, a=attr: self._set_flag(a, on))
            card.layout.addWidget(box)
        test = QPushButton(tr("Send a test notification"), card)
        test.clicked.connect(self.notifications_test_requested)
        card.layout.addWidget(test, 0, Qt.AlignmentFlag.AlignLeft)

        card = s.card(tr("Quiet hours"))
        self._quiet = QCheckBox(tr("Don't show notifications between these times"), card)
        self._quiet.setChecked(self._settings.quiet_hours)
        self._quiet.toggled.connect(lambda on: self._set_flag("quiet_hours", on))
        card.layout.addWidget(self._quiet)
        row = QHBoxLayout()
        self._quiet_start = QTimeEdit(QTime.fromString(self._settings.quiet_start, "HH:mm"), card)
        self._quiet_start.setDisplayFormat("HH:mm")
        self._quiet_start.timeChanged.connect(self._on_quiet_times)
        row.addWidget(self._quiet_start)
        row.addWidget(QLabel("–", card))
        self._quiet_end = QTimeEdit(QTime.fromString(self._settings.quiet_end, "HH:mm"), card)
        self._quiet_end.setDisplayFormat("HH:mm")
        self._quiet_end.timeChanged.connect(self._on_quiet_times)
        row.addWidget(self._quiet_end)
        row.addStretch(1)
        card.layout.addLayout(row)

    def _set_flag(self, attr: str, on: bool) -> None:
        setattr(self._settings, attr, on)
        self._save()

    def _on_autostart(self, on: bool) -> None:
        self._settings.autostart = on
        self._save()
        if not autostart.set_enabled(on):
            QMessageBox.warning(
                self, tr("Startup"), tr("The startup setting could not be changed.")
            )

    def _on_quiet_times(self) -> None:
        self._settings.quiet_start = self._quiet_start.time().toString("HH:mm")
        self._settings.quiet_end = self._quiet_end.time().toString("HH:mm")
        self._save()

    # --- Gizlilik ve veriler ---

    def _build_privacy(self, s: _Section) -> None:
        card = s.card(tr("Data Linwas keeps"))
        intro = QLabel(
            tr(
                "Everything stays on this computer. API keys are kept in the system keyring "
                "and deleted under AI assistant."
            ),
            card,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        card.layout.addWidget(intro)
        self._data_rows = QVBoxLayout()
        self._data_rows.setSpacing(6)
        card.layout.addLayout(self._data_rows)
        rrow = QHBoxLayout()
        self._rollback_lbl = QLabel("", card)
        self._rollback_lbl.setWordWrap(True)
        rrow.addWidget(self._rollback_lbl, 1)
        backups = QPushButton(tr("Backups & Rollback") + " ›", card)
        backups.clicked.connect(lambda: self.page_requested.emit("backups"))
        rrow.addWidget(backups)
        card.layout.addLayout(rrow)
        delete_all = QPushButton(tr("Delete all my Linwas data"), card)
        delete_all.clicked.connect(self._delete_all_data)
        card.layout.addWidget(delete_all, 0, Qt.AlignmentFlag.AlignLeft)

        card = s.card(tr("Activity history"))
        self._history = QListWidget(card)
        self._history.setMinimumHeight(220)
        self._history.setAccessibleName(tr("Activity history"))
        card.layout.addWidget(self._history)
        row = QHBoxLayout()
        row.addStretch(1)
        clear = QPushButton(tr("Clear history"), card)
        clear.clicked.connect(self._clear_history)
        row.addWidget(clear)
        card.layout.addLayout(row)

    def _load_history(self) -> None:
        self._history.clear()
        results = {
            "success": tr("Done"),
            "failure": tr("Failed"),
            "partial": tr("Partly done"),
        }
        entries = HistoryDB().list(limit=200)
        if not entries:
            self._history.addItem(tr("No activity yet."))
            return
        for e in entries:
            mark = "✓" if e.result == "success" else "⚠"
            self._history.addItem(
                f"{mark} {_when(e.timestamp)} — {e.task_label} ({results.get(e.result, e.result)})"
            )

    def _clear_history(self) -> None:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            tr("Clear history"),
            tr("Delete the whole activity history?"),
            parent=self,
        )
        yes = box.addButton(tr("Delete"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            HistoryDB().clear()
            self._load_history()

    def _data_label(self, key: str) -> tuple[str, str]:
        return {
            "history": (tr("Activity history"), tr("What Linwas changed on this computer")),
            "chats": (tr("AI conversations"), tr("Saved conversations with the assistant")),
            "usage": (
                tr("AI usage counters"),
                tr("Tokens used per month and your monthly limits"),
            ),
            "notifications": (
                tr("Notification state"),
                tr("Which notifications were already shown"),
            ),
            "drivers": (
                tr("Driver change history"),
                tr("Needed for “Return to the previous driver”"),
            ),
            "log": (tr("Log files"), tr("Written only when the detailed log is on")),
        }.get(key, (key, ""))

    def _load_data(self) -> None:
        from linwas.core import user_data

        if not hasattr(self, "_data_rows"):
            return
        while self._data_rows.count():
            row = self._data_rows.takeAt(0)
            if row.layout():
                while row.layout().count():
                    w = row.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()
        locale = QLocale()
        for item in user_data.items():
            name, desc = self._data_label(item.key)
            row = QHBoxLayout()
            size = locale.formattedDataSize(item.size, 1) if item.exists else tr("none")
            lbl = QLabel(
                f"<b>{name}</b> · {size}<br><span style='font-size:11px'>{desc}</span>", self
            )
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
            btn = QPushButton(tr("Delete"), self)
            btn.setEnabled(item.exists and item.size > 0)
            btn.clicked.connect(lambda _=False, k=item.key, n=name: self._delete_data(k, n))
            row.addWidget(btn)
            self._data_rows.addLayout(row)
        count = user_data.rollback_record_count()
        self._rollback_lbl.setText(
            tr("Undo records: {n} (kept by the system, managed under Backups & Rollback)").format(
                n=count if count is not None else "?"
            )
        )

    def _delete_data(self, key: str, name: str) -> None:
        from linwas.core import user_data

        answer = QMessageBox.question(self, tr("Delete"), tr("Delete {name}?").format(name=name))
        if answer != QMessageBox.StandardButton.Yes:
            return
        user_data.delete(key)
        self._load_data()
        self._load_history()
        if key in ("chats", "usage"):
            self.ai_settings_changed.emit()

    def _delete_all_data(self) -> None:
        from linwas.core import user_data

        answer = QMessageBox.question(
            self,
            tr("Delete all my Linwas data"),
            tr(
                "Delete the activity history, AI conversations and usage counters, notification "
                "state, driver change history and logs? Settings and API keys are kept."
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not user_data.delete_all():
            QMessageBox.warning(self, tr("Delete"), tr("Some data could not be deleted."))
        self._load_data()
        self._load_history()
        self.ai_settings_changed.emit()

    # --- Yedekleme ve sıfırlama ---

    def _build_backup(self, s: _Section) -> None:
        card = s.card(tr("Move your settings"))
        text = QLabel(
            tr(
                "Save Linwas settings to a file and load them on another computer. API keys "
                "are not written to the file."
            ),
            card,
        )
        text.setWordWrap(True)
        card.layout.addWidget(text)
        row = QHBoxLayout()
        export = QPushButton(tr("Export settings…"), card)
        export.clicked.connect(self._export)
        row.addWidget(export)
        imp = QPushButton(tr("Import settings…"), card)
        imp.clicked.connect(self._import)
        row.addWidget(imp)
        row.addStretch(1)
        card.layout.addLayout(row)

        card = s.card(tr("Reset"))
        text = QLabel(
            tr(
                "Return all Linwas settings to their defaults. Your data, API keys and the "
                "changes Linwas made to the system are not affected."
            ),
            card,
        )
        text.setWordWrap(True)
        card.layout.addWidget(text)
        reset = QPushButton(tr("Reset settings"), card)
        reset.clicked.connect(self._reset)
        card.layout.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)

    def _export(self) -> None:
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        from linwas.core import user_data

        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export settings"),
            str(Path.home() / "linwas-settings.json"),
            tr("Linwas settings (*.json)"),
        )
        if not path:
            return
        try:
            user_data.export_settings(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, tr("Export settings"), str(exc))
            return
        QMessageBox.information(self, tr("Export settings"), tr("Settings saved."))

    def _import(self) -> None:
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        from linwas.core import user_data

        path, _ = QFileDialog.getOpenFileName(
            self, tr("Import settings"), str(Path.home()), tr("Linwas settings (*.json)")
        )
        if not path:
            return
        try:
            user_data.import_settings(Path(path))
        except user_data.ImportError_:
            QMessageBox.warning(
                self, tr("Import settings"), tr("This file is not a Linwas settings file.")
            )
            return
        self._apply_reloaded()
        QMessageBox.information(
            self,
            tr("Import settings"),
            tr("Settings loaded. The language changes the next time Linwas starts."),
        )

    def _reset(self) -> None:
        from linwas.core import user_data

        answer = QMessageBox.question(
            self, tr("Reset settings"), tr("Return all Linwas settings to their defaults?")
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        user_data.reset_settings()
        self._apply_reloaded()

    def _apply_reloaded(self) -> None:
        """Diskteki yeni ayarları uygular: tema, başlangıç, kapatma davranışı, AI."""
        settings = app_settings.load()
        autostart.set_enabled(settings.autostart)
        self.theme_changed.emit(settings.theme)
        self.close_action_changed.emit(settings.close_action)
        self.ai_settings_changed.emit()
        self._rebuild()

    # --- Hakkında ---

    def _build_about(self, s: _Section) -> None:
        import os
        import sys

        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion

        from linwas import __version__
        from linwas.backend.desktop import detect_desktop, detect_session_type
        from linwas.backend.distro import detect_distro

        card = s.card("Linwas")
        info = [
            (tr("Version"), __version__),
            (tr("System"), detect_distro().display_name),
            (
                tr("Desktop"),
                f"{detect_desktop(os.environ).value} ({detect_session_type(os.environ)})",
            ),
            ("Python", sys.version.split()[0]),
            ("Qt / PySide6", f"{qVersion()} / {pyside_version}"),
        ]
        form = QFormLayout()
        for label, value in info:
            v = QLabel(value, card)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label + ":", v)
        card.layout.addLayout(form)
        self._about_text = "\n".join(f"{k}: {v}" for k, v in info)
        row = QHBoxLayout()
        copy = QPushButton(tr("Copy system information"), card)
        copy.clicked.connect(self._copy_about)
        row.addWidget(copy)
        report = QPushButton(tr("Report a problem"), card)
        report.clicked.connect(self._report_problem)
        row.addWidget(report)
        row.addStretch(1)
        card.layout.addLayout(row)

        card = s.card(tr("Licenses"))
        lic = QLabel(
            tr("Linwas: the licence will be chosen before the first public release.")
            + "\n"
            + tr("Qt and PySide6: LGPL-3.0 · Python: PSF License · keyring: MIT"),
            card,
        )
        lic.setWordWrap(True)
        card.layout.addWidget(lic)

    def _copy_about(self) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self._about_text)

    def _report_problem(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from linwas.core.error_report import issue_url

        QDesktopServices.openUrl(QUrl(issue_url("Linwas: ", self._about_text)))

    # --- Eklentiler ---

    def _build_plugins(self, s: _Section) -> None:
        card = s.card(tr("Installed plugins"))
        self._plugins = QLabel("", card)
        self._plugins.setWordWrap(True)
        card.layout.addWidget(self._plugins)

    def _load_plugins(self) -> None:
        from linwas.core.plugins.loader import PluginLoader

        # Ana pencerenin yüklediği eklentiler (yerleşikler dahil)
        loader = getattr(self.window(), "plugin_loader", None)
        if loader is None:
            loader = PluginLoader()
            with contextlib.suppress(Exception):
                loader.discover()
        lines = []
        for plugin in loader.plugins():
            info = getattr(plugin, "meta", None)
            name = getattr(info, "name", type(plugin).__name__)
            version = getattr(info, "version", "")
            lines.append(f"✓ {name} {version}".strip())
        for name, error in loader.errors():
            lines.append(f"⚠ {name}: {error}")
        empty = tr("No plugins installed. Built-in features are listed in the menu.")
        self._plugins.setText("\n".join(lines) if lines else empty)
