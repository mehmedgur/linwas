"""Eco ayarlar penceresi: sol gezinme (gruplu) + sayfa alanı."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QSize, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from linwas.core import theme
from linwas.ui.eco.about_page import AboutPage
from linwas.ui.eco.widgets import Page
from linwas.ui.theme.manager import ThemeManager

_PAGE_ROLE = Qt.ItemDataRole.UserRole


def tr(text: str) -> str:
    return QCoreApplication.translate("EcoSettingsWindow", text)


@dataclass(frozen=True)
class NavEntry:
    key: str
    icon: str
    label: str


def nav_groups() -> list[tuple[str, list[NavEntry]]]:
    """Gezinme grupları ve öğeleri ('Hakkında' görselindeki sıra)."""
    return [
        (
            tr("Personalization"),
            [
                NavEntry("appearance", "appearance", tr("Appearance")),
                NavEntry("display", "display", tr("Display")),
            ],
        ),
        (
            tr("System"),
            [
                NavEntry("network", "network", tr("Network")),
                NavEntry("sound", "sound", tr("Sound")),
                NavEntry("storage", "storage", tr("Storage")),
            ],
        ),
        (
            tr("Account & security"),
            [
                NavEntry("users", "users", tr("Users")),
                NavEntry("security", "security", tr("Security")),
            ],
        ),
        (
            tr("Other"),
            [
                NavEntry("apps", "apps", tr("Apps")),
                NavEntry("accessibility", "accessibility", tr("Accessibility")),
                NavEntry("about", "about", tr("About")),
            ],
        ),
    ]


class EcoSettingsWindow(QMainWindow):
    def __init__(self, themes: ThemeManager) -> None:
        super().__init__()
        self._themes = themes
        tokens = theme.load_tokens(theme.EDITION_ECO)
        width, height = tokens["olcu"]["pencere_varsayilan"]
        min_width, min_height = tokens["olcu"]["pencere_en_kucuk"]
        self.setWindowTitle(tr("System Settings"))
        self.resize(width, height)
        self.setMinimumSize(min_width, min_height)

        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        self._nav.setFixedWidth(tokens["olcu"]["gezinme_bolmesi"])
        self._nav.setIconSize(QSize(tokens["olcu"]["simge"], tokens["olcu"]["simge"]))
        self._nav.setAccessibleName(tr("Settings categories"))
        self._nav.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._stack = QStackedWidget()
        self._icons: list[tuple[QListWidgetItem, str]] = []
        item_height = tokens["olcu"]["gezinme_ogesi"]

        caption = theme.font_style("caption", theme.EDITION_ECO)
        for position, (group, entries) in enumerate(nav_groups()):
            header = QListWidgetItem(group.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header_font = header.font()
            header_font.setPixelSize(caption.size)
            header_font.setWeight(QFont.Weight.Medium)
            header.setFont(header_font)
            # İlk başlığın üstü dar, sonrakilerde grup arası boşluk
            header.setSizeHint(QSize(0, 32 if position == 0 else 44))
            header.setData(Qt.ItemDataRole.AccessibleTextRole, group)
            self._nav.addItem(header)
            for entry in entries:
                item = QListWidgetItem(entry.label)
                item.setSizeHint(QSize(0, item_height))
                item.setData(_PAGE_ROLE, self._stack.count())
                self._nav.addItem(item)
                self._icons.append((item, entry.icon))
                self._stack.addWidget(self._make_page(entry))

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._nav.currentItemChanged.connect(self._on_item_changed)
        themes.modeChanged.connect(lambda _mode: self._refresh_icons())
        self.show_page("about")

    @staticmethod
    def _make_page(entry: NavEntry) -> QWidget:
        if entry.key == "about":
            return AboutPage()
        page = Page(entry.label)
        note = QLabel(tr("This page is not ready yet."))
        note.setProperty("role", "tertiary")
        page.body.addWidget(note)
        page.body.addStretch(1)
        return page

    def show_page(self, key: str) -> None:
        for index in range(self._nav.count()):
            item = self._nav.item(index)
            if item.data(_PAGE_ROLE) is not None and self._icon_name(item) == key:
                self._nav.setCurrentItem(item)
                return

    def _icon_name(self, item: QListWidgetItem) -> str:
        return next(name for it, name in self._icons if it is item)

    def _on_item_changed(self, current: QListWidgetItem | None, _previous) -> None:  # noqa: ANN001
        if current is not None and current.data(_PAGE_ROLE) is not None:
            self._stack.setCurrentIndex(current.data(_PAGE_ROLE))
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        """Seçili öğenin simgesi vurgu renginde, diğerleri ikincil metin renginde."""
        pal = theme.palette(self._themes.edition, self._themes.mode)
        current = self._nav.currentItem()
        icon: QIcon
        for item, name in self._icons:
            color = pal.accent if item is current else pal.text_secondary
            icon = self._themes.icon(name, color)
            item.setIcon(icon)
