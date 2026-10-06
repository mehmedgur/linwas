"""QSS stil sayfası üreteci.

Tasarım değerlerinden (tokens.py) QSS stringi üretir.
`app.setStyleSheet(build(theme))` ile uygulanır.
"""

from __future__ import annotations

from linwas.ui.theme.tokens import THEMES, ColorSet, Theme


def build(theme: Theme = Theme.LIGHT) -> str:
    c = THEMES.get(theme, THEMES[Theme.LIGHT])
    return _qss(c)


def _qss(c: ColorSet) -> str:
    return f"""
/* === Temel === */
QWidget {{
    font-family: "Noto Sans", sans-serif;
    font-size: 13px;
    color: {c.text_primary};
    background-color: {c.background};
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
QWidget#Sidebar {{
    background-color: {c.sidebar_bg};
    border-right: 1px solid {c.border};
}}

QPushButton#SidebarItem {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
    text-align: left;
    color: {c.text_primary};
    font-weight: normal;
}}
QPushButton#SidebarItem:hover {{
    background-color: {c.sidebar_item_hover};
}}
QPushButton#SidebarItem[active="true"] {{
    background-color: {c.sidebar_item_active};
    color: {c.accent};
    font-weight: bold;
}}

/* === Kartlar === */
QFrame#Card {{
    background-color: {c.surface};
    border: 1px solid {c.border};
    border-radius: 8px;
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

/* === Diyalog === */
QDialog {{
    background-color: {c.background};
}}

/* === Ayırıcı === */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {c.border};
}}
"""
