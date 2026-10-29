# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
""" "Windows'ta nasıl?" rehberi sayfası."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QCoreApplication, Signal
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

from linwas.backend import windows_guide
from linwas.backend.desktop import detect_desktop
from linwas.backend.settings_launcher import open_settings
from linwas.core import app_settings
from linwas.core.plugins.loader import active as active_plugins
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("GuidePage", text)


class GuidePage(BasePage):
    search_software = Signal(str)  # Programlar sayfasında ara

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries = windows_guide.load()
        self._plugin_entries_added = False
        self._lang = app_settings.load().language
        self._desktop = detect_desktop(os.environ).value

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(10)
        title = QLabel(tr("How was it on Windows?"), self)
        title.setObjectName("H1")
        layout.addWidget(title)
        hint = QLabel(
            tr("Type what you used on Windows — a setting, a program or a shortcut."), self
        )
        hint.setObjectName("Secondary")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self._query = QLineEdit(self)
        self._query.setPlaceholderText(tr("e.g. Control Panel, Word, Ctrl+Alt+Del"))
        self._query.setClearButtonEnabled(True)
        self._query.textChanged.connect(self._render)
        row.addWidget(self._query, 1)
        self._kind = QComboBox(self)
        for value, text in (
            ("", tr("Everything")),
            ("setting", tr("Settings")),
            ("program", tr("Programs")),
            ("shortcut", tr("Keyboard shortcuts")),
            ("concept", tr("Concepts")),
        ):
            self._kind.addItem(text, value)
        self._kind.currentIndexChanged.connect(self._render)
        row.addWidget(self._kind)
        layout.addLayout(row)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        holder = QWidget()
        self._list = QVBoxLayout(holder)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(8)
        self._list.addStretch(1)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        self._render()

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        # Eklentiler sayfalardan sonra yüklenir; girdileri ilk gösterimde eklenir
        if not self._plugin_entries_added:
            self._plugin_entries_added = True
            if self._add_plugin_entries():
                self._render()

    def _add_plugin_entries(self) -> bool:
        loader = active_plugins()
        if loader is None:
            return False
        added = False
        for entry in loader.gate("guide_entries"):
            action: dict[str, str] = {}
            if entry.target_page_id:
                action["page"] = entry.target_page_id
            elif entry.settings_launcher_key:
                action["settings"] = entry.settings_launcher_key
            self._entries.append(
                windows_guide.GuideEntry(
                    kind=entry.kind,
                    windows=list(entry.keywords),
                    # Eklenti metni zaten arayüz dilinde verir
                    text={self._lang: entry.label, "en": entry.label},
                    action=action,
                )
            )
            added = True
        return added

    def set_query(self, text: str) -> None:
        self._kind.setCurrentIndex(0)
        self._query.setText(text)

    def _clear(self) -> None:
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _render(self) -> None:
        self._clear()
        found = windows_guide.search(self._query.text(), self._entries, self._kind.currentData())
        if not found:
            lbl = QLabel(tr("Nothing found. Try another word or ask the assistant."), self)
            lbl.setObjectName("Secondary")
            self._list.insertWidget(0, lbl)
            return
        for i, entry in enumerate(found[:60]):
            self._list.insertWidget(i, self._card(entry))

    def _card(self, entry: windows_guide.GuideEntry) -> Card:
        card = Card(self)
        row = QHBoxLayout()
        info = QVBoxLayout()
        head = QLabel(f"<b>{html.escape(' · '.join(entry.windows[:3]))}</b>", card)
        info.addWidget(head)
        text = entry.text.get(self._lang) or entry.text.get("en", "")
        body = QLabel("→ " + text, card)
        body.setWordWrap(True)
        info.addWidget(body)
        row.addLayout(info, 1)
        button = self._action_button(card, entry.action)
        if button:
            row.addWidget(button)
        card.layout.addLayout(row)
        return card

    def _action_button(self, parent: QWidget, action: dict[str, str]) -> QPushButton | None:
        if "page" in action:
            btn = QPushButton(tr("Open"), parent)
            btn.clicked.connect(lambda: self.page_requested.emit(action["page"]))
        elif "settings" in action:
            btn = QPushButton(tr("Open settings"), parent)
            btn.clicked.connect(lambda: open_settings(action["settings"], self._desktop))
        elif "search" in action:
            btn = QPushButton(tr("Find program"), parent)
            btn.clicked.connect(lambda: self.search_software.emit(action["search"]))
        else:
            return None
        return btn
