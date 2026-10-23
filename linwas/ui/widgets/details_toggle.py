"""\"Ayrıntılar\" düğmesi: teknik bilgiyi varsayılan gizler, tıklanınca açar (süzülmüş görünüm)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QWidget

from linwas.ui import icons


class DetailsToggle(QToolButton):
    """Chevron'lu, işaretlenebilir düğme; bağlı parçaları açıp kapatır (varsayılan kapalı)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailsToggle")
        self.setText(text)
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._targets: list[QWidget] = []
        self._refresh_icon()
        self.toggled.connect(self._on_toggled)

    def add_target(self, widget: QWidget) -> None:
        """`widget`, düğme açıkken görünür, kapalıyken gizli olur."""
        self._targets.append(widget)
        widget.setVisible(self.isChecked())

    def _refresh_icon(self) -> None:
        icons.bind(self, "chevron_down" if self.isChecked() else "chevron_right", "secondary", 14)

    def _on_toggled(self, on: bool) -> None:
        for widget in self._targets:
            widget.setVisible(on)
        self._refresh_icon()
