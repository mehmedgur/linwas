"""Sol gezinme menüsü.

Genişleyebilir alt menüler, arama kutusu, sistem durumu kartı ve
altta Ayarlar düğmesi içerir. Daraltılabilir (220 px ↔ 48 px).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linwas.ui import icons
from linwas.ui.theme.tokens import SIDEBAR_WIDTH

_LOGO = Path(__file__).resolve().parent.parent / "resources" / "linwas.svg"


def tr(text: str) -> str:
    return QCoreApplication.translate("Sidebar", text)


def _is_laptop() -> bool:
    from linwas.backend.power import is_laptop

    return is_laptop()


@dataclass
class MenuItem:
    id: str
    label: str
    icon: str = ""
    children: list[MenuItem] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return bool(self.children)


MENU: list[MenuItem] = [
    MenuItem("ai_chat", "AI Question"),
    MenuItem(
        "system",
        "System",
        children=[
            MenuItem("overview", "Overview"),
            MenuItem("updates", "Update center"),
            MenuItem("network", "Wi-Fi & Bluetooth"),
            MenuItem("backups", "Backups & Rollback"),
            MenuItem("hardware", "Hardware & Printers"),
            MenuItem("taskmgr", "Task Manager"),
            MenuItem("cleanup", "Disk Cleanup"),
            MenuItem("personal_backup", "Personal Backup"),
            MenuItem("power", "Power & Battery"),
            MenuItem("migrate", "Import from Windows"),
            MenuItem("all_settings", "All Settings"),
        ],
    ),
    MenuItem(
        "interface",
        "Interface",
        children=[
            MenuItem("appearance", "Windows Appearance"),
            MenuItem("theme", "Theme & Wallpaper"),
            MenuItem("fonts", "Fonts"),
            MenuItem("display", "Display & Scaling"),
            MenuItem("app_folders", "App Folders"),
            MenuItem("workgroups", "Work Groups"),
            MenuItem("window_groups", "Window Groups"),
        ],
    ),
    MenuItem("software", "Software"),
    MenuItem("troubleshoot", "Troubleshooting"),
    MenuItem("guide", "How was it on Windows?"),
]

BOTTOM_ITEMS: list[MenuItem] = [
    MenuItem("settings", "Settings"),
]


class _NavButton(QPushButton):
    def __init__(self, item: MenuItem, indent: int = 0, parent: QWidget | None = None) -> None:
        label = tr(item.label)
        if item.id == "power" and not _is_laptop():
            label = tr("Power")  # masaüstü bilgisayar: pil bölümleri yok
        super().__init__(label, parent)
        self._item = item
        self._active = False
        self._expanded = False
        # Grup başlığı ayrı görünür (küçük, ikincil renk, aç/kapa oku)
        self.setObjectName("SidebarGroup" if item.is_group else "SidebarItem")
        self.setProperty("active", False)
        self.setProperty("indent", str(indent))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCheckable(False)
        self._update_icon()

    @property
    def item_id(self) -> str:
        return self._item.id

    def _update_icon(self) -> None:
        if self._item.is_group:
            name = "chevron_down" if self._expanded else "chevron_right"
            icons.bind(self, name, "secondary", 14)
        else:
            icons.bind(
                self, self._item.icon or self._item.id, "accent" if self._active else "normal", 18
            )

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._update_icon()

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        self.setProperty("active", active)
        self._update_icon()
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """Sol gezinme menüsü."""

    guide_search = Signal(str)
    page_requested = Signal(str)  # menü öğesi ID'si

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        # QWidget alt sınıfı QSS zeminini ve kenarlığını ancak bu bayrakla çizer
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 12, 8, 8)
        outer.setSpacing(6)

        # Uygulama adı ve simgesi
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 6)
        brand.setSpacing(10)
        logo = QLabel(self)
        logo.setPixmap(QIcon(str(_LOGO)).pixmap(26, 26))
        brand.addWidget(logo)
        name = QLabel("Linwas", self)
        name.setObjectName("Brand")
        brand.addWidget(name, 1)
        outer.addLayout(brand)

        # Arama kutusu
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(tr("Search"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        # Enter: Windows terimini "Windows'ta nasıl?" rehberinde ara
        self._search.returnPressed.connect(
            lambda: self.guide_search.emit(self._search.text().strip())
        )
        self._search.setToolTip(tr("Press Enter to look up a Windows term"))
        outer.addWidget(self._search)

        # Kaydırılabilir menü alanı
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        self._menu_layout = QVBoxLayout(scroll_content)
        self._menu_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_layout.setSpacing(2)
        self._menu_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, 1)

        # Alt ayırıcı
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)

        # Alt menü (Ayarlar)
        self._bottom_layout = QVBoxLayout()
        self._bottom_layout.setSpacing(2)
        outer.addLayout(self._bottom_layout)

        self._buttons: list[_NavButton] = []
        self._expanded: set[str] = {"system"}  # Sistem varsayılan açık
        self._hidden: set[str] = set()  # bu sistemde gösterilmeyen öğeler
        self._active_id: str = "overview"

        self._build_menu()

    def _build_menu(self) -> None:
        layout = self._menu_layout
        # Stretch'in önüne ekle
        stretch = layout.takeAt(layout.count() - 1)

        for item in MENU:
            btn = _NavButton(item)
            btn.clicked.connect(self._on_click)
            btn.set_expanded(item.id in self._expanded)
            layout.addWidget(btn)
            self._buttons.append(btn)

            if item.is_group:
                for child in item.children:
                    child_btn = _NavButton(child, indent=1)
                    child_btn.clicked.connect(self._on_click)
                    child_btn.setVisible(item.id in self._expanded)
                    layout.addWidget(child_btn)
                    self._buttons.append(child_btn)

        layout.addItem(stretch)

        for item in BOTTOM_ITEMS:
            btn = _NavButton(item)
            btn.clicked.connect(self._on_click)
            self._bottom_layout.addWidget(btn)
            self._buttons.append(btn)

        self._refresh_active()

    def _on_click(self) -> None:
        btn = self.sender()
        if not isinstance(btn, _NavButton):
            return
        item_id = btn.item_id

        # Grup tıklaması → aç/kapa
        group = next((m for m in MENU if m.id == item_id and m.is_group), None)
        if group:
            if item_id in self._expanded:
                self._expanded.discard(item_id)
            else:
                self._expanded.add(item_id)
            self._update_visibility()
            return

        # Yaprak tıklaması → sayfa değiştir
        self._active_id = item_id
        self._refresh_active()
        self.page_requested.emit(item_id)

    def _update_visibility(self) -> None:
        for btn in self._buttons:
            if btn.objectName() == "SidebarGroup":
                btn.set_expanded(btn.item_id in self._expanded)
            # Alt menü öğesi mi? Üst grubunu bul
            parent_group = next(
                (m for m in MENU if any(c.id == btn.item_id for c in m.children)),
                None,
            )
            if parent_group:
                btn.setVisible(parent_group.id in self._expanded)
        self._apply_hidden()

    def _apply_hidden(self) -> None:
        for btn in self._buttons:
            if btn.item_id in self._hidden:
                btn.setVisible(False)

    def has_item(self, item_id: str) -> bool:
        return any(btn.item_id == item_id for btn in self._buttons)

    def add_item(self, item_id: str, label: str) -> None:
        """Eklenti sayfası için menüye öğe ekler (menünün sonuna, ayırıcıdan önce)."""
        btn = _NavButton(MenuItem(item_id, label))
        btn.clicked.connect(self._on_click)
        self._menu_layout.insertWidget(self._menu_layout.count() - 1, btn)
        self._buttons.append(btn)

    def hide_item(self, item_id: str) -> None:
        """Öğeyi menüden gizler (ör. masaüstü bilgisayarda Güç ve pil)."""
        self._hidden.add(item_id)
        self._apply_hidden()

    def _refresh_active(self) -> None:
        for btn in self._buttons:
            btn.set_active(btn.item_id == self._active_id)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for btn in self._buttons:
            if text:
                btn.setVisible(text in btn.text().lower())
            else:
                # Filtre temizlendi → normal görünürlük
                parent_group = next(
                    (m for m in MENU if any(c.id == btn.item_id for c in m.children)),
                    None,
                )
                if parent_group:
                    btn.setVisible(parent_group.id in self._expanded)
                else:
                    btn.setVisible(True)
        self._apply_hidden()

    def set_active(self, page_id: str) -> None:
        """Programatik olarak aktif sayfayı değiştirir."""
        self._active_id = page_id
        self._refresh_active()
        # İlgili grubu otomatik aç
        for m in MENU:
            if any(c.id == page_id for c in m.children):
                self._expanded.add(m.id)
                self._update_visibility()
                break


def _translation_markers() -> None:
    """Çeviri tarayıcısı için işaretleyiciler.

    MENU etiketleri dinamik olarak tr(item.label) ile çevrilir;
    AST tarayıcısı dinamik çağrıları göremez, bu yüzden
    her etiket burada açıkça referans edilir. Bu işlev hiçbir zaman çağrılmaz.
    """
    tr("AI Question")
    tr("System")
    tr("Overview")
    tr("Update center")
    tr("Wi-Fi & Bluetooth")
    tr("Backups & Rollback")
    tr("Hardware & Printers")
    tr("Task Manager")
    tr("Disk Cleanup")
    tr("Personal Backup")
    tr("Power & Battery")
    tr("Power")
    tr("Import from Windows")
    tr("All Settings")
    tr("Interface")
    tr("Windows Appearance")
    tr("Theme & Wallpaper")
    tr("Fonts")
    tr("Display & Scaling")
    tr("App Folders")
    tr("Work Groups")
    tr("Window Groups")
    tr("Software")
    tr("Troubleshooting")
    tr("How was it on Windows?")
    tr("Settings")
