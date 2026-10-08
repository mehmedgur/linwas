"""Tüm Ayarlar (Denetim Masası): klasik "Kategori görünümü".

Her kategori bir satır: solda büyük simge, sağda kalın başlık ve altında tıklanabilir
bağlantılar. Linwas'ın kendi sayfası olan ayarlarda önce Linwas sayfası açılır (Linwas
öncelikli) ve bağlantının yanında küçük "Linwas" etiketi durur; sistemdeki karşılığı
sağ tık menüsündeki "Sistem ayarlarında aç" ile açılır.
"""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
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

# Satırdaki bağlantıların ayırıcısı
_SEPARATOR = " · "


def _categories() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """(simge, başlık, [(ayar kimliği, bağlantı metni)])."""
    return [
        (
            "system",
            tr("System"),
            [
                ("about", tr("About this computer")),
                ("datetime", tr("Date & time")),
                ("region", tr("Language & region")),
                ("users", tr("User accounts")),
                ("default_apps", tr("Default apps")),
            ],
        ),
        (
            "hardware",
            tr("Hardware & sound"),
            [
                ("display", tr("Display")),
                ("sound", tr("Sound")),
                ("mouse", tr("Mouse & touchpad")),
                ("keyboard", tr("Keyboard")),
                ("printers", tr("Printers")),
                ("power", tr("Power")),
            ],
        ),
        (
            "network",
            tr("Network & Internet"),
            [
                ("wifi", tr("Wi-Fi")),
                ("network", tr("Network connections")),
                ("bluetooth", tr("Bluetooth")),
            ],
        ),
        (
            "interface",
            tr("Appearance & personalization"),
            [
                ("background", tr("Wallpaper")),
                ("themes", tr("Colors & theme")),
                ("fonts", tr("Fonts")),
            ],
        ),
        (
            "privacy",
            tr("Privacy & notifications"),
            [
                ("privacy", tr("Privacy")),
                ("notifications", tr("Notifications")),
            ],
        ),
        ("accessibility", tr("Ease of access"), [("accessibility", tr("Accessibility"))]),
    ]


def _fold(text: str) -> str:
    """Aramada büyük/küçük harf ve Türkçe İ/ı farkını yok sayar."""
    return text.replace("İ", "i").replace("I", "ı").lower()


class _LinkLabel(QLabel):
    """Bağlantı satırı; sağ tıkta üzerindeki bağlantının menüsünü açar."""

    def __init__(self, page: AllSettingsPage, parent: QWidget) -> None:
        super().__init__(parent)
        self._page = page
        self._hovered = ""
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.linkActivated.connect(page.open_item)
        self.linkHovered.connect(self._on_hovered)
        self.customContextMenuRequested.connect(self._menu)

    def _on_hovered(self, link: str) -> None:
        self._hovered = link

    def _menu(self, pos: QPoint) -> None:
        if self._hovered:
            self._page.show_item_menu(self._hovered, self.mapToGlobal(pos))


class _CategoryRow(QWidget):
    def __init__(
        self,
        page: AllSettingsPage,
        icon_name: str,
        title: str,
        items: list[tuple[str, str]],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardRow")
        self._page = page
        self._title = title
        self._items = items
        self._visible_ids = [item_id for item_id, _ in items]

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(14)
        ico = QLabel(self)
        ico.setObjectName("CardIcon")
        ico.setFixedSize(56, 56)
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icons.bind(ico, icon_name, "accent", 34)
        lay.addWidget(ico, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(4)
        head = QLabel(title, self)
        head.setObjectName("AppName")
        col.addWidget(head)
        self._links = _LinkLabel(page, self)
        self._links.setAccessibleName(title)
        col.addWidget(self._links)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.render_links()

    def apply_filter(self, needle: str) -> bool:
        """Aramaya uyan bağlantıları bırakır; satırda hiç kalmazsa False."""
        if not needle or needle in _fold(self._title):
            ids = [item_id for item_id, _ in self._items]
        else:
            ids = [item_id for item_id, label in self._items if needle in _fold(label)]
        self._visible_ids = ids
        self.render_links()
        return bool(ids)

    def render_links(self) -> None:
        link_color = icons.color_for("accent")
        muted = icons.color_for("secondary")
        parts = []
        for item_id, label in self._items:
            if item_id not in self._visible_ids:
                continue
            text = html.escape(label)
            if not self._page.can_open(item_id):
                parts.append(f'<span style="color:{muted}">{text}</span>')
                continue
            part = (
                f'<a href="{item_id}" style="color:{link_color}; text-decoration:none">{text}</a>'
            )
            if item_id in _LINWAS_PAGES:
                part += (
                    f' <span style="color:{muted}; font-size:10px; font-weight:bold">'
                    f"{html.escape(tr('Linwas'))}</span>"
                )
            parts.append(part)
        self._links.setText(_SEPARATOR.join(parts))


class AllSettingsPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._desktop = detect_desktop(os.environ).value
        self._labels = {item_id: label for _, _, items in _categories() for item_id, label in items}

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

        card = Card(content)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        self._grid = grid
        self._rows = [
            _CategoryRow(self, icon_name, cat_title, items, card)
            for icon_name, cat_title, items in _categories()
        ]
        self._place_rows(self._rows)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        card.layout.addLayout(grid)
        outer.addWidget(card)

        self._empty = QLabel(tr("No settings match your search."), content)
        self._empty.setObjectName("Secondary")
        self._empty.hide()
        outer.addWidget(self._empty)
        self._card = card

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
        label = self._labels.get(item_id, "")
        if item_id in _LINWAS_PAGES:
            menu.addAction(tr("Open in Linwas"), lambda: self.open_item(item_id))
        sys_action = menu.addAction(
            tr("Open in system settings"), lambda: open_settings(item_id, self._desktop)
        )
        sys_action.setEnabled(self._has_system(item_id))
        menu.setAccessibleName(label)
        menu.exec(global_pos)

    # --- Arama ve tema ---

    def _filter(self, text: str) -> None:
        needle = _fold(text.strip())
        shown = []
        for row in self._rows:
            visible = row.apply_filter(needle)
            row.setVisible(visible)
            if visible:
                shown.append(row)
        # Gizlenen satırlar boşluk bırakmasın: kalanlar baştan iki sütuna dizilir.
        self._place_rows(shown)
        self._card.setVisible(bool(shown))
        self._empty.setVisible(not shown)

    def _place_rows(self, rows: list[_CategoryRow]) -> None:
        for row in self._rows:
            self._grid.removeWidget(row)
        for i, row in enumerate(rows):
            self._grid.addWidget(row, i // 2, i % 2)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        # Tema değişince bağlantı renkleri yeni paletten yeniden yazılır.
        if event.type() == QEvent.Type.StyleChange:
            for row in getattr(self, "_rows", []):
                row.render_links()
        super().changeEvent(event)
