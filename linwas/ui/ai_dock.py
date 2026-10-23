"""Sayfaların sağındaki AI yardımcısı: ayırıcıyla genişletilebilir, kapatılabilir.

Kapalıyken yer kaplamaz (dar şerit yok); kenar çubuğundaki "Yardımcı" düğmesi ya da F1 açar.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QWidget

from linwas.ai import prefs as ai_prefs
from linwas.ui.ai_panel import AIPanel


def tr(text: str) -> str:
    return QCoreApplication.translate("AIDock", text)


_MIN_WIDTH = 260
_MAX_WIDTH = 900


class AIDock(QWidget):
    """AIPanel kabı. Genişlik ve açık/kapalı durumu ~/.config/linwas/ai.json içinde hatırlanır."""

    collapsed_changed = Signal(bool)

    def __init__(self, splitter: QSplitter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AIDock")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._splitter = splitter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = AIPanel(self)
        self.panel.collapse_requested.connect(self.collapse)
        layout.addWidget(self.panel, 1)

        self._prefs = ai_prefs.load()
        self._collapsed = bool(self._prefs.panel_collapsed)
        self.panel.setVisible(not self._collapsed)
        splitter.splitterMoved.connect(self._on_splitter_moved)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def collapse(self) -> None:
        self._apply(True)

    def expand(self) -> None:
        self._apply(False)

    def toggle(self) -> None:
        self._apply(not self._collapsed)

    def _apply(self, collapsed: bool) -> None:
        changed = collapsed != self._collapsed
        self._collapsed = collapsed
        self.panel.setVisible(not collapsed)
        if not collapsed:
            self.setMinimumWidth(_MIN_WIDTH)
            self.setMaximumWidth(_MAX_WIDTH)
            if self.isVisible():
                self._resize_to(self._prefs.panel_width)
        if self._prefs.panel_collapsed != collapsed:
            self._prefs.panel_collapsed = collapsed
            ai_prefs.update(panel_collapsed=collapsed)
        if changed:
            # Ana pencere kabı gizler/gösterir; kapalıyken alanın tamamı sayfaya kalır
            self.collapsed_changed.emit(collapsed)

    def _resize_to(self, width: int) -> None:
        total = sum(self._splitter.sizes())
        self._set_width(max(_MIN_WIDTH, min(width, _MAX_WIDTH, total - 300)))

    def _set_width(self, width: int) -> None:
        sizes = self._splitter.sizes()
        index = self._splitter.indexOf(self)
        if index < 0 or len(sizes) != 2:
            return
        total = sum(sizes)
        sizes[index] = width
        sizes[1 - index] = total - width
        self._splitter.setSizes(sizes)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        # Pencere ilk gösterildiğinde kayıtlı genişlik uygulanır
        if not self._collapsed:
            self._resize_to(self._prefs.panel_width)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._collapsed or not self.isVisible():
            return
        index = self._splitter.indexOf(self)
        if index < 0:
            return
        # Ayırıcının bildirdiği boyut (widget geometrisi henüz güncellenmemiş olabilir)
        width = self._splitter.sizes()[index]
        if abs(width - self._prefs.panel_width) >= 4:
            self._prefs.panel_width = width
            ai_prefs.update(panel_width=width)


def make_content_splitter(parent: QWidget) -> QSplitter:
    splitter = QSplitter(Qt.Orientation.Horizontal, parent)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(5)
    return splitter
