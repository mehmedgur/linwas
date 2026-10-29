# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Görev Yöneticisi sayfası: süreçler ve başlangıç uygulamaları."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.process_list import ProcessInfo, kill_process, list_processes
from linwas.backend.startup import StartupApp, list_startup_apps, set_enabled
from linwas.translations import ui_language
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.fit import fit_width

_DATA = Path(__file__).resolve().parent.parent.parent / "data"

_startup_db: dict | None = None


def _get_app_info(app: StartupApp) -> dict | None:
    """startup_apps.json'dan uygulama bilgisini döner (arayüz dilinde)."""
    global _startup_db
    if _startup_db is None:
        try:
            _startup_db = json.loads((_DATA / "startup_apps.json").read_text(encoding="utf-8"))
        except Exception:
            _startup_db = {}
    # Desktop dosya adıyla eşleş (uzantısız)
    key = app.desktop_file.stem.lower()
    info = _startup_db.get(key) or next(
        (v for k, v in _startup_db.items() if k.endswith(".") and key.startswith(k)), None
    )
    if not isinstance(info, dict):
        return None
    localized = info.get(ui_language())
    return {**info, **localized} if isinstance(localized, dict) else info


def tr(text: str) -> str:
    return QCoreApplication.translate("TaskMgrPage", text)


# --- Süreç listesi sekmesi ---


class _ProcessWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(list_processes())
        except Exception:
            self.done.emit([])


class _ProcessTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(6)

        # Bilgi satırı
        info_row = QHBoxLayout()
        self._info_lbl = QLabel("", self)
        self._info_lbl.setObjectName("Secondary")
        info_row.addWidget(self._info_lbl)
        info_row.addStretch(1)
        self._kill_btn = QPushButton(tr("Force quit"), self)
        self._kill_btn.setEnabled(False)
        self._kill_btn.clicked.connect(self._kill_selected)
        info_row.addWidget(self._kill_btn)
        layout.addLayout(info_row)

        # Tablo
        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels([tr("Name"), "PID", "CPU %", tr("Memory (MB)")])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setSortingEnabled(True)
        self._tree.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._tree)

        self._worker: _ProcessWorker | None = None
        self._processes: list[ProcessInfo] = []

        # 3 saniyede bir yenile
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def _refresh(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = _ProcessWorker()
        self._worker.done.connect(self._on_data)
        self._worker.start()

    def _on_data(self, procs: object) -> None:
        self._processes = procs  # type: ignore[assignment]
        selected_pid = self._selected_pid()

        self._tree.setSortingEnabled(False)
        self._tree.clear()
        for p in self._processes:
            item = QTreeWidgetItem(
                [
                    p.name,
                    str(p.pid),
                    f"{p.cpu_pct:.1f}",
                    f"{p.rss_mb:.0f}",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, p.pid)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, p.can_kill)
            if not p.can_kill:
                for col in range(4):
                    item.setForeground(
                        col,
                        self._tree.palette().color(self._tree.palette().ColorRole.PlaceholderText),
                    )
            self._tree.addTopLevelItem(item)

        # Önceki seçimi geri yükle
        if selected_pid:
            for i in range(self._tree.topLevelItemCount()):
                it = self._tree.topLevelItem(i)
                if it and it.data(0, Qt.ItemDataRole.UserRole) == selected_pid:
                    self._tree.setCurrentItem(it)
                    break

        self._tree.setSortingEnabled(True)

        # Özet
        total_cpu = sum(p.cpu_pct for p in self._processes)
        total_mem = sum(p.rss_mb for p in self._processes)
        self._info_lbl.setText(
            tr("{n} processes — CPU: {cpu:.1f}%  RAM: {mem:.0f} MB").format(
                n=len(self._processes), cpu=total_cpu, mem=total_mem
            )
        )

    def _selected_pid(self) -> int | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def _on_selection(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            self._kill_btn.setEnabled(False)
            return
        can_kill = items[0].data(0, Qt.ItemDataRole.UserRole + 1)
        self._kill_btn.setEnabled(bool(can_kill))

    def _kill_selected(self) -> None:
        pid = self._selected_pid()
        if not pid:
            return
        proc = next((p for p in self._processes if p.pid == pid), None)
        if not proc or not proc.can_kill:
            return

        reply = QMessageBox.question(
            self,
            tr("Force quit"),
            tr("Force quit {name} (PID {pid})?").format(name=proc.name, pid=pid),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok, msg = kill_process(pid)
        if not ok:
            QMessageBox.warning(self, tr("Error"), msg)
        else:
            self._refresh()

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.start()
        super().showEvent(event)  # type: ignore[misc]

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[misc]


# --- Başlangıç uygulamaları sekmesi ---


class _StartupTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        desc = QLabel(
            tr("These apps start automatically when you log in. Disable any you don't need."),
            self,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._apps: list[StartupApp] = []
        self._loaded = False

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        # Liste sekme ilk açılınca okunur; Linwas açılışını bekletmesin
        if not self._loaded:
            self._loaded = True
            self._load()
        super().showEvent(event)  # type: ignore[misc]

    def _load(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._apps = list_startup_apps(ui_language())
        for app in self._apps:
            row = _StartupRow(app, self)
            row.toggled.connect(self._on_toggle)
            self._list_layout.addWidget(row)
            sep = QFrame(self)
            sep.setFrameShape(QFrame.Shape.HLine)
            self._list_layout.addWidget(sep)
        self._list_layout.addStretch(1)

    def _on_toggle(self, app: StartupApp, enabled: bool) -> None:
        set_enabled(app, enabled)


class _StartupRow(QWidget):
    toggled = Signal(object, bool)  # (StartupApp, enabled)

    def __init__(self, app: StartupApp, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._expanded = False
        self._info_data = _get_app_info(app)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(4)

        # Üst satır: ad + kategori + expand + toggle
        row_widget = QWidget(self)
        row_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(10)

        name_lbl = QLabel(app.name, row_widget)
        name_lbl.setStyleSheet("font-weight: bold;")
        row.addWidget(name_lbl)

        if self._info_data:
            cat_lbl = QLabel(self._info_data.get("category", ""), row_widget)
            cat_lbl.setObjectName("Secondary")
            row.addWidget(cat_lbl)

        row.addStretch(1)

        if app.system:
            sys_lbl = QLabel(tr("System"), row_widget)
            sys_lbl.setObjectName("Secondary")
            row.addWidget(sys_lbl)

        # Bilgi butonu (her satırda; veri yoksa .desktop açıklaması gösterilir)
        # Genel düğme stili 14px yan boşluk verir; küçük düğmede simge sığsın diye sıfırlanır
        self._info_btn = QPushButton(row_widget)
        self._info_btn.setFixedSize(32, 32)
        self._info_btn.setStyleSheet(
            "QPushButton { border: none; padding: 0; min-height: 0; background: transparent; }"
        )
        icons.bind(self._info_btn, "info", "accent", 20)
        self._info_btn.setAccessibleName(tr("Show info"))
        self._info_btn.setToolTip(tr("Show info"))
        self._info_btn.clicked.connect(self._toggle_info)
        row.addWidget(self._info_btn)

        self._toggle_btn = QPushButton(tr("Enabled") if app.enabled else tr("Disabled"), row_widget)
        self._toggle_btn.setProperty("primary", app.enabled)
        fit_width(self._toggle_btn, tr("Enabled"), tr("Disabled"))
        self._toggle_btn.clicked.connect(self._do_toggle)
        row.addWidget(self._toggle_btn)

        outer.addWidget(row_widget)
        # Satıra tıklamak da bilgi kartını açar/kapatır
        row_widget.mousePressEvent = lambda _e: self._toggle_info()  # type: ignore[method-assign]

        # Info kartı (başta gizli)
        self._info_card = self._build_info_card()
        self._info_card.setVisible(False)
        outer.addWidget(self._info_card)

    def _build_info_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        if self._info_data:
            desc = QLabel(self._info_data.get("description", ""), card)
            desc.setWordWrap(True)
            layout.addWidget(desc)

            impact = self._info_data.get("impact", "")
            if impact:
                safe = self._info_data.get("safe_to_disable", True)
                color = "#0e7a0e" if safe else "#c42b1c"
                impact_lbl = QLabel(f"⚠ {impact}", card)
                impact_lbl.setWordWrap(True)
                impact_lbl.setStyleSheet(f"color: {color};")
                layout.addWidget(impact_lbl)
        else:
            comment = QLabel(self._app.comment or tr("No description available."), card)
            comment.setWordWrap(True)
            layout.addWidget(comment)

        return card

    def _toggle_info(self) -> None:
        self._expanded = not self._expanded
        self._info_card.setVisible(self._expanded)

    def _do_toggle(self) -> None:
        new_state = not self._app.enabled
        self._app.enabled = new_state
        self._toggle_btn.setText(tr("Enabled") if new_state else tr("Disabled"))
        self._toggle_btn.setProperty("primary", new_state)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)
        self.toggled.emit(self._app, new_state)


# --- Ana sayfa ---


class TaskMgrPage(BasePage):
    """Görev Yöneticisi sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(12)

        title = QLabel(tr("Task Manager"), self)
        title.setObjectName("H1")
        layout.addWidget(title)

        tabs = QTabWidget(self)
        tabs.addTab(_ProcessTab(tabs), tr("Processes"))
        tabs.addTab(_StartupTab(tabs), tr("Startup"))
        layout.addWidget(tabs)
