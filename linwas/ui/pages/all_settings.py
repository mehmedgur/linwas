"""Tüm Ayarlar (Denetim Masası): Windows'taki gibi kategoriler.

Linwas'ın yaptığı ayarlarda önce Linwas sayfası açılır (Linwas öncelikli);
sistem ayarı ikincil düğmeyle açılır. Diğerleri doğrudan sistem ayarlarında açılır.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.desktop import detect_desktop
from linwas.backend.settings_launcher import command_for, open_settings
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


def _categories() -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        (
            tr("System"),
            [
                ("about", tr("About this computer")),
                ("datetime", tr("Date & time")),
                ("region", tr("Language & region")),
                ("users", tr("User accounts")),
                ("notifications", tr("Notifications")),
                ("default_apps", tr("Default apps")),
                ("privacy", tr("Privacy")),
            ],
        ),
        (
            tr("Devices"),
            [
                ("display", tr("Display")),
                ("sound", tr("Sound")),
                ("mouse", tr("Mouse & touchpad")),
                ("keyboard", tr("Keyboard")),
                ("printers", tr("Printers")),
                ("bluetooth", tr("Bluetooth")),
                ("power", tr("Power")),
            ],
        ),
        (
            tr("Network & Internet"),
            [("wifi", tr("Wi-Fi")), ("network", tr("Network connections"))],
        ),
        (
            tr("Personalization"),
            [
                ("background", tr("Wallpaper")),
                ("themes", tr("Colors & theme")),
                ("fonts", tr("Fonts")),
            ],
        ),
        (tr("Accessibility"), [("accessibility", tr("Accessibility"))]),
    ]


class AllSettingsPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._desktop = detect_desktop(os.environ).value

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(tr("All Settings"), content)
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch(1)
        all_btn = QPushButton(tr("Open system settings"), content)
        all_btn.setEnabled(command_for("all", self._desktop) is not None)
        all_btn.clicked.connect(lambda: open_settings("all", self._desktop))
        header.addWidget(all_btn)
        outer.addLayout(header)

        hint = QLabel(
            tr(
                "Like the Windows Control Panel. Where Linwas can do the job itself, its own "
                "page opens; everything else opens in your system settings."
            ),
            content,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        for cat_title, items in _categories():
            card = Card(content)
            h = QLabel(cat_title, card)
            h.setObjectName("H2")
            card.layout.addWidget(h)
            grid = QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)
            for i, (item_id, label) in enumerate(items):
                grid.addWidget(self._item(card, item_id, label), i // 2, i % 2)
            card.layout.addLayout(grid)
            outer.addWidget(card)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def _item(self, parent: QWidget, item_id: str, label: str) -> QWidget:
        row = QWidget(parent)
        row.setObjectName("CardRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        has_system = command_for(item_id, self._desktop) is not None
        linwas_page = _LINWAS_PAGES.get(item_id)

        main = QPushButton(label, row)
        main.setStyleSheet("text-align: left; padding-left: 10px;")
        if linwas_page:
            main.setToolTip(tr("Opens in Linwas"))
            main.clicked.connect(lambda: self.page_requested.emit(linwas_page))
        else:
            main.setEnabled(has_system)
            main.setToolTip(tr("Opens in your system settings"))
            main.clicked.connect(lambda: open_settings(item_id, self._desktop))
        lay.addWidget(main, 1)

        if linwas_page and has_system:
            sys_btn = QPushButton(tr("System"), row)
            sys_btn.setToolTip(tr("Open the same setting in your system settings"))
            sys_btn.setAccessibleName(tr("{name} in system settings").format(name=label))
            sys_btn.clicked.connect(lambda: open_settings(item_id, self._desktop))
            lay.addWidget(sys_btn)
        return row
