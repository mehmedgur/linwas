"""QSS stil sayfası üreteci.

Tasarım değerlerinden (tokens.py) QSS stringi üretir.
`app.setStyleSheet(build(theme))` ile uygulanır.
macOS havası (12 Ekim 2026): yumuşak gri zemin, beyaz kartlar, büyük köşeler, vurgu zeminli seçim.
"""

from __future__ import annotations

from linwas.ui.theme.icon_data import asset_path
from linwas.ui.theme.tokens import (
    CARD_RADIUS,
    CORNER_RADIUS,
    FONT_SIZE_CAPTION_PX,
    FONT_SIZE_H1_PX,
    FONT_SIZE_H2_PX,
    FONT_SIZE_PX,
    FONT_SIZE_SECONDARY_PX,
    THEMES,
    ColorSet,
    Theme,
)


def build(theme: Theme = Theme.LIGHT) -> str:
    c = THEMES.get(theme, THEMES[Theme.LIGHT])
    return _qss(c)


def _qss(c: ColorSet) -> str:
    check = asset_path("check", c.text_on_accent)
    chevron = asset_path("chevron_down", c.text_secondary)
    r = CORNER_RADIUS
    rc = CARD_RADIUS
    fs = FONT_SIZE_PX
    fs2 = FONT_SIZE_SECONDARY_PX
    fs3 = FONT_SIZE_CAPTION_PX
    return f"""
/* === Temel === */
QWidget {{
    font-family: "Noto Sans", sans-serif;
    font-size: {fs}px;
    color: {c.text_primary};
    background-color: {c.background};
}}

/* Etiketler üst bileşenin zeminini göstersin (başlık şeridinde kutu görünmesin) */
QLabel {{
    background-color: transparent;
}}

/* === Kaydırma çubuğu (macOS gibi ince, yuvarlak) === */
QScrollBar:vertical {{
    width: 10px;
    background: transparent;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c.border};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.text_disabled};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
QScrollBar:horizontal {{
    height: 10px;
    background: transparent;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c.border};
    border-radius: 3px;
    min-width: 32px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0;
    background: transparent;
}}

/* === Düğmeler === */
QPushButton {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {r}px;
    padding: 7px 18px;
    min-height: 26px;
}}
QPushButton:hover {{
    background-color: {c.surface_hover};
}}
QPushButton:pressed {{
    background-color: {c.border};
}}
QPushButton:focus {{
    border-color: {c.accent};
}}
QPushButton:disabled {{
    color: {c.text_disabled};
    border-color: {c.border};
}}

QPushButton[primary="true"] {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border: 1px solid {c.accent};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background-color: {c.accent_hover};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {c.accent_pressed};
}}
QPushButton[primary="true"]:disabled {{
    background-color: {c.border};
    border-color: {c.border};
    color: {c.text_disabled};
}}
QToolButton {{
    border-radius: {r}px;
    padding: 4px;
}}

/* === Kenar çubuğu (System Settings gibi) === */
QWidget#Sidebar, QWidget#Sidebar QScrollArea, QWidget#Sidebar QScrollArea > QWidget > QWidget {{
    background-color: {c.sidebar_bg};
}}
QWidget#Sidebar {{
    border-right: 1px solid {c.border};
}}
QWidget#AIDock {{
    border-left: 1px solid {c.border};
}}
QLabel#Brand {{
    font-size: 18px;
    font-weight: bold;
    color: {c.text_primary};
}}
QWidget#Sidebar QLineEdit#SidebarSearch {{
    background-color: {c.field_bg};
    border: 1px solid {c.field_bg};
    border-radius: 9px;
    padding: 7px 12px;
}}
QWidget#Sidebar QLineEdit#SidebarSearch:focus {{
    border-color: {c.accent};
}}

QPushButton#SidebarItem {{
    background-color: transparent;
    border: none;
    border-radius: {r}px;
    padding: 6px 10px 6px 8px;
    min-height: 28px;
    text-align: left;
    color: {c.text_primary};
    font-weight: normal;
}}
QPushButton#SidebarItem:hover {{
    background-color: {c.sidebar_item_hover};
}}
QPushButton#SidebarItem[active="true"] {{
    background-color: {c.sidebar_item_active};
    color: {c.sidebar_text_active};
    font-weight: 600;
}}
QPushButton#SidebarGroup {{
    background-color: transparent;
    border: none;
    padding: 16px 10px 4px 10px;
    min-height: 16px;
    text-align: left;
    color: {c.text_secondary};
    font-size: {fs3}px;
    font-weight: bold;
}}
QPushButton#SidebarGroup:hover {{
    color: {c.text_primary};
}}

/* === Kartlar === */
QFrame#Card {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: {rc}px;
}}
QFrame#Card[clickable="true"]:hover {{
    border-color: {c.accent};
}}
QLabel#CardIcon {{
    background-color: {c.soft_accent};
    border-radius: 10px;
}}
QFrame#Card QLabel#CardIcon {{
    background-color: {c.soft_accent};
}}
/* Kart içindeki metinler kartın zeminini kullansın (genel QWidget zemini yerine).
   Saydam verilmez: seçim düğmesi/onay kutusu çerçevesi zeminle birlikte kaybolur. */
QFrame#Card QLabel, QFrame#Card QCheckBox, QFrame#Card QRadioButton,
QFrame#Card QWidget#CardRow {{
    background-color: {c.surface};
}}

/* === Durum çubuğu === */
QWidget#StatusBar {{
    background-color: {c.status_bar_bg};
    border-top: 1px solid {c.border};
}}

/* === Giriş kutuları === */
QLineEdit {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: {r}px;
    padding: 7px 12px;
    color: {c.text_primary};
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
}}
QLineEdit:focus {{
    border: 2px solid {c.accent};
    padding: 6px 11px;
}}

/* === İlerleme çubuğu === */
QProgressBar {{
    border: none;
    border-radius: 4px;
    background-color: {c.segment_bg};
    max-height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {c.accent};
    border-radius: 4px;
}}

/* === Etiketler (başlıklar) === */
QLabel#H1 {{
    font-size: {FONT_SIZE_H1_PX}px;
    font-weight: bold;
    color: {c.text_primary};
}}
QLabel#H2 {{
    font-size: {FONT_SIZE_H2_PX}px;
    font-weight: bold;
    color: {c.text_primary};
}}
QLabel#Secondary {{
    color: {c.text_secondary};
    font-size: {fs2}px;
}}

/* === Program kartları (Programlar › Keşfet / arama) === */
QLabel#AppName {{
    font-size: 17px;
    font-weight: bold;
}}
QLabel#Caption {{
    color: {c.text_secondary};
    font-size: {fs3}px;
}}
QLabel#Success {{
    color: {c.success};
    font-weight: bold;
}}
QLabel#Warning {{
    color: {c.warning};
    font-size: {fs2}px;
}}
QLabel#Pill {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {fs3}px;
    font-weight: bold;
}}
QListWidget#SettingsNav {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget#SettingsNav::item {{
    padding: 9px 12px;
    margin: 1px 8px 1px 0;
    border-radius: {r}px;
}}
QListWidget#SettingsNav::item:hover {{
    background-color: {c.sidebar_item_hover};
}}
QListWidget#SettingsNav::item:selected {{
    background-color: {c.sidebar_item_active};
    color: {c.sidebar_text_active};
    font-weight: 600;
}}
QLabel#TileNumber {{
    font-size: 34px;
    font-weight: bold;
    color: {c.success};
}}
QLabel#TileNumber[attention="true"] {{
    color: {c.accent};
}}
/* === Tüm Ayarlar (Denetim Masası) === */
QFrame#Card QToolButton#SettingLink {{
    background-color: {c.surface};
    border: 1px solid transparent;
    border-radius: {r}px;
    padding: 6px 10px;
    color: {c.accent};
    text-align: left;
}}
QFrame#Card QToolButton#SettingLink:hover {{
    background-color: {c.surface_hover};
    border-color: {c.border};
}}
QFrame#Card QToolButton#SettingLink:focus {{
    border-color: {c.accent};
}}
QFrame#Card QToolButton#SettingLink:disabled {{
    color: {c.text_disabled};
}}
QFrame#Card QToolButton#DetailsToggle {{
    background-color: {c.surface};
    border: none;
    padding: 2px 0;
    color: {c.text_secondary};
}}
QFrame#Card QToolButton#DetailsToggle:hover {{
    color: {c.accent};
}}
QFrame#Card QFrame#Separator {{
    background-color: {c.separator};
    border: none;
    max-height: 1px;
}}
QFrame#Card QLabel#CategoryIcon {{
    background-color: {c.accent};
    border-radius: 12px;
}}
QFrame#Card QLabel#LinwasTag {{
    background-color: {c.soft_accent};
    color: {c.accent};
    border-radius: 6px;
    padding: 1px 7px;
    font-size: 12px;
    font-weight: bold;
}}
QPushButton#Chip {{
    border-radius: 16px;
    padding: 6px 16px;
    min-height: 20px;
}}
QPushButton#Chip:checked {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border-color: {c.accent};
}}

/* === Metin alanları, açılır listeler, sayı kutuları === */
QTextEdit, QPlainTextEdit, QTextBrowser, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: {r}px;
    padding: 6px 10px;
    color: {c.text_primary};
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
}}
QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus {{
    border-color: {c.accent};
}}
QComboBox {{
    min-height: 26px;
    padding-right: 28px;
}}
QComboBox:hover {{
    background-color: {c.surface_hover};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox::down-arrow {{
    image: url("{chevron}");
    width: 16px;
    height: 16px;
}}
QComboBox QAbstractItemView {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: {r}px;
    padding: 4px;
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
    outline: none;
}}

/* === Onay kutusu ve seçim düğmesi === */
QCheckBox, QRadioButton {{
    spacing: 10px;
    background-color: transparent;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {c.text_disabled};
    background-color: {c.surface};
}}
QCheckBox::indicator {{
    border-radius: 5px;
}}
QRadioButton::indicator {{
    border-radius: 10px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {c.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {c.accent};
    border-color: {c.accent};
    image: url("{check}");
}}
QRadioButton::indicator:checked {{
    border: 6px solid {c.accent};
    background-color: {c.text_on_accent};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {c.text_disabled};
    background-color: {c.surface_hover};
}}

/* === Sekmeler (macOS segmented control gibi) === */
QTabWidget::pane {{
    border: none;
    top: 8px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: {c.segment_bg};
    color: {c.text_primary};
    border: 1px solid {c.segment_bg};
    padding: 7px 18px;
    margin-right: 0;
}}
QTabBar::tab:first {{
    border-top-left-radius: {r}px;
    border-bottom-left-radius: {r}px;
}}
QTabBar::tab:last {{
    border-top-right-radius: {r}px;
    border-bottom-right-radius: {r}px;
}}
QTabBar::tab:only-one {{
    border-radius: {r}px;
}}
QTabBar::tab:hover {{
    background: {c.sidebar_item_hover};
}}
QTabBar::tab:selected {{
    background: {c.surface};
    border-color: {c.border};
    border-radius: {r}px;
    font-weight: 600;
}}

/* === Listeler, ağaçlar, tablolar === */
QListView, QTreeView, QTableView, QListWidget, QTreeWidget, QTableWidget {{
    background-color: {c.surface};
    alternate-background-color: {c.surface_hover};
    border: 1px solid {c.border};
    border-radius: {rc}px;
    padding: 4px;
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
    outline: none;
}}
QListView::item, QTreeView::item {{
    padding: 6px 4px;
    border-radius: 6px;
}}
QListView::item:hover, QTreeView::item:hover {{
    background-color: {c.surface_hover};
}}
QListView::item:selected, QTreeView::item:selected {{
    background-color: {c.accent};
    color: {c.text_on_accent};
}}
QHeaderView::section {{
    background-color: {c.surface};
    color: {c.text_secondary};
    border: none;
    border-bottom: 1px solid {c.separator};
    padding: 8px 10px;
    font-size: {fs2}px;
    font-weight: bold;
}}
QTableCornerButton::section {{
    background-color: {c.surface};
    border: none;
}}

/* === Grup kutusu === */
QGroupBox {{
    border: 1px solid {c.border};
    border-radius: {rc}px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 4px;
    color: {c.text_secondary};
}}

/* === Kaydırıcı (beyaz yuvarlak tutamak) === */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c.segment_bg};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c.accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 1px solid {c.border};
    width: 18px;
    height: 18px;
    margin: -8px 0;
    border-radius: 10px;
}}

/* === Menü ve ipucu === */
QMenu {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {c.accent};
    color: {c.text_on_accent};
}}
QMenu::separator {{
    height: 1px;
    background: {c.separator};
    margin: 4px 8px;
}}
QToolTip {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: {fs2}px;
}}

/* === Diyalog === */
QDialog {{
    background-color: {c.background};
}}

/* === Ayırıcı === */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {c.separator};
}}
"""
