"""Temayı uygulamaya uygular: yazı tipi, QPalette, QSS; sistem açık/koyu değişimini izler."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from linwas.core import theme
from linwas.core.color import parse_color
from linwas.ui.theme.fonts import load_bundled_fonts
from linwas.ui.theme.qss import build_stylesheet

# Kullanıcı tercihi: sistemi izle ya da elle seç
PREFERENCE_AUTO = "auto"
PREFERENCE_LIGHT = "light"
PREFERENCE_DARK = "dark"
PREFERENCES = (PREFERENCE_AUTO, PREFERENCE_LIGHT, PREFERENCE_DARK)


def qcolor(value: str) -> QColor:
    r, g, b, a = parse_color(value)
    return QColor(r, g, b, round(a * 255))


def build_qpalette(pal: theme.Palette) -> QPalette:
    """Stil sayfasının kapsamadığı widget'lar için de okunur varsayılanlar."""
    qpal = QPalette()
    roles = {
        QPalette.ColorRole.Window: pal.window_bg,
        QPalette.ColorRole.WindowText: pal.text,
        QPalette.ColorRole.Base: pal.surface,
        QPalette.ColorRole.AlternateBase: pal.surface_alt,
        QPalette.ColorRole.Text: pal.text,
        QPalette.ColorRole.Button: pal.surface,
        QPalette.ColorRole.ButtonText: pal.text,
        QPalette.ColorRole.ToolTipBase: pal.surface,
        QPalette.ColorRole.ToolTipText: pal.text,
        QPalette.ColorRole.PlaceholderText: pal.text_tertiary,
        QPalette.ColorRole.Highlight: pal.accent,
        QPalette.ColorRole.HighlightedText: pal.accent_text,
        QPalette.ColorRole.Link: pal.accent,
    }
    for role, value in roles.items():
        qpal.setColor(role, qcolor(value))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        qpal.setColor(QPalette.ColorGroup.Disabled, role, qcolor(pal.text_disabled))
    return qpal


class ThemeManager(QObject):
    """Sürüme (linwas / eco) ve açık-koyu tercihine göre temayı uygular."""

    modeChanged = Signal(str)  # "acik" / "koyu"

    def __init__(self, app: QApplication, edition: str = theme.EDITION_LINWAS) -> None:
        super().__init__(app)
        self._app = app
        self._edition = edition
        self._preference = PREFERENCE_AUTO
        self._mode = theme.MODE_LIGHT
        self._font_families: list[str] = []
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)

    @property
    def edition(self) -> str:
        return self._edition

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def preference(self) -> str:
        return self._preference

    def set_preference(self, preference: str) -> None:
        if preference not in PREFERENCES:
            raise ValueError(f"Bilinmeyen tercih: {preference!r}")
        self._preference = preference
        # Sistem renk şemasını da zorla; böylece yerel pencere süslemesi temayla uyumlu olur
        scheme = {
            PREFERENCE_AUTO: Qt.ColorScheme.Unknown,
            PREFERENCE_LIGHT: Qt.ColorScheme.Light,
            PREFERENCE_DARK: Qt.ColorScheme.Dark,
        }[preference]
        QGuiApplication.styleHints().setColorScheme(scheme)
        self.apply()

    def _on_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        self.apply()

    def _resolve_mode(self) -> str:
        if self._preference == PREFERENCE_LIGHT:
            return theme.MODE_LIGHT
        if self._preference == PREFERENCE_DARK:
            return theme.MODE_DARK
        dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        return theme.MODE_DARK if dark else theme.MODE_LIGHT

    def _apply_font(self) -> None:
        families = theme.font_families(self._edition)
        if self._edition == theme.EDITION_ECO and not self._font_families:
            self._font_families = load_bundled_fonts()
        font = QFont()
        font.setFamilies(families)
        style = theme.font_style("body", self._edition)
        font.setPixelSize(style.size)
        font.setWeight(QFont.Weight(style.weight))
        self._app.setFont(font)

    def apply(self) -> None:
        mode = self._resolve_mode()
        changed = mode != self._mode
        self._mode = mode
        self._apply_font()
        # Fusion stili: QSS ve QPalette her platformda aynı çalışsın
        self._app.setStyle("Fusion")
        self._app.setPalette(build_qpalette(theme.palette(self._edition, mode)))
        self._app.setStyleSheet(build_stylesheet(self._edition, mode))
        if changed:
            self.modeChanged.emit(mode)
