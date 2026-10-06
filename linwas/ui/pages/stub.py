"""Henüz hazır olmayan sayfalar için yer tutucu."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def tr(text: str) -> str:
    return QCoreApplication.translate("StubPage", text)


class StubPage(QWidget):
    """'Yakında' yer tutucu sayfası."""

    def __init__(self, page_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel(f"{page_label}\n\n{tr('Coming soon')}", self)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setObjectName("Secondary")
        layout.addWidget(lbl)
