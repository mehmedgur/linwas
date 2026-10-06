"""Sağ taraftaki AI yardımcı paneli.

Konfigure edilmiş sağlayıcı yoksa panel gizlenir.
Mesaj gönderme QThread içinde çalışır; UI donmaz.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.ai.base import AIResponse, TaskSuggestion
from linwas.ai.keystore import delete_key, get_key, keyring_available, set_key
from linwas.ai.manager import ALL_PROVIDERS, AISession, available_providers, get_provider
from linwas.ai.usage import UsageDB


def tr(text: str) -> str:
    return QCoreApplication.translate("AIPanel", text)


# --- Worker ---


class _ChatWorker(QThread):
    response_ready = Signal(AIResponse)
    error = Signal(str)

    def __init__(
        self,
        session: AISession,
        text: str,
        images: list[bytes],
        include_context: bool,
    ) -> None:
        super().__init__()
        self._session = session
        self._text = text
        self._images = images
        self._include_context = include_context

    def run(self) -> None:
        try:
            resp = self._session.send(self._text, self._images, self._include_context)
            self.response_ready.emit(resp)
        except Exception as exc:
            self.error.emit(str(exc))


# --- Mesaj balonu ---


class _MessageBubble(QFrame):
    def __init__(self, text: str, is_user: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        role_lbl = QLabel(tr("You") if is_user else tr("AI"), self)
        role_lbl.setObjectName("Secondary")
        layout.addWidget(role_lbl)

        text_lbl = QLabel(text, self)
        text_lbl.setWordWrap(True)
        text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text_lbl)

        if is_user:
            self.setStyleSheet(
                "QFrame#Card { background-color: #dce6f5; border: none; border-radius: 8px; }"
            )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


class _TaskSuggestionCard(QFrame):
    """AI'ın görev önerisini gösteren kart."""

    add_to_queue = Signal(str, dict)  # (op_id, params)

    def __init__(self, suggestion: TaskSuggestion, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(
            "QFrame#Card { background-color: #e8f5e9; border: 1px solid #81c784;"
            " border-radius: 8px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        lbl = QLabel(f"💡 {suggestion.label}", self)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        op_lbl = QLabel(f"{suggestion.op_id}", self)
        op_lbl.setObjectName("Secondary")
        layout.addWidget(op_lbl)

        add_btn = QPushButton(tr("Add to Queue"), self)
        add_btn.setProperty("primary", True)
        add_btn.clicked.connect(lambda: self.add_to_queue.emit(suggestion.op_id, suggestion.params))
        layout.addWidget(add_btn)


# --- Anahtar yapılandırma diyaloğu ---


class _KeyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("AI Provider Settings"))
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        info = QLabel(
            tr("Enter API keys for AI providers. Keys are stored in the system keyring."), self
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        if not keyring_available():
            warn = QLabel(
                tr(
                    "⚠ System keyring not available. Keys will be remembered for this session only."
                ),
                self,
            )
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #9d5d00;")
            layout.addWidget(warn)

        form = QFormLayout()
        self._fields: dict[str, QLineEdit] = {}
        for provider in ALL_PROVIDERS:
            field = QLineEdit(self)
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText(tr("Paste API key here"))
            existing = get_key(provider.provider_id)
            if existing:
                field.setText(existing)
            self._fields[provider.provider_id] = field
            form.addRow(provider.display_name + ":", field)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        for pid, field in self._fields.items():
            key = field.text().strip()
            if key:
                set_key(pid, key)
            else:
                delete_key(pid)
        self.accept()


# --- Ana panel ---


class AIPanel(QWidget):
    """AI yardımcı paneli (sağ kenar)."""

    task_add_requested = Signal(str, dict)  # (op_id, params) → main_window kuyruğa ekler

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(320)

        self._session: AISession | None = None
        self._worker: _ChatWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Başlık çubuğu
        header = QWidget(self)
        header.setObjectName("StatusBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        title_lbl = QLabel(tr("AI Assistant"), header)
        title_lbl.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch(1)

        self._settings_btn = QPushButton("⚙", header)
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setToolTip(tr("AI Provider Settings"))
        self._settings_btn.clicked.connect(self._open_settings)
        header_layout.addWidget(self._settings_btn)
        outer.addWidget(header)

        # Sağlayıcı + model seçimi
        selector_widget = QWidget(self)
        selector_layout = QHBoxLayout(selector_widget)
        selector_layout.setContentsMargins(8, 6, 8, 6)
        selector_layout.setSpacing(6)

        self._provider_combo = QComboBox(self)
        self._provider_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        selector_layout.addWidget(self._provider_combo)

        self._model_combo = QComboBox(self)
        self._model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        selector_layout.addWidget(self._model_combo)
        outer.addWidget(selector_widget)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep)

        # Sohbet alanı
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._chat_content = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_content)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(8)
        self._chat_layout.addStretch(1)
        self._scroll.setWidget(self._chat_content)
        outer.addWidget(self._scroll, 1)

        sep2 = QFrame(self)
        sep2.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(sep2)

        # Alt giriş alanı
        input_widget = QWidget(self)
        input_layout = QVBoxLayout(input_widget)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(6)

        self._input = QTextEdit(self)
        self._input.setPlaceholderText(tr("Ask a question…"))
        self._input.setFixedHeight(80)
        self._input.installEventFilter(self)
        input_layout.addWidget(self._input)

        opts_row = QHBoxLayout()
        self._ctx_check = QCheckBox(tr("Add my system info"), self)
        opts_row.addWidget(self._ctx_check)
        opts_row.addStretch(1)
        input_layout.addLayout(opts_row)

        send_row = QHBoxLayout()
        send_row.addStretch(1)
        self._send_btn = QPushButton(tr("Send"), self)
        self._send_btn.setProperty("primary", True)
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._send)
        send_row.addWidget(self._send_btn)
        input_layout.addLayout(send_row)

        # Kullanım çubuğu
        self._usage_lbl = QLabel("", self)
        self._usage_lbl.setObjectName("Secondary")
        input_layout.addWidget(self._usage_lbl)

        outer.addWidget(input_widget)

        self._refresh_providers()

    # --- Sağlayıcı/model yönetimi ---

    def _refresh_providers(self) -> None:
        providers = available_providers()
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        for p in providers:
            self._provider_combo.addItem(p.display_name, p.provider_id)
        self._provider_combo.blockSignals(False)

        if providers:
            self._on_provider_changed(0)
            self._send_btn.setEnabled(True)
        else:
            self._model_combo.clear()
            self._send_btn.setEnabled(False)

    def _on_provider_changed(self, _index: int) -> None:
        provider_id = self._provider_combo.currentData()
        if not provider_id:
            return
        provider = get_provider(provider_id)
        if not provider:
            return

        api_key = get_key(provider_id)
        if not api_key:
            return

        self._model_combo.clear()
        try:
            models = provider.list_models(api_key)
            for m in models:
                self._model_combo.addItem(m)
        except Exception:
            self._model_combo.addItem("(model listesi alınamadı)")

        self._reset_session()
        self._update_usage()

    def _reset_session(self) -> None:
        provider_id = self._provider_combo.currentData()
        model = self._model_combo.currentText()
        if not provider_id or not model:
            self._session = None
            return
        provider = get_provider(provider_id)
        if not provider:
            self._session = None
            return
        self._session = AISession(provider, model)

    def _update_usage(self) -> None:
        provider_id = self._provider_combo.currentData()
        if not provider_id:
            return
        usage = UsageDB().get(provider_id)
        if usage.limit > 0:
            self._usage_lbl.setText(
                tr("{used:,} / {limit:,} tokens this month").format(
                    used=usage.total, limit=usage.limit
                )
            )
        else:
            self._usage_lbl.setText(tr("{used:,} tokens this month").format(used=usage.total))

    def _open_settings(self) -> None:
        dlg = _KeyDialog(self)
        dlg.exec()
        self._refresh_providers()

    # --- Mesaj gönderme ---

    def _send(self) -> None:
        if not self._session:
            self._reset_session()
        if not self._session:
            return

        text = self._input.toPlainText().strip()
        if not text:
            return

        self._input.clear()
        self._add_bubble(text, is_user=True)
        self._send_btn.setEnabled(False)

        worker = _ChatWorker(
            self._session,
            text,
            images=[],
            include_context=self._ctx_check.isChecked(),
        )
        worker.response_ready.connect(self._on_response)
        worker.error.connect(self._on_error)
        worker.finished.connect(lambda: self._send_btn.setEnabled(True))
        self._worker = worker
        worker.start()

    def _on_response(self, resp: AIResponse) -> None:
        self._add_bubble(resp.text, is_user=False)
        if resp.task_suggestion:
            card = _TaskSuggestionCard(resp.task_suggestion, self._chat_content)
            card.add_to_queue.connect(self.task_add_requested)
            self._chat_layout.insertWidget(self._chat_layout.count() - 1, card)
        self._update_usage()
        self._scroll_to_bottom()

    def _on_error(self, msg: str) -> None:
        err_lbl = QLabel(f"⚠ {msg}", self._chat_content)
        err_lbl.setStyleSheet("color: #c42b1c; padding: 6px;")
        err_lbl.setWordWrap(True)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, err_lbl)
        self._scroll_to_bottom()

    def _add_bubble(self, text: str, is_user: bool) -> None:
        bubble = _MessageBubble(text, is_user, self._chat_content)
        # Stretch'ten önce ekle
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())

    def eventFilter(self, obj: object, event: object) -> bool:
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        if (
            obj is self._input
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Return
            and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            self._send()
            return True
        return super().eventFilter(obj, event)

    def refresh(self) -> None:
        """Anahtarlar değiştikten sonra paneli günceller."""
        self._refresh_providers()
