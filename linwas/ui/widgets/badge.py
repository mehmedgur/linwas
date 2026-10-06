"""Rozet/etiket bileşeni: bildirim sayısı veya durum göstergesi."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget


class Badge(QLabel):
    """Küçük yuvarlak rozet; genellikle menü öğesi yanında gösterilir."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_style()

    def set_count(self, n: int) -> None:
        self.setText(str(n) if n > 0 else "")
        self.setVisible(n > 0)

    def _update_style(self) -> None:
        self.setStyleSheet(
            "background-color: #0067c0; color: white; border-radius: 9px;"
            " font-size: 11px; font-weight: bold; padding: 1px 6px;"
            " min-width: 18px; min-height: 18px;"
        )
