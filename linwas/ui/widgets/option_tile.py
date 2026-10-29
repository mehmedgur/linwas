# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Seçim kartı: yuvarlatılmış kutu içinde seçim düğmesi/onay kutusu, başlık ve açıklama.

Kutunun her yerine tıklanabilir; seçiliyken vurgu kenarlığı ve açık vurgu zemini alır
(stil: stylesheet.py › QFrame#OptionTile).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from linwas.ui import icons


class OptionTile(QFrame):
    """`checkbox=False` → seçim düğmesi (QButtonGroup'a `button` eklenir)."""

    def __init__(
        self,
        title: str,
        description: str = "",
        checkbox: bool = False,
        parent: QWidget | None = None,
        icon: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OptionTile")
        self.setProperty("clickable", True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button: QAbstractButton = QCheckBox(self) if checkbox else QRadioButton(self)
        self.button.setAccessibleName(title)
        self.button.setAccessibleDescription(description)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)
        row.addWidget(self.button, 0, Qt.AlignmentFlag.AlignTop)
        if icon:
            tile = QLabel(self)
            tile.setFixedSize(32, 32)
            icons.bind(tile, icon, "tile", 32)
            row.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        heading = QLabel(title, self)
        heading.setObjectName("OptionTitle")
        heading.setWordWrap(True)
        texts.addWidget(heading)
        if description:
            note = QLabel(description, self)
            note.setObjectName("OptionNote")
            note.setWordWrap(True)
            texts.addWidget(note)
        row.addLayout(texts, 1)

        self.button.toggled.connect(self._sync)
        self._sync(self.button.isChecked())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.button.click()
        super().mouseReleaseEvent(event)

    def _sync(self, checked: bool) -> None:
        # Seçili durum stil sayfasında [checked="true"] ile boyanır; alt bileşenler de yenilenir
        self.setProperty("checked", checked)
        for widget in (self, *self.findChildren(QWidget)):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
