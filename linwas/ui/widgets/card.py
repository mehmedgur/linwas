"""Kart bileşeni: beyaz zemin, kenarlık, yuvarlatılmış köşe."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class Card(QFrame):
    """İçerik kartı; alt bileşenler `layout` özelliğiyle eklenir."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 18, 20, 18)
        self._layout.setSpacing(10)

    @property
    def layout(self) -> QVBoxLayout:  # type: ignore[override]
        return self._layout
