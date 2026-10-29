# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Tüm Ayarlar (Denetim Masası): klasik "Kategori görünümü".

Her kategori bir kart: solda büyük renkli simge, sağda kalın başlık ve kısa açıklama;
altında her ayar kendi simgesiyle tıklanabilir bağlantı. Linwas'ın kendi sayfası olan
ayarlarda önce Linwas sayfası açılır (Linwas öncelikli) ve bağlantının yanında küçük
"Linwas" etiketi durur; sistemdeki karşılığı sağ tık menüsündeki "Sistem ayarlarında aç"
ile açılır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.desktop import detect_desktop
from linwas.backend.settings_launcher import command_for, open_settings
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("AllSettingsPage", text)


# ayar kimliği → Linwas'ta aynı işi yapan sayfa
_LINWAS_PAGES = {
    "network": "network",
    "wifi": "network",
    "bluetooth": "network",
    "printers": "hardware",
    "power": "power",
    "background": "theme",
    "themes": "theme",
    "fonts": "fonts",
    "display": "display",
}


@dataclass(frozen=True)
class _Category:
    icon: str
    title: str
    description: str
    items: list[tuple[str, str, str]]  # (ayar kimliği, simge, bağlantı metni)


def _categories() -> list[_Category]:
    return [
        _Category(
            "system",
            tr("System"),
            tr("Computer info, time, language and accounts"),
            [
                ("about", "info", tr("About this computer")),
                ("datetime", "clock", tr("Date & time")),
                ("region", "globe", tr("Language & region")),
                ("users", "user", tr("User accounts")),
                ("default_apps", "default_apps", tr("Default apps")),
            ],
        ),
        _Category(
            "hardware",
            tr("Hardware & sound"),
            tr("Screen, sound, input devices, printers and power"),
            [
                ("display", "display", tr("Display")),
                ("sound", "sound", tr("Sound")),
                ("mouse", "mouse", tr("Mouse & touchpad")),
                ("keyboard", "keyboard", tr("Keyboard")),
                ("printers", "hardware", tr("Printers")),
                ("power", "power", tr("Power")),
            ],
        ),
        _Category(
            "network",
            tr("Network & Internet"),
            tr("Wireless, wired connections and Bluetooth"),
            [
                ("wifi", "network", tr("Wi-Fi")),
                ("network", "ethernet", tr("Network connections")),
                ("bluetooth", "bluetooth", tr("Bluetooth")),
            ],
        ),
        _Category(
            "interface",
            tr("Appearance & personalization"),
            tr("Wallpaper, colors and fonts"),
            [
                ("background", "wallpaper", tr("Wallpaper")),
                ("themes", "theme", tr("Colors & theme")),
                ("fonts", "fonts", tr("Fonts")),
            ],
        ),
        _Category(
            "privacy",
            tr("Privacy & notifications"),
            tr("What apps can see and which alerts you get"),
            [
                ("privacy", "privacy", tr("Privacy")),
                ("notifications", "bell", tr("Notifications")),
            ],
        ),
        _Category(
            "accessibility",
            tr("Ease of access"),
            tr("Text size, contrast, screen reader and more"),
            [("accessibility", "accessibility", tr("Accessibility"))],
        ),
    ]


def _fold(text: str) -> str:
    """Aramada büyük/küçük harf ve Türkçe İ/ı farkını yok sayar."""
    return text.replace("İ", "i").replace("I", "ı").lower()


class _SettingLink(QWidget):
    """Simgeli bağlantı düğmesi + (Linwas sayfası varsa) "Linwas" etiketi."""

    def __init__(
        self, page: AllSettingsPage, item_id: str, icon_name: str, label: str, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardRow")
        self.label = label
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        btn = QToolButton(self)
        btn.setObjectName("SettingLink")
        btn.setText(label.replace("&", "&&"))  # "&" kısayol işareti sayılmasın
        btn.setAccessibleName(label)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icons.bind(btn, icon_name, "accent", 18)
        btn.setEnabled(page.can_open(item_id))
        btn.clicked.connect(lambda: page.open_item(item_id))
        # Sağ tık ve klavyedeki menü tuşu aynı menüyü açar
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos: page.show_item_menu(item_id, btn.mapToGlobal(pos))
        )
        lay.addWidget(btn)

        if item_id in _LINWAS_PAGES:
            tag = QLabel(tr("Linwas"), self)
            tag.setObjectName("LinwasTag")
            tag.setToolTip(tr("Opens in Linwas; right-click for system settings"))
            lay.addWidget(tag, 0, Qt.AlignmentFlag.AlignVCenter)
            btn.setToolTip(tr("Opens in Linwas; right-click for system settings"))
        else:
            btn.setToolTip(tr("Opens in your system settings"))
        lay.addStretch(1)


class _CategoryCard(Card):
    def __init__(self, page: AllSettingsPage, cat: _Category, parent: QWidget) -> None:
        super().__init__(parent)
        self._title = cat.title
        self.layout.setContentsMargins(18, 16, 18, 14)
        self.layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(14)
        ico = QLabel(self)
        ico.setObjectName("CategoryIcon")
        ico.setFixedSize(52, 52)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icons.bind(ico, cat.icon, "on_accent", 30)
        head.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(cat.title, self)
        title.setObjectName("H2")
        text.addWidget(title)
        desc = QLabel(cat.description, self)
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        text.addWidget(desc)
        head.addLayout(text, 1)
        self.layout.addLayout(head)

        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("Separator")
        self.layout.addWidget(line)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(2)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._links = [
            _SettingLink(page, item_id, icon_name, label, self)
            for item_id, icon_name, label in cat.items
        ]
        self._place(self._links)
        self.layout.addLayout(self._grid)
        self.layout.addStretch(1)

    def _place(self, links: list[_SettingLink]) -> None:
        for link in self._links:
            self._grid.removeWidget(link)
        for i, link in enumerate(links):
            self._grid.addWidget(link, i // 2, i % 2)

    def apply_filter(self, needle: str) -> bool:
        """Aramaya uyan bağlantıları bırakır; kartta hiç kalmazsa False."""
        title_match = not needle or needle in _fold(self._title)
        shown = []
        for link in self._links:
            visible = title_match or needle in _fold(link.label)
            link.setVisible(visible)
            if visible:
                shown.append(link)
        self._place(shown)
        return bool(shown)


class AllSettingsPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._desktop = detect_desktop(os.environ).value

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(tr("All Settings"), content)
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch(1)
        self._search = QLineEdit(content)
        self._search.setPlaceholderText(tr("Search settings"))
        self._search.setAccessibleName(tr("Search settings"))
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(240)
        self._search.textChanged.connect(self._filter)
        header.addWidget(self._search)
        all_btn = QPushButton(tr("Open system settings"), content)
        all_btn.setEnabled(command_for("all", self._desktop) is not None)
        all_btn.clicked.connect(lambda: open_settings("all", self._desktop))
        header.addWidget(all_btn)
        outer.addLayout(header)

        hint = QLabel(
            tr(
                "Like the Windows Control Panel. Settings marked Linwas open in Linwas; "
                "right-click them to open the same setting in your system settings."
            ),
            content,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._cards = [_CategoryCard(self, cat, content) for cat in _categories()]
        self._place(self._cards)
        outer.addLayout(self._grid)

        self._empty = QLabel(tr("No settings match your search."), content)
        self._empty.setObjectName("Secondary")
        self._empty.hide()
        outer.addWidget(self._empty)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    # --- Bağlantılar ---

    def _has_system(self, item_id: str) -> bool:
        return command_for(item_id, self._desktop) is not None

    def can_open(self, item_id: str) -> bool:
        return item_id in _LINWAS_PAGES or self._has_system(item_id)

    def open_item(self, item_id: str) -> None:
        linwas_page = _LINWAS_PAGES.get(item_id)
        if linwas_page:
            self.page_requested.emit(linwas_page)
        elif self._has_system(item_id):
            open_settings(item_id, self._desktop)

    def show_item_menu(self, item_id: str, global_pos: QPoint) -> None:
        if not self.can_open(item_id):
            return
        menu = QMenu(self)
        if item_id in _LINWAS_PAGES:
            menu.addAction(tr("Open in Linwas"), lambda: self.open_item(item_id))
        sys_action = menu.addAction(
            tr("Open in system settings"), lambda: open_settings(item_id, self._desktop)
        )
        sys_action.setEnabled(self._has_system(item_id))
        menu.exec(global_pos)

    # --- Arama ---

    def _place(self, cards: list[_CategoryCard]) -> None:
        for card in self._cards:
            self._grid.removeWidget(card)
        for i, card in enumerate(cards):
            self._grid.addWidget(card, i // 2, i % 2)

    def _filter(self, text: str) -> None:
        needle = _fold(text.strip())
        shown = []
        for card in self._cards:
            visible = card.apply_filter(needle)
            card.setVisible(visible)
            if visible:
                shown.append(card)
        # Gizlenen kartlar boşluk bırakmasın: kalanlar baştan iki sütuna dizilir.
        self._place(shown)
        self._empty.setVisible(not shown)
