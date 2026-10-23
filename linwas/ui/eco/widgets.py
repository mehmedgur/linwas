"""Eco ayar sayfalarının ortak parçaları: sayfa iskeleti ve bilgi kartı."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.core import theme


class Page(QScrollArea):
    """Başlıklı, kaydırılabilir sayfa. İçerik `self.body` düzenine eklenir."""

    def __init__(self, title: str, subtitle: str = "", edition: str = theme.EDITION_ECO) -> None:
        super().__init__()
        tokens = theme.load_tokens(edition)
        side = tokens["bosluk"]["sayfa_yatay_ic"]
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName(title)

        content = QWidget()
        content.setObjectName("pageContent")
        self.setWidget(content)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(side, 24, side, 24)
        self.body.setSpacing(tokens["bosluk"]["icerik_alanlari"])

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        self.body.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setProperty("role", "tertiary")
            self.body.addWidget(sub)
            self.body.addSpacing(8)


class InfoCard(QFrame):
    """Başlıklı kart; satırlar (etiket, değer) iki sütunlu ızgarada gösterilir."""

    def __init__(self, title: str, rows: list[tuple[str, str]]) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(12)

        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(14)
        for index, (label, value) in enumerate(rows):
            cell = QVBoxLayout()
            cell.setSpacing(2)
            name = QLabel(label)
            name.setProperty("role", "tertiary")
            text = QLabel(value)
            text.setObjectName("cardValue")
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cell.addWidget(name)
            cell.addWidget(text)
            grid.addLayout(cell, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
