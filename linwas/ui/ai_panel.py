# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sağ taraftaki AI yardımcı paneli.

Konfigure edilmiş sağlayıcı yoksa panel gizlenir.
Mesaj gönderme QThread içinde çalışır; UI donmaz.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.ai import prefs as ai_prefs
from linwas.ai.base import AIResponse, Message, TaskSuggestion
from linwas.ai.chat_history import ChatHistoryDB, display_text
from linwas.ai.keystore import get_key
from linwas.ai.manager import AISession, available_providers, get_provider
from linwas.ai.model_catalog import available_curated
from linwas.ai.usage import UsageDB


def tr(text: str) -> str:
    return QCoreApplication.translate("AIPanel", text)


# --- Worker ---

# Sağlayıcı başına canlı model listesi; iki panel (yan panel, AI sayfası) ortak kullanır
_model_cache: dict[str, list[str]] = {}


class _ModelWorker(QThread):
    """Model listesini ağdan çeker; açılışta arayüz ağ yanıtını beklemesin."""

    done = Signal(str, list)  # (sağlayıcı, modeller; hata olursa boş)

    def __init__(self, provider_id: str) -> None:
        super().__init__()
        self._provider_id = provider_id

    def run(self) -> None:
        provider = get_provider(self._provider_id)
        api_key = get_key(self._provider_id)
        models: list[str] = []
        if provider and api_key:
            try:
                models = provider.list_models(api_key)
            except Exception:
                models = []
        self.done.emit(self._provider_id, models)


class _ChatWorker(QThread):
    response_ready = Signal(AIResponse)
    error = Signal(str, int)  # (mesaj, HTTP durum kodu; yoksa 0)

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
            self.error.emit(str(exc), getattr(exc, "status", None) or 0)


# --- Mesaj balonu ---


class _MessageBubble(QFrame):
    def __init__(
        self, text: str, is_user: bool, parent: QWidget | None = None, model: str = ""
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        role = tr("You") if is_user else tr("AI")
        if model and not is_user:
            role += f" · {model}"
        role_lbl = QLabel(role, self)
        role_lbl.setObjectName("Secondary")
        layout.addWidget(role_lbl)

        text_lbl = QLabel(text, self)
        text_lbl.setWordWrap(True)
        text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(text_lbl)

        if is_user:
            self.setStyleSheet(
                "QFrame#Card { background-color: #dce6f5; border: none; border-radius: 8px; }"
                " QLabel { background-color: transparent; }"
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
            " border-radius: 8px; } QLabel { background-color: transparent; }"
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


# --- Ana panel ---


_MEDALS = ("🥇", "🥈", "🥉")


def _role_text(role: str) -> str:
    return {
        "main": tr("Main model — code, error analysis, agents, long context"),
        "fast": tr("Quick and cheap tasks — coding, tool use, 1M context"),
        "hard": tr("Very hard problems — deep reasoning, complex code"),
        "free": tr("Free tier, 1M token context"),
    }.get(role, "")


def _http_error_text(status: int) -> str:
    """Sağlayıcıların ortak HTTP hata kodlarının sade açıklaması.

    Kodlar: DeepSeek hata kodları belgesi (402 = bakiye bitti) ve genel HTTP anlamları.
    """
    return {
        400: tr("The request was not accepted by the provider."),
        401: tr("The API key is wrong or has been deleted. Check it with ⚙."),
        402: tr(
            "Your account with this provider has run out of balance. Top up your "
            "balance on the provider's website, or choose another provider."
        ),
        403: tr("This API key isn't allowed to use this model or service."),
        429: tr(
            "Too many requests or your quota is used up. Wait a bit or choose another provider."
        ),
        500: tr("The provider has a server problem. Try again in a few minutes."),
        503: tr("The provider is overloaded right now. Try again in a few minutes."),
    }.get(status, "")


class AIPanel(QWidget):
    """AI yardımcı paneli (sağ kenar)."""

    task_add_requested = Signal(str, dict)  # (op_id, params) → main_window kuyruğa ekler
    conversation_saved = Signal()  # yanıt geldi, geçmiş güncellendi
    collapse_requested = Signal()  # başlıktaki "»" düğmesi
    settings_changed = Signal()  # anahtarlar/sınırlar değişti
    settings_requested = Signal()  # ⚙ → Ayarlar › Yapay zekâ açılsın

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Genişliği yan panelde ayırıcı (splitter), AI sayfasında sayfa belirler
        self.setMinimumWidth(260)

        self._session: AISession | None = None
        self._worker: _ChatWorker | None = None
        # Listesi alınamayan sağlayıcılar (yeniden denenmez; ayarlar değişince silinir)
        self._failed: set[str] = set()
        self._model_workers: list[_ModelWorker] = []
        # Son seçimler uygulama yeniden açılınca da hatırlanır
        self._prefs = ai_prefs.load()
        self._chosen_model: dict[str, str] = dict(self._prefs.models)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Başlık çubuğu
        header = QWidget(self)
        self._header = header
        header.setObjectName("StatusBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        title_lbl = QLabel(tr("AI Assistant"), header)
        title_lbl.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch(1)

        self._collapse_btn = QPushButton("»", header)
        self._collapse_btn.setFixedSize(28, 28)
        self._collapse_btn.setStyleSheet("padding: 0px; font-size: 15px;")
        self._collapse_btn.setToolTip(tr("Collapse the assistant"))
        self._collapse_btn.setAccessibleName(tr("Collapse the assistant"))
        self._collapse_btn.clicked.connect(self.collapse_requested)
        header_layout.addWidget(self._collapse_btn)

        self._settings_btn = QPushButton("⚙", header)
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setStyleSheet("padding: 0px; font-size: 15px;")
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
        self._model_combo.setToolTip(
            tr("You can switch models during a chat; the conversation continues.")
        )
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
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
        # Ayarlar › Yapay zekâ'da izin kapalıysa kullanılamaz
        from linwas.core import app_settings

        self._ctx_check.setEnabled(app_settings.load().ai_allow_system_info)
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

    def set_header_visible(self, visible: bool) -> None:
        """AI sayfasında başlık çubuğu gereksizdir (sayfanın kendi başlığı ve ayar düğmesi var)."""
        self._header.setVisible(visible)

    def _refresh_providers(self) -> None:
        current = self._provider_combo.currentData() or self._prefs.last_provider
        providers = available_providers()
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        for p in providers:
            self._provider_combo.addItem(p.display_name, p.provider_id)
        index = self._provider_combo.findData(current)
        self._provider_combo.setCurrentIndex(max(index, 0))
        self._provider_combo.blockSignals(False)

        if providers:
            self._on_provider_changed(self._provider_combo.currentIndex())
            self._send_btn.setEnabled(True)
        else:
            self._model_combo.clear()
            self._session = None
            self._send_btn.setEnabled(False)

    def _fetch_models(self, provider_id: str) -> None:
        # Biten iş parçacıkları burada bırakılır (çalışırken silinirse Qt çöker)
        self._model_workers = [w for w in self._model_workers if w.isRunning()]
        if any(w._provider_id == provider_id for w in self._model_workers):
            return
        worker = _ModelWorker(provider_id)
        worker.done.connect(self._on_models)
        self._model_workers.append(worker)
        worker.start()

    def _on_models(self, provider_id: str, models: list) -> None:
        if models:
            _model_cache[provider_id] = models
        else:
            self._failed.add(provider_id)
        if self._provider_combo.currentData() == provider_id:
            self._on_provider_changed(self._provider_combo.currentIndex())

    def _on_provider_changed(self, _index: int) -> None:
        provider_id = self._provider_combo.currentData()
        if not provider_id:
            return
        models = _model_cache.get(provider_id)
        loading = models is None and provider_id not in self._failed
        if loading:
            self._fetch_models(provider_id)
        models = models or []
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        # Seçilmiş liste varsa (ör. Gemini) yalnızca o modeller gösterilir
        curated = available_curated(provider_id, models)
        if curated:
            for i, m in enumerate(curated):
                medal = _MEDALS[i] + " " if i < len(_MEDALS) else ""
                role = _role_text(m.role)
                cost = ""
                if m.free is True:
                    cost = " · " + tr("free")
                elif m.free is False:
                    cost = " · " + tr("paid")
                self._model_combo.addItem(f"{medal}{m.label}{cost}", m.id)
                self._model_combo.setItemData(
                    i, f"{m.id}\n{role}" if role else m.id, Qt.ItemDataRole.ToolTipRole
                )
        else:
            for m in models:
                self._model_combo.addItem(m, m)
        if models:
            index = self._model_combo.findData(self._chosen_model.get(provider_id))
            self._model_combo.setCurrentIndex(max(index, 0))
        elif loading:
            # Liste gelene dek son seçilen model kullanılır; sohbet beklemeden başlayabilir
            chosen = self._chosen_model.get(provider_id)
            if chosen:
                self._model_combo.addItem(chosen, chosen)
            else:
                self._model_combo.addItem(tr("Loading models…"), "")
        else:
            self._model_combo.addItem(tr("(model list unavailable)"), "")
        self._model_combo.blockSignals(False)
        self._apply_selection()
        self._update_usage()

    def _on_model_changed(self, _index: int) -> None:
        self._apply_selection()

    def _selected(self) -> tuple[object, str] | None:
        provider = get_provider(self._provider_combo.currentData() or "")
        model = self._model_combo.currentData()
        if not provider or not model:
            return None
        return provider, model

    def _apply_selection(self) -> None:
        """Seçilen sağlayıcı/modeli oturuma uygular; sohbet geçmişi korunur."""
        selected = self._selected()
        if selected is None:
            return
        provider, model = selected
        pid = provider.provider_id  # type: ignore[attr-defined]
        self._chosen_model[pid] = model
        if self._prefs.last_provider != pid or self._prefs.models.get(pid) != model:
            self._prefs.last_provider = pid
            self._prefs.models[pid] = model
            ai_prefs.update(last_provider=pid, models=dict(self._prefs.models))
        if self._session is None:
            self._session = AISession(provider, model)  # type: ignore[arg-type]
        else:
            self._session.switch(provider, model)  # type: ignore[arg-type]

    def _reset_session(self) -> None:
        self._session = None
        self._apply_selection()

    # --- Sohbet yönetimi ---

    def _clear_chat(self) -> None:
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def new_chat(self) -> None:
        """Boş yeni sohbet başlatır (seçili model korunur)."""
        self._clear_chat()
        self._reset_session()

    @property
    def conversation_id(self) -> str:
        return self._session.conversation_id if self._session else ""

    def load_conversation(self, conv_id: str) -> bool:
        """Kayıtlı sohbeti açar; sonraki sorular seçili modele gider."""
        conv = ChatHistoryDB().load(conv_id)
        selected = self._selected()
        if conv is None:
            return False
        self._clear_chat()
        if selected is not None:
            provider, model = selected
            self._session = AISession.resume(conv, provider, model)  # type: ignore[arg-type]
            messages = self._session.messages
        else:
            # Anahtar yoksa yalnızca okunur gösterim
            self._session = None
            messages = [m for m in conv.messages if m.role != "system"]
        for msg in messages:
            self._show_message(msg)
        return True

    def _show_message(self, msg: Message) -> None:
        is_user = msg.role == "user"
        text = display_text(msg.content) if is_user else msg.content
        bubble = _MessageBubble(text, is_user, self._chat_content, model=msg.model)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def _update_usage(self) -> None:
        provider_id = self._provider_combo.currentData()
        if not provider_id:
            return
        usage = UsageDB().get(provider_id)
        if usage.limit > 0:
            text = tr("{used:,} / {limit:,} tokens this month").format(
                used=usage.total, limit=usage.limit
            )
            # Sınırın %80'ine gelince uyarı (aşılınca AISession göndermeyi durdurur)
            if usage.total >= usage.limit * 0.8:
                text = "⚠ " + text + " · " + tr("close to your monthly limit")
            self._usage_lbl.setText(text)
        else:
            self._usage_lbl.setText(tr("{used:,} tokens this month").format(used=usage.total))

    def open_settings(self) -> None:
        # AI ayarları Ayarlar sayfasında (Ayarlar › Yapay zekâ); ana pencere oraya götürür
        self.settings_requested.emit()

    _open_settings = open_settings

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
        bubble = _MessageBubble(
            resp.text,
            False,
            self._chat_content,
            model=resp.model or self._model_combo.currentData(),
        )
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self.conversation_saved.emit()
        if resp.task_suggestion:
            card = _TaskSuggestionCard(resp.task_suggestion, self._chat_content)
            card.add_to_queue.connect(self.task_add_requested)
            self._chat_layout.insertWidget(self._chat_layout.count() - 1, card)
        self._update_usage()
        self._scroll_to_bottom()

    def _on_error(self, msg: str, status: int = 0) -> None:
        friendly = _http_error_text(status)
        text = f"⚠ {friendly}\n\n{msg}" if friendly else f"⚠ {msg}"
        err_lbl = QLabel(text, self._chat_content)
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

    def ask(self, text: str) -> bool:
        """Hazır bir soruyu gönderir (ör. hata çıktısı). Sağlayıcı yoksa False."""
        if not self._send_btn.isEnabled():
            return False
        self._input.setPlainText(text)
        self._send()
        return True

    def refresh(self) -> None:
        """Anahtarlar ya da AI ayarları değiştikten sonra paneli günceller."""
        from linwas.core import app_settings

        _model_cache.clear()
        self._failed.clear()
        self._refresh_providers()
        allowed = app_settings.load().ai_allow_system_info
        self._ctx_check.setEnabled(allowed)
        if not allowed:
            self._ctx_check.setChecked(False)
        self._update_usage()
