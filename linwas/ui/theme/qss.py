"""QSS üretimi: palet ve ölçü tokenlarından stil sayfası (Qt'siz, test edilebilir)."""

from __future__ import annotations

from linwas.core import theme
from linwas.core.color import to_qss


def build_stylesheet(edition: str, mode: str) -> str:
    """Sürüm ve moda göre uygulama stil sayfasını üretir."""
    pal = theme.palette(edition, mode)
    tokens = theme.load_tokens(edition)
    radius = tokens["kose"]["kontrol"]
    button_height = tokens["olcu"]["dugme_yukseklik"]
    button_pad = tokens["olcu"]["dugme_yatay_ic"]
    field_height = tokens["olcu"]["metin_kutusu"]
    c = {name: to_qss(getattr(pal, name)) for name in theme.Palette.__dataclass_fields__}

    return f"""
QMainWindow, QDialog {{ background: {c["window_bg"]}; }}
QWidget {{ color: {c["text"]}; }}
QLabel {{ background: transparent; }}
QLabel[role="secondary"] {{ color: {c["text_secondary"]}; }}
QLabel[role="tertiary"] {{ color: {c["text_tertiary"]}; }}
QFrame[frameShape="4"] {{ border: none; background: {c["divider"]}; min-height: 1px;
    max-height: 1px; }}
QToolTip {{ background: {c["surface"]}; color: {c["text"]}; border: 1px solid {c["border"]};
    padding: 4px 8px; }}
QPushButton {{ min-height: {button_height}px; padding: 0 {button_pad}px; border-radius: {radius}px;
    border: 1px solid {c["border"]}; background: {c["surface"]}; color: {c["text"]}; }}
QPushButton:hover {{ background: {c["selected_bg"]}; }}
QPushButton:pressed {{ background: {c["accent_bg"]}; }}
QPushButton:disabled {{ color: {c["text_disabled"]}; }}
QPushButton[accent="true"] {{ background: {c["accent"]}; color: {c["accent_text"]};
    border: 1px solid {c["accent"]}; }}
QPushButton[accent="true"]:hover {{ background: {c["accent"]}; }}
QLineEdit {{ min-height: {field_height}px; padding: 0 {button_pad}px; border-radius: {radius}px;
    border: 1px solid {c["border"]}; background: {c["surface"]};
    selection-background-color: {c["accent"]}; selection-color: {c["accent_text"]}; }}
QLineEdit:focus {{ border: 1px solid {c["accent"]}; }}
QLineEdit:disabled {{ color: {c["text_disabled"]}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c["text_disabled"]}; border-radius: 3px;
    min-height: 24px; margin: 2px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
""".strip()
