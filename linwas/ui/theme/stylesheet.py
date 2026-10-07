"""QSS stil sayfası üreteci.

Tasarım değerlerinden (tokens.py) QSS stringi üretir.
`app.setStyleSheet(build(theme))` ile uygulanır.
"""

from __future__ import annotations

from linwas.ui.theme.icon_data import asset_path
from linwas.ui.theme.tokens import THEMES, ColorSet, Theme


def build(theme: Theme = Theme.LIGHT) -> str:
    c = THEMES.get(theme, THEMES[Theme.LIGHT])
    return _qss(c)


def _qss(c: ColorSet) -> str:
    check = asset_path("check", c.text_on_accent)
    chevron = asset_path("chevron_down", c.text_secondary)
    return f"""
/* === Temel === */
QWidget {{
    font-family: "Noto Sans", sans-serif;
    font-size: 13px;
    color: {c.text_primary};
    background-color: {c.background};
}}

/* Etiketler üst bileşenin zeminini göstersin (başlık şeridinde kutu görünmesin) */
QLabel {{
    background-color: transparent;
}}

/* === Kaydırma çubuğu === */
QScrollBar:vertical {{
    width: 8px;
    background: transparent;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c.border};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.text_secondary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* === Düğmeler === */
QPushButton {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {c.surface_hover};
    border-color: {c.accent};
}}
QPushButton:pressed {{
    background-color: {c.border};
}}
QPushButton:disabled {{
    color: {c.text_disabled};
    border-color: {c.border};
}}

QPushButton[primary="true"] {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border: none;
    font-weight: bold;
}}
QPushButton[primary="true"]:hover {{
    background-color: {c.accent_hover};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {c.accent_pressed};
}}
QPushButton[primary="true"]:disabled {{
    background-color: {c.border};
    color: {c.text_disabled};
}}

/* === Sidebar === */
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
    font-size: 17px;
    font-weight: bold;
    color: {c.text_primary};
}}

QPushButton#SidebarItem {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 7px 10px;
    min-height: 22px;
    text-align: left;
    color: {c.text_primary};
    font-weight: normal;
}}
QPushButton#SidebarItem[indent="1"] {{
    padding-left: 22px;
}}
QPushButton#SidebarItem:hover {{
    background-color: {c.sidebar_item_hover};
}}
QPushButton#SidebarItem[active="true"] {{
    background-color: {c.sidebar_item_active};
    color: {c.accent};
    font-weight: bold;
}}
QPushButton#SidebarGroup {{
    background-color: transparent;
    border: none;
    padding: 12px 10px 4px 8px;
    min-height: 16px;
    text-align: left;
    color: {c.text_secondary};
    font-size: 12px;
    font-weight: bold;
}}
QPushButton#SidebarGroup:hover {{
    color: {c.text_primary};
}}

/* === Kartlar === */
QFrame#Card {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: 10px;
}}
QFrame#Card[clickable="true"]:hover {{
    border-color: {c.accent};
}}
QLabel#CardIcon {{
    background-color: {c.sidebar_item_active};
    border-radius: 10px;
}}
QFrame#Card QLabel#CardIcon {{
    background-color: {c.sidebar_item_active};
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
    border-radius: 6px;
    padding: 5px 10px;
    color: {c.text_primary};
}}
QLineEdit:focus {{
    border-color: {c.accent};
}}

/* === İlerleme çubuğu === */
QProgressBar {{
    border: 1px solid {c.border};
    border-radius: 4px;
    background-color: {c.surface};
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {c.accent};
    border-radius: 3px;
}}

/* === Etiketler (başlıklar) === */
QLabel#H1 {{
    font-size: 20px;
    font-weight: bold;
    color: {c.text_primary};
}}
QLabel#H2 {{
    font-size: 16px;
    font-weight: bold;
    color: {c.text_primary};
}}
QLabel#Secondary {{
    color: {c.text_secondary};
    font-size: 12px;
}}

/* === Program kartları (Programlar › Keşfet / arama) === */
QLabel#AppName {{
    font-size: 14px;
    font-weight: bold;
}}
QLabel#Caption {{
    color: {c.text_secondary};
    font-size: 11px;
}}
QLabel#Success {{
    color: {c.success};
    font-weight: bold;
}}
QLabel#Warning {{
    color: {c.warning};
    font-size: 12px;
}}
QLabel#Pill {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border-radius: 8px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: bold;
}}
QListWidget#SettingsNav {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget#SettingsNav::item {{
    padding: 8px 12px;
    margin: 1px 8px 1px 0;
    border-radius: 6px;
}}
QListWidget#SettingsNav::item:hover {{
    background-color: {c.surface_hover};
}}
QListWidget#SettingsNav::item:selected {{
    background-color: {c.surface};
    color: {c.accent};
    font-weight: bold;
    border-left: 3px solid {c.accent};
}}
QLabel#TileNumber {{
    font-size: 30px;
    font-weight: bold;
    color: {c.success};
}}
QLabel#TileNumber[attention="true"] {{
    color: {c.accent};
}}
QPushButton#Chip {{
    border-radius: 14px;
    padding: 4px 14px;
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
    border-radius: 6px;
    padding: 4px 8px;
    color: {c.text_primary};
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
}}
QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus {{
    border-color: {c.accent};
}}
QComboBox {{
    min-height: 24px;
    padding-right: 24px;
}}
QComboBox:hover {{
    border-color: {c.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: url("{chevron}");
    width: 14px;
    height: 14px;
}}
QComboBox QAbstractItemView {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    selection-background-color: {c.sidebar_item_active};
    selection-color: {c.text_primary};
    outline: none;
}}

/* === Onay kutusu ve seçim düğmesi === */
QCheckBox, QRadioButton {{
    spacing: 8px;
    background-color: transparent;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c.text_secondary};
    background-color: {c.surface};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 9px;
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
    border: 5px solid {c.accent};
    background-color: {c.text_on_accent};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {c.text_disabled};
    background-color: {c.surface_hover};
}}

/* === Sekmeler === */
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {c.border};
    top: -1px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {c.text_secondary};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 14px;
    margin-right: 4px;
}}
QTabBar::tab:hover {{
    color: {c.text_primary};
}}
QTabBar::tab:selected {{
    color: {c.text_primary};
    border-bottom-color: {c.accent};
    font-weight: bold;
}}

/* === Listeler, ağaçlar, tablolar === */
QListView, QTreeView, QTableView, QListWidget, QTreeWidget, QTableWidget {{
    background-color: {c.surface};
    alternate-background-color: {c.surface_hover};
    border: 1px solid {c.border};
    border-radius: 8px;
    selection-background-color: {c.sidebar_item_active};
    selection-color: {c.text_primary};
    outline: none;
}}
QListView::item, QTreeView::item {{
    padding: 4px;
}}
QListView::item:hover, QTreeView::item:hover {{
    background-color: {c.surface_hover};
}}
QHeaderView::section {{
    background-color: {c.surface};
    color: {c.text_secondary};
    border: none;
    border-bottom: 1px solid {c.border};
    padding: 6px 8px;
    font-weight: bold;
}}
QTableCornerButton::section {{
    background-color: {c.surface};
    border: none;
}}

/* === Grup kutusu === */
QGroupBox {{
    border: 1px solid {c.border};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {c.text_secondary};
}}

/* === Kaydırıcı === */
QSlider::groove:horizontal {{
    height: 4px;
    background: {c.border};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {c.accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c.accent};
    border: 3px solid {c.surface};
    width: 12px;
    height: 12px;
    margin: -7px 0;
    border-radius: 9px;
}}

/* === Menü ve ipucu === */
QMenu {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px 6px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {c.sidebar_item_hover};
}}
QToolTip {{
    background-color: {c.surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    padding: 4px 8px;
}}

/* === Diyalog === */
QDialog {{
    background-color: {c.background};
}}

/* === Ayırıcı === */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {c.border};
}}
"""
