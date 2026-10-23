"""Program klasörü açılır penceresi (`linwas --app-folder <kimlik> [bırakılan dosyalar]`).

Android ana ekran klasörü gibi: başlığa tıklayıp yeniden adlandır, programa tıklayıp başlat,
sürükleyerek sırala, sağ tıkla klasörden çıkar, "+" ile ekle, dışarıdan kısayol bırak.
Pencere dışına tıklanınca ya da Esc ile kapanır. Ana Linwas penceresinden bağımsız, hafif bir
süreçtir (tek kopya kuralına girmez).
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import app_folders
from linwas.backend.app_folders import AppEntry, AppFolder

COLUMNS = 4
ICON = 48
CELL = QSize(96, 92)
_REF = Qt.ItemDataRole.UserRole
_ADD = "__add__"


def tr(text: str) -> str:
    return QCoreApplication.translate("AppFolderPopup", text)


def app_icon(entry: AppEntry | None) -> QIcon:
    if entry is not None and entry.icon:
        icon = QIcon(entry.icon) if entry.icon.startswith("/") else QIcon.fromTheme(entry.icon)
        if not icon.isNull():
            return icon
    return QIcon.fromTheme("application-x-executable")


def render_folder_icon(folder: AppFolder, size: int = 256) -> None:
    """2×2 küçük program simgesinden klasör simgesi (Android klasörü gibi) yazar."""
    entries = app_folders.folder_entries(folder)[:4]
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    margin = size * 0.06
    path.addRoundedRect(
        QRectF(margin, margin, size - 2 * margin, size - 2 * margin), size * 0.22, size * 0.22
    )
    p.fillPath(path, QColor(235, 240, 248, 215))
    p.setPen(QColor(255, 255, 255, 160))
    p.drawPath(path)
    cell = (size - 2 * margin) / 2
    inner = cell * 0.62
    for i, entry in enumerate(entries):
        x = margin + (i % 2) * cell + (cell - inner) / 2
        y = margin + (i // 2) * cell + (cell - inner) / 2
        app_icon(entry).paint(p, int(x), int(y), int(inner), int(inner))
    p.end()
    target = app_folders.new_icon_path(folder.id)
    pix.save(str(target), "PNG")


def save_and_refresh(folder: AppFolder) -> None:
    """Klasörü kaydeder, simgeyi ve kısayolları yeniler."""
    app_folders.update_folder(folder)
    render_folder_icon(folder)
    app_folders.write_launchers(folder)


class AppPicker(QDialog):
    """Klasöre eklenecek programları seçme penceresi."""

    def __init__(
        self, exclude: set[str], parent: QWidget | None = None, checked: set[str] | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Add programs"))
        self.resize(420, 520)
        layout = QVBoxLayout(self)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(tr("Search programs"))
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)
        self._list = QListWidget(self)
        self._list.setIconSize(QSize(32, 32))
        for entry in app_folders.all_apps():
            if entry.ref in exclude:
                continue
            item = QListWidgetItem(app_icon(entry), entry.name)
            item.setData(_REF, entry.ref)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if entry.ref in (checked or set())
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        self._list.itemClicked.connect(self._toggle)
        layout.addWidget(self._list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Add"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle(self, item: QListWidgetItem) -> None:
        checked = item.checkState() == Qt.CheckState.Checked
        item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    def selected(self) -> list[str]:
        return [
            self._list.item(i).data(_REF)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]


class _Grid(QListWidget):
    """Simge ızgarası: içeride sürükleyerek sıralama, dışarıdan kısayol bırakma."""

    urls_dropped = Signal(list)
    order_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(ICON, ICON))
        self.setGridSize(CELL)
        self.setMovement(QListWidget.Movement.Snap)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAcceptDrops(True)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QListWidget { background: transparent; }")

    def _external(self, event: object) -> bool:
        return event.source() is not self and event.mimeData().hasUrls()  # type: ignore[attr-defined]

    def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
        if self._external(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            super().dragEnterEvent(event)  # type: ignore[arg-type]

    def dragMoveEvent(self, event: object) -> None:  # type: ignore[override]
        if self._external(event):
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            super().dragMoveEvent(event)  # type: ignore[arg-type]

    def dropEvent(self, event: object) -> None:  # type: ignore[override]
        if self._external(event):
            urls = [u.toString() for u in event.mimeData().urls()]  # type: ignore[attr-defined]
            event.acceptProposedAction()  # type: ignore[attr-defined]
            self.urls_dropped.emit(urls)
            return
        super().dropEvent(event)  # type: ignore[arg-type]
        self.order_changed.emit()


class FolderPopup(QWidget):
    def __init__(self, folder: AppFolder) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._folder = folder
        self._busy = False  # alt pencere açıkken odak kaybı kapatmasın
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(folder.name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)
        self._title = QLineEdit(folder.name, self)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setMaxLength(app_folders.MAX_NAME_LEN)
        self._title.setFrame(False)
        self._title.setStyleSheet(
            "QLineEdit { background: transparent; font-size: 16px; font-weight: 600; }"
        )
        self._title.setToolTip(tr("Click to rename the folder"))
        self._title.editingFinished.connect(self._rename)
        layout.addWidget(self._title)

        self._grid = _Grid(self)
        self._grid.itemClicked.connect(self._on_click)
        self._grid.urls_dropped.connect(self._on_urls)
        self._grid.order_changed.connect(self._on_reorder)
        self._grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._grid.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self._grid)

        hint = QLabel(tr("Drag to reorder · right-click to remove"), self)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: palette(placeholder-text); font-size: 13px;")
        layout.addWidget(hint)
        self._fill()

    # --- Görünüm ---

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().window().color()
        color.setAlpha(245)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 22, 22)
        p.fillPath(path, color)
        p.setPen(self.palette().mid().color())
        p.drawPath(path)

    def _fill(self) -> None:
        self._grid.clear()
        for entry in app_folders.folder_entries(self._folder):
            item = QListWidgetItem(app_icon(entry), entry.name)
            item.setData(_REF, entry.ref)
            item.setToolTip(entry.name)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self._grid.addItem(item)
        add = QListWidgetItem(QIcon.fromTheme("list-add"), tr("Add"))
        add.setData(_REF, _ADD)
        add.setFlags(Qt.ItemFlag.ItemIsEnabled)  # sürüklenemez, seçilemez
        add.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._grid.addItem(add)
        rows = (self._grid.count() + COLUMNS - 1) // COLUMNS
        self._grid.setFixedSize(CELL.width() * COLUMNS + 6, CELL.height() * min(rows, 4) + 6)
        self.adjustSize()

    def show_near_cursor(self) -> None:
        self.adjustSize()
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(pos.x() - self.width() // 2, area.left() + 8), area.right() - self.width() - 8)
        y = min(
            max(pos.y() - self.height() // 2, area.top() + 8), area.bottom() - self.height() - 8
        )
        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self.activateWindow()

    # --- Kapanma ---

    def keyPressEvent(self, event: object) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:  # type: ignore[attr-defined]
            self.close()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def changeEvent(self, event: object) -> None:  # type: ignore[override]
        super().changeEvent(event)  # type: ignore[arg-type]
        if (
            event.type() == event.Type.ActivationChange  # type: ignore[attr-defined]
            and not self.isActiveWindow()
            and not self._busy
        ):
            self.close()

    # --- Eylemler ---

    def _save(self) -> None:
        save_and_refresh(self._folder)

    def _rename(self) -> None:
        name = " ".join(self._title.text().split())
        if name and name != self._folder.name:
            self._folder.name = name
            self.setWindowTitle(name)
            self._save()
        elif not name:
            self._title.setText(self._folder.name)

    def _on_click(self, item: QListWidgetItem) -> None:
        ref = item.data(_REF)
        if ref == _ADD:
            self._add_programs()
            return
        entry = app_folders.app_entry(ref)
        if entry and app_folders.launch(entry):
            self.close()

    def _add_programs(self) -> None:
        self._busy = True
        try:
            picker = AppPicker(set(self._folder.apps), self)
            if picker.exec() == QDialog.DialogCode.Accepted:
                refs = [r for r in picker.selected() if r not in self._folder.apps]
                if refs:
                    self._folder.apps.extend(refs)
                    self._save()
                    self._fill()
        finally:
            self._busy = False
            self.activateWindow()

    def _on_urls(self, urls: list[str]) -> None:
        if app_folders.add_dropped(self._folder, urls):
            self._save()
            self._fill()

    def _on_reorder(self) -> None:
        refs = [self._grid.item(i).data(_REF) for i in range(self._grid.count())]
        refs = [r for r in refs if r != _ADD]
        if refs != self._folder.apps:
            self._folder.apps = refs
            self._save()
        self._fill()  # "Ekle" en sonda kalsın

    def _context_menu(self, pos: QPoint) -> None:
        item = self._grid.itemAt(pos)
        if item is None or item.data(_REF) == _ADD:
            return
        self._busy = True
        try:
            menu = QMenu(self)
            remove = menu.addAction(tr("Remove from folder"))
            if menu.exec(self._grid.mapToGlobal(pos)) is remove:
                app_folders.remove_app(self._folder, item.data(_REF))
                self._save()
                self._fill()
        finally:
            self._busy = False
            self.activateWindow()


def run(folder_id: str, dropped: list[str]) -> int:
    """`linwas --app-folder` giriş noktası."""
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Linwas")
    app.setDesktopFileName("linwas")
    from linwas.core import app_settings
    from linwas.translations import install_translator

    install_translator(app, app_settings.load().language)
    folder = app_folders.get_folder(folder_id)
    if folder is None:
        return 1
    if dropped and app_folders.add_dropped(folder, dropped):
        save_and_refresh(folder)
    popup = FolderPopup(folder)
    popup.show_near_cursor()
    return app.exec()
