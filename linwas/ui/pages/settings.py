"""Linwas'ın kendi ayarları: tema, pencere kapatma, dil, işlem geçmişi, eklentiler."""

from __future__ import annotations

import contextlib
from datetime import datetime

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.core import app_settings
from linwas.core.history import HistoryDB
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("SettingsPage", text)


def _when(iso: str) -> str:
    try:
        ts = int(datetime.fromisoformat(iso).timestamp())
    except ValueError:
        return iso
    return QLocale().toString(QDateTime.fromSecsSinceEpoch(ts), QLocale.FormatType.ShortFormat)


class SettingsPage(BasePage):
    theme_changed = Signal(str)  # app_settings.THEMES değerlerinden biri
    close_action_changed = Signal(str)
    consent_changed = Signal(str)
    onboarding_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = app_settings.load()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        title = QLabel(tr("Settings"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Genel
        card = Card(content)
        h = QLabel(tr("General"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
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
        self._close = self._combo(
            card,
            [
                ("auto", tr("Automatic (tray if available, otherwise quit)")),
                ("tray", tr("Keep running in the system tray")),
                ("quit", tr("Quit Linwas")),
            ],
            self._settings.close_action,
        )
        self._close.currentIndexChanged.connect(self._on_close)
        form.addRow(tr("When I close the window:"), self._close)
        self._lang = self._combo(
            card, [("tr", "Türkçe"), ("en", "English")], self._settings.language
        )
        self._lang.currentIndexChanged.connect(self._on_lang)
        form.addRow(tr("Language:"), self._lang)
        self._consent = self._combo(
            card,
            [("ask", tr("Ask every time")), ("yes", tr("Yes")), ("no", tr("No"))],
            self._settings.send_errors_to_ai,
        )
        self._consent.currentIndexChanged.connect(self._on_consent)
        form.addRow(tr("Send error details to the assistant:"), self._consent)
        card.layout.addLayout(form)
        self._lang_note = QLabel(tr("The language changes the next time Linwas starts."), card)
        self._lang_note.setObjectName("Secondary")
        self._lang_note.hide()
        card.layout.addWidget(self._lang_note)
        tour = QPushButton(tr("Show the welcome tour again"), card)
        tour.clicked.connect(self.onboarding_requested)
        card.layout.addWidget(tour)
        outer.addWidget(card)

        # İşlem geçmişi
        card = Card(content)
        h = QLabel(tr("Activity history"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        self._history = QListWidget(card)
        self._history.setMinimumHeight(180)
        self._history.setAccessibleName(tr("Activity history"))
        card.layout.addWidget(self._history)
        row = QHBoxLayout()
        row.addStretch(1)
        clear = QPushButton(tr("Clear history"), card)
        clear.clicked.connect(self._clear_history)
        row.addWidget(clear)
        card.layout.addLayout(row)
        outer.addWidget(card)

        # Eklentiler
        card = Card(content)
        h = QLabel(tr("Plugins"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        self._plugins = QLabel("", card)
        self._plugins.setWordWrap(True)
        card.layout.addWidget(self._plugins)
        outer.addWidget(card)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    @staticmethod
    def _combo(parent: QWidget, items: list[tuple[str, str]], current: str) -> QComboBox:
        combo = QComboBox(parent)
        for value, text in items:
            combo.addItem(text, value)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        return combo

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._load_history()
        self._load_plugins()

    def on_tasks_finished(self) -> None:
        if self.isVisible():
            self._load_history()

    # --- Genel ---

    def _save(self) -> None:
        app_settings.save(self._settings)

    def _on_theme(self) -> None:
        self._settings.theme = self._theme.currentData()
        self._save()
        self.theme_changed.emit(self._settings.theme)

    def _on_close(self) -> None:
        self._settings.close_action = self._close.currentData()
        self._save()
        self.close_action_changed.emit(self._settings.close_action)

    def _on_consent(self) -> None:
        self._settings.send_errors_to_ai = self._consent.currentData()
        self._save()
        self.consent_changed.emit(self._settings.send_errors_to_ai)

    def _on_lang(self) -> None:
        self._settings.language = self._lang.currentData()
        self._save()
        self._lang_note.show()

    # --- Geçmiş ---

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

    # --- Eklentiler ---

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
