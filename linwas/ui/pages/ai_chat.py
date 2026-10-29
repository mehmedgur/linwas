# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Yapay Zeka Sorusu sayfası: geniş sohbet, sohbet geçmişi ve AI ayarları."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.ai.chat_history import ChatHistoryDB
from linwas.ai.manager import get_provider
from linwas.core.tasks import Task, TaskStep
from linwas.core.whitelist import ValidationError, validate
from linwas.ui.ai_panel import AIPanel
from linwas.ui.pages.base import BasePage

# QWidget'ın en büyük boyutu (QWIDGETSIZE_MAX)
_MAX_WIDTH = 16777215


def tr(text: str) -> str:
    return QCoreApplication.translate("AIChatPage", text)


def _when(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    local = QDateTime.fromSecsSinceEpoch(int(dt.timestamp()))
    return QLocale().toString(local, QLocale.FormatType.ShortFormat)


class AIChatPage(BasePage):
    """Sol: sohbet geçmişi. Sağ: sohbet (sağlayıcı/model sohbet sırasında değiştirilebilir)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history = ChatHistoryDB()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(tr("AI Question"), self)
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch(1)
        settings_btn = QPushButton(tr("AI settings"), self)
        settings_btn.setToolTip(tr("API keys and monthly token limits"))
        header.addWidget(settings_btn)
        layout.addLayout(header)

        hint = QLabel(
            tr(
                "Ask anything about your computer. Suggested actions are only added to the "
                "queue; nothing runs until you press Apply."
            ),
            self,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        body = QHBoxLayout()
        body.setSpacing(12)

        # Sol: geçmiş
        side = QVBoxLayout()
        new_btn = QPushButton(tr("+ New chat"), self)
        new_btn.setProperty("primary", True)
        new_btn.clicked.connect(self._new_chat)
        side.addWidget(new_btn)
        lbl = QLabel(tr("Previous chats"), self)
        lbl.setObjectName("Secondary")
        side.addWidget(lbl)
        self._list = QListWidget(self)
        self._list.setAccessibleName(tr("Previous chats"))
        self._list.setSpacing(4)
        self._list.setWordWrap(True)
        self._list.itemActivated.connect(self._open_item)
        self._list.itemClicked.connect(self._open_item)
        side.addWidget(self._list, 1)
        row = QHBoxLayout()
        delete_btn = QPushButton(tr("Delete"), self)
        delete_btn.clicked.connect(self._delete_selected)
        row.addWidget(delete_btn)
        clear_btn = QPushButton(tr("Delete all"), self)
        clear_btn.clicked.connect(self._delete_all)
        row.addWidget(clear_btn)
        side.addLayout(row)
        side_widget = QWidget(self)
        side_widget.setLayout(side)
        side_widget.setFixedWidth(260)
        body.addWidget(side_widget)

        # Sağ: sohbet
        self._panel = AIPanel(self)
        # Yan paneldeki sabit genişlik burada kaldırılır
        self._panel.setMinimumWidth(0)
        self._panel.setMaximumWidth(_MAX_WIDTH)
        self._panel.set_header_visible(False)
        self._panel.task_add_requested.connect(self._on_task)
        self._panel.conversation_saved.connect(self._reload_list)
        body.addWidget(self._panel, 1)
        layout.addLayout(body, 1)

        settings_btn.clicked.connect(self._panel.open_settings)
        self._reload_list()

    # --- Geçmiş ---

    def _reload_list(self) -> None:
        current = self._panel.conversation_id
        self._list.clear()
        for conv in self._history.list(limit=100):
            provider = get_provider(conv.provider)
            pname = provider.display_name if provider else conv.provider
            item = QListWidgetItem(
                f"{conv.title or tr('(empty chat)')}\n{_when(conv.updated_at)} · {pname}"
            )
            item.setData(Qt.ItemDataRole.UserRole, conv.id)
            item.setToolTip(f"{pname} · {conv.model}")
            self._list.addItem(item)
            if conv.id == current:
                item.setSelected(True)

    def _open_item(self, item: QListWidgetItem) -> None:
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if conv_id and conv_id != self._panel.conversation_id:
            self._panel.load_conversation(conv_id)

    def _new_chat(self) -> None:
        self._panel.new_chat()
        self._list.clearSelection()

    def _confirm(self, text: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, tr("Delete"), text, parent=self)
        yes = box.addButton(tr("Delete"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def _delete_selected(self) -> None:
        item = self._list.currentItem()
        if not item or not self._confirm(tr("Delete this chat?")):
            return
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        self._history.delete(conv_id)
        if conv_id == self._panel.conversation_id:
            self._panel.new_chat()
        self._reload_list()

    def _delete_all(self) -> None:
        if self._list.count() == 0 or not self._confirm(
            tr("Delete all chats? This cannot be undone.")
        ):
            return
        self._history.clear_all()
        self._panel.new_chat()
        self._reload_list()

    # --- Görev önerisi ---

    def _on_task(self, op_id: str, params: dict) -> None:
        clean = {str(k): str(v) for k, v in params.items()}
        try:
            # AI önerisi kuyruğa girmeden izin listesine karşı doğrulanır
            validate(op_id, clean)
            step = TaskStep(op_id=op_id, params=clean)
            self.task_requested.emit(Task(label=step.label, steps=[step]))
        except ValidationError as exc:
            QMessageBox.warning(self, "Linwas", str(exc))
