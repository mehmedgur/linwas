"""Programlar › Keşfet: kategorilere ayrılmış öne çıkan programlar (kart ızgarası)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import featured
from linwas.backend.flatpak import is_available as flatpak_ok
from linwas.translations import ui_language
from linwas.ui.widgets.app_card import FeaturedCard


def tr(text: str) -> str:
    return QCoreApplication.translate("DiscoverView", text)


def _category_name(cat_id: str) -> str:
    # Çeviri aracı adları görsün diye açıkça yazılır
    return {
        "all": tr("All"),
        "internet": tr("Internet"),
        "office": tr("Office"),
        "graphics": tr("Graphics & Photo"),
        "media": tr("Music & Video"),
        "communication": tr("Communication"),
        "tools": tr("Tools"),
        "education": tr("Education"),
    }.get(cat_id, cat_id)


class _ResolveWorker(QThread):
    done = Signal(list)  # list[FeaturedApp]

    def run(self) -> None:
        apps = featured.load()
        featured.resolve(apps, flatpak_ok())
        self.done.emit(apps)


class DiscoverView(QWidget):
    """Arama kutusu boşken gösterilen öne çıkan programlar."""

    # (kaynak, paket/kimlik, görünen ad); kaynak: "apt" | "flatpak" | "third-party"
    install_requested = Signal(str, str, str)

    _CARD_MIN_WIDTH = 260

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apps: list[featured.FeaturedApp] = []
        self._category = "all"
        self._columns = 0
        self._worker: _ResolveWorker | None = None
        self._lang = ui_language()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel(tr("Popular programs"), self)
        title.setObjectName("H2")
        layout.addWidget(title)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for cat_id in ("all", *featured.CATEGORIES):
            chip = QPushButton(_category_name(cat_id), self)
            chip.setObjectName("Chip")
            chip.setCheckable(True)
            chip.setChecked(cat_id == "all")
            chip.clicked.connect(lambda _=None, c=cat_id: self._set_category(c))
            self._chip_group.addButton(chip)
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)

        self._status = QLabel(tr("Loading…"), self)
        self._status.setObjectName("Secondary")
        layout.addWidget(self._status)

        self._grid_widget = QWidget(self)
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        layout.addWidget(self._grid_widget)

    def reload(self) -> None:
        """Kurulu bilgisini sistemden yeniden okur (kurulum sonrası)."""
        if self._worker and self._worker.isRunning():
            return
        self._worker = _ResolveWorker(self)
        self._worker.done.connect(self._on_loaded)
        self._worker.start()

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        if not self._apps:
            self.reload()

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        if self._apps and self._column_count() != self._columns:
            self._render()

    def _column_count(self) -> int:
        return max(1, min(4, self.width() // self._CARD_MIN_WIDTH))

    def _on_loaded(self, apps: list) -> None:
        self._apps = apps
        self._status.setVisible(not apps)
        if not apps:
            self._status.setText(tr("The program list could not be loaded."))
        self._render()

    def _set_category(self, cat_id: str) -> None:
        self._category = cat_id
        self._render()

    def _render(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._columns = self._column_count()
        for col in range(4):
            self._grid.setColumnStretch(col, 1 if col < self._columns else 0)
        shown = [a for a in self._apps if self._category in ("all", a.category)]
        for i, app in enumerate(shown):
            card = FeaturedCard(
                name=app.name,
                description=app.text.get(self._lang) or app.text.get("en", ""),
                icon=app.icon,
                source=app.source,
                installed=app.installed,
                parent=self._grid_widget,
            )
            card.install_clicked.connect(
                lambda a=app: self.install_requested.emit(a.source, a.package, a.name)
            )
            self._grid.addWidget(card, i // self._columns, i % self._columns)
