"""Sol gezinme menüsü.

macOS Sistem Ayarları gibi: kategori başlıkları altında renkli simge kutulu
öğeler, arama kutusu ve altta Yardımcı/Ayarlar düğmeleri.
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
from linwas.ui.theme.tokens import METRICS, UiStyle

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
    color: str = ""  # simge kutusunun rengi (macOS düzeni)
    children: list[MenuItem] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return bool(self.children)


# Kategoriler (macOS Sistem Ayarları gibi); boş başlıklı ilk grup başlıksız en üstte durur.
# Renkler Apple'ın sistem renklerinden; kutu üstten alta hafif degradeli çizilir.
MENU: list[MenuItem] = [
    MenuItem(
        "top",
        "",
        children=[
            MenuItem("overview", "Overview", color="#0a84ff"),
            MenuItem("ai_chat", "AI Question", color="#bf5af2"),
        ],
    ),
    MenuItem(
        "system",
        "System",
        children=[
            MenuItem("updates", "Update center", color="#ff453a"),
            MenuItem("software", "Software", color="#5e5ce6"),
            MenuItem("taskmgr", "Task Manager", color="#30b158"),
            MenuItem("cleanup", "Disk Cleanup", color="#ff9f0a"),
            MenuItem("power", "Power & Battery", color="#34c759"),
        ],
    ),
    MenuItem(
        "devices",
        "Connections & Devices",
        children=[
            MenuItem("network", "Wi-Fi & Bluetooth", color="#007aff"),
            MenuItem("hardware", "Hardware & Printers", color="#8e8e93"),
            MenuItem("display", "Display & Scaling", color="#32ade6"),
        ],
    ),
    MenuItem(
        "personalize",
        "Personalization",
        children=[
            MenuItem("theme", "Theme & Wallpaper", color="#ff375f"),
            MenuItem("taskbar", "Taskbar", color="#3a3a3c"),
            MenuItem("fonts", "Fonts", color="#a2845e"),
        ],
    ),
    MenuItem(
        "organize",
        "Organize",
        children=[
            MenuItem("app_folders", "App Folders", color="#0a84ff"),
            MenuItem("workgroups", "Work Groups", color="#ff9f0a"),
            MenuItem("window_groups", "Window Groups", color="#64d2ff"),
        ],
    ),
    MenuItem(
        "backup",
        "Backup & Transfer",
        children=[
            MenuItem("backups", "Backups & Rollback", color="#30b0c7"),
            MenuItem("personal_backup", "Personal Backup", color="#007aff"),
            MenuItem("migrate", "Transfer", color="#34c759"),
        ],
    ),
    MenuItem(
        "help",
        "Help",
        children=[
            MenuItem("troubleshoot", "Troubleshooting", color="#ff9500"),
            MenuItem("guide", "How was it on Windows?", color="#0a84ff"),
            MenuItem("all_settings", "All Settings", color="#8e8e93"),
        ],
    ),
]

BOTTOM_ITEMS: list[MenuItem] = [
    # sağ paneli açar/kapatır (sayfa değil)
    MenuItem("assistant", "Assistant", icon="ai_chat", color="#bf5af2"),
    MenuItem("settings", "Settings", color="#8e8e93"),
]

_PLUGIN_COLOR = "#636366"  # eklenti sayfaları

# Geçerli düzenin ölçüleri; Sidebar.set_style() değiştirir
_metrics = METRICS[UiStyle.MACOS]


class _NavButton(QPushButton):
    def __init__(self, item: MenuItem, parent: QWidget | None = None) -> None:
        label = tr(item.label)
        if item.id == "power" and not _is_laptop():
            label = tr("Power")  # masaüstü bilgisayar: pil bölümleri yok
        super().__init__(label, parent)
        self._item = item
        self._active = False
        self.setObjectName("SidebarItem")
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._update_icon()

    @property
    def item_id(self) -> str:
        return self._item.id

    def _update_icon(self) -> None:
        name = self._item.icon or self._item.id
        if _metrics.sidebar_tiles:
            # macOS: her öğenin kendi renkli kutusu; seçiliyken de renk korunur
            icons.bind(
                self, name, f"tile:{self._item.color or _PLUGIN_COLOR}", _metrics.sidebar_icon
            )
        else:
            role = "accent" if self._active else "normal"
            icons.bind(self, name, role, _metrics.sidebar_icon)

    def set_active(self, active: bool) -> None:
        if active == self._active:
            return
        self._active = active
        self.setProperty("active", active)
        self._update_icon()
        self.style().unpolish(self)
        self.style().polish(self)


class _SectionHeader(QLabel):
    """Kategori başlığı (tıklanmaz)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SidebarSection")


class Sidebar(QWidget):
    """Sol gezinme menüsü."""

    guide_search = Signal(str)
    assistant_toggled = Signal()  # "Yardımcı" düğmesi: yapay zekâ panelini aç/kapat
    page_requested = Signal(str)  # menü öğesi ID'si

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        # QWidget alt sınıfı QSS zeminini ve kenarlığını ancak bu bayrakla çizer
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(_metrics.sidebar_width)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 16, 12, 10)
        outer.setSpacing(10)

        # Uygulama adı ve simgesi
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 4)
        brand.setSpacing(10)
        logo = QLabel(self)
        logo.setPixmap(QIcon(str(_LOGO)).pixmap(30, 30))
        brand.addWidget(logo)
        name = QLabel("Linwas", self)
        name.setObjectName("Brand")
        brand.addWidget(name, 1)
        outer.addLayout(brand)

        # Arama kutusu
        self._search = QLineEdit(self)
        self._search.setObjectName("SidebarSearch")
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

        # Alt menü (Yardımcı, Ayarlar)
        self._bottom_layout = QVBoxLayout()
        self._bottom_layout.setSpacing(2)
        outer.addLayout(self._bottom_layout)

        self._buttons: list[_NavButton] = []
        # Kategori başlığı → altındaki düğmeler (arama/gizleme sonrası boş başlık saklanır)
        self._sections: list[tuple[_SectionHeader | None, list[_NavButton]]] = []
        self._plugin_section: tuple[_SectionHeader, list[_NavButton]] | None = None
        self._hidden: set[str] = set()  # bu sistemde gösterilmeyen öğeler
        self._active_id: str = "overview"

        self._build_menu()

    def _insert(self, widget: QWidget) -> None:
        # Stretch'in önüne ekle
        self._menu_layout.insertWidget(self._menu_layout.count() - 1, widget)

    def _new_button(self, item: MenuItem) -> _NavButton:
        btn = _NavButton(item)
        btn.clicked.connect(self._on_click)
        self._buttons.append(btn)
        return btn

    def _build_menu(self) -> None:
        for group in MENU:
            header = _SectionHeader(tr(group.label)) if group.label else None
            if header is not None:
                self._insert(header)
            members = []
            for child in group.children:
                btn = self._new_button(child)
                self._insert(btn)
                members.append(btn)
            self._sections.append((header, members))

        for item in BOTTOM_ITEMS:
            self._bottom_layout.addWidget(self._new_button(item))

        self._refresh_active()

    def _on_click(self) -> None:
        btn = self.sender()
        if not isinstance(btn, _NavButton):
            return
        item_id = btn.item_id
        if item_id == "assistant":
            self.assistant_toggled.emit()
            return
        self._active_id = item_id
        self._refresh_active()
        self.page_requested.emit(item_id)

    def _update_visibility(self, text: str = "") -> None:
        for btn in self._buttons:
            visible = btn.item_id not in self._hidden
            if text and visible:
                visible = text in btn.text().lower()
            btn.setVisible(visible)
        # Bütün öğeleri gizli kategorinin başlığı da gizlenir
        for header, members in self._sections:
            if header is not None:
                header.setVisible(any(not b.isHidden() for b in members))

    def has_item(self, item_id: str) -> bool:
        return any(btn.item_id == item_id for btn in self._buttons)

    def add_item(self, item_id: str, label: str) -> None:
        """Eklenti sayfası için menüye öğe ekler ("Eklentiler" kategorisine)."""
        if self._plugin_section is None:
            header = _SectionHeader(tr("Plugins"))
            self._insert(header)
            self._plugin_section = (header, [])
            self._sections.append(self._plugin_section)
        btn = self._new_button(MenuItem(item_id, label, icon="plugin"))
        self._insert(btn)
        self._plugin_section[1].append(btn)
        self._update_visibility(self._search.text().strip().lower())

    def hide_item(self, item_id: str) -> None:
        """Öğeyi menüden gizler (ör. masaüstü bilgisayarda Güç ve pil)."""
        self._hidden.add(item_id)
        self._update_visibility(self._search.text().strip().lower())

    def _refresh_active(self) -> None:
        for btn in self._buttons:
            btn.set_active(btn.item_id == self._active_id)

    def _filter(self, text: str) -> None:
        self._update_visibility(text.strip().lower())

    def set_style(self, style: UiStyle) -> None:
        """Düzeni değiştirir (macOS: renkli simge kutuları; Windows: düz simgeler)."""
        global _metrics
        _metrics = METRICS[style]
        self.setFixedWidth(_metrics.sidebar_width)
        for btn in self._buttons:
            btn._update_icon()

    def set_active(self, page_id: str) -> None:
        """Programatik olarak aktif sayfayı değiştirir."""
        self._active_id = page_id
        self._refresh_active()


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
    tr("Transfer")
    tr("All Settings")
    tr("Connections & Devices")
    tr("Personalization")
    tr("Organize")
    tr("Backup & Transfer")
    tr("Help")
    tr("Plugins")
    tr("Theme & Wallpaper")
    tr("Fonts")
    tr("Display & Scaling")
    tr("App Folders")
    tr("Work Groups")
    tr("Window Groups")
    tr("Taskbar")
    tr("Software")
    tr("Troubleshooting")
    tr("How was it on Windows?")
    tr("Settings")
    tr("Assistant")
