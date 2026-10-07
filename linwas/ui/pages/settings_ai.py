"""Ayarlar › Yapay zekâ: sağlayıcı başına API anahtarı, anahtar testi, aylık token sınırı,
sohbet saklama süresi ve asistanın erişim izinleri."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from linwas.ai.base import AIProvider
from linwas.ai.keystore import delete_key, get_key, keyring_available, set_key
from linwas.ai.manager import ALL_PROVIDERS
from linwas.ai.usage import UsageDB
from linwas.core import app_settings


def tr(text: str) -> str:
    return QCoreApplication.translate("AISettingsDialog", text)


class _TestWorker(QThread):
    """Anahtarı model listesini çekerek dener (token harcamaz)."""

    done = Signal(bool, str)  # (başarılı, model sayısı veya hata)

    def __init__(self, provider: AIProvider, key: str) -> None:
        super().__init__()
        self._provider = provider
        self._key = key

    def run(self) -> None:
        try:
            models = self._provider.list_models(self._key)
            self.done.emit(True, str(len(models)))
        except Exception as exc:
            self.done.emit(False, str(exc))


class _ProviderSection(QFrame):
    changed = Signal()

    def __init__(self, provider: AIProvider, usage: UsageDB, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.provider = provider
        self._worker: _TestWorker | None = None
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)

        title = QLabel(provider.display_name, self)
        title.setObjectName("H2")
        grid.addWidget(title, 0, 0, 1, 3)

        grid.addWidget(QLabel(tr("API key:"), self), 1, 0)
        self.key = QLineEdit(self)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(tr("Paste API key here"))
        self.key.setText(get_key(provider.provider_id) or "")
        self.key.setAccessibleName(tr("{name} API key").format(name=provider.display_name))
        self.key.editingFinished.connect(self._save_key)
        self._usage = usage
        grid.addWidget(self.key, 1, 1)
        buttons = QHBoxLayout()
        show = QPushButton(tr("Show"), self)
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: self.key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        buttons.addWidget(show)
        self._test_btn = QPushButton(tr("Test"), self)
        self._test_btn.clicked.connect(self._test)
        buttons.addWidget(self._test_btn)
        clear = QPushButton(tr("Delete"), self)
        clear.clicked.connect(self._delete_key)
        buttons.addWidget(clear)
        grid.addLayout(buttons, 1, 2)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        grid.addWidget(self._status, 2, 1, 1, 2)

        month = usage.get(provider.provider_id)
        grid.addWidget(QLabel(tr("Monthly limit:"), self), 3, 0)
        self.limit = QSpinBox(self)
        self.limit.setRange(0, 100_000_000)
        self.limit.setSingleStep(10_000)
        self.limit.setGroupSeparatorShown(True)
        self.limit.setSpecialValueText(tr("No limit"))
        self.limit.setSuffix(" " + tr("tokens"))
        self.limit.setValue(month.limit)
        self.limit.valueChanged.connect(self._save_limit)
        grid.addWidget(self.limit, 3, 1)
        used = QLabel(tr("Used this month: {n} tokens").format(n=f"{month.total:,}"), self)
        used.setObjectName("Secondary")
        grid.addWidget(used, 3, 2)

    def _save_key(self) -> None:
        key = self.key.text().strip()
        if key == (get_key(self.provider.provider_id) or ""):
            return
        if key:
            set_key(self.provider.provider_id, key)
        else:
            delete_key(self.provider.provider_id)
        self._status.setStyleSheet("")
        self._status.setText(tr("Saved."))
        self.changed.emit()

    def _delete_key(self) -> None:
        self.key.clear()
        self._save_key()

    def _save_limit(self, value: int) -> None:
        self._usage.set_limit(self.provider.provider_id, value)
        self.changed.emit()

    def _test(self) -> None:
        key = self.key.text().strip()
        if not key:
            self._status.setText(tr("Enter a key first."))
            return
        self._test_btn.setEnabled(False)
        self._status.setStyleSheet("")
        self._status.setText(tr("Testing…"))
        self._worker = _TestWorker(self.provider, key)
        self._worker.done.connect(self._on_tested)
        self._worker.start()

    def _on_tested(self, ok: bool, info: str) -> None:
        self._test_btn.setEnabled(True)
        if ok:
            self._status.setStyleSheet("color:#0e7a0e;")
            self._status.setText(tr("✓ Key works ({n} models available).").format(n=info))
        else:
            self._status.setStyleSheet("color:#c42b1c;")
            self._status.setText(tr("✗ Key doesn't work: {error}").format(error=info))


class AISettingsSection(QWidget):
    """Ayarlar › Yapay zekâ: sağlayıcılar (anahtar, aylık sınır), sohbet saklama, erişim izinleri.

    Değişiklikler anında kaydedilir.
    """

    changed = Signal()  # anahtar/sınır değişti → AI panelleri yenilensin

    def __init__(self, settings: app_settings.AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._usage = UsageDB()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        info = QLabel(
            tr(
                "Keys are stored in the system keyring and never written to disk as plain "
                "text. “Test” only lists models and uses no tokens."
            ),
            self,
        )
        info.setObjectName("Secondary")
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
            warn.setObjectName("Warning")
            layout.addWidget(warn)

        self._sections = [_ProviderSection(p, self._usage, self) for p in ALL_PROVIDERS]
        for section in self._sections:
            section.changed.connect(self.changed)
            layout.addWidget(section)

        # Sohbetler
        chats = QFrame(self)
        chats.setObjectName("Card")
        cl = QVBoxLayout(chats)
        cl.setContentsMargins(12, 10, 12, 10)
        h = QLabel(tr("Conversations"), chats)
        h.setObjectName("H2")
        cl.addWidget(h)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Keep conversations:"), chats))
        self._retention = QComboBox(chats)
        for value, text in (
            ("never", tr("Don't keep")),
            ("7", tr("7 days")),
            ("30", tr("30 days")),
            ("forever", tr("Always")),
        ):
            self._retention.addItem(text, value)
        self._retention.setCurrentIndex(max(self._retention.findData(settings.ai_retention), 0))
        self._retention.currentIndexChanged.connect(self._on_retention)
        row.addWidget(self._retention)
        row.addStretch(1)
        clear = QPushButton(tr("Delete all conversations"), chats)
        clear.clicked.connect(self._clear_chats)
        row.addWidget(clear)
        cl.addLayout(row)
        layout.addWidget(chats)

        # Asistanın erişimi
        access = QFrame(self)
        access.setObjectName("Card")
        al = QVBoxLayout(access)
        al.setContentsMargins(12, 10, 12, 10)
        h = QLabel(tr("What the assistant can see"), access)
        h.setObjectName("H2")
        al.addWidget(h)
        self._sysinfo = QCheckBox(
            tr("Allow adding my system information (distribution, desktop, hardware)"), access
        )
        self._sysinfo.setChecked(settings.ai_allow_system_info)
        self._sysinfo.toggled.connect(self._on_sysinfo)
        al.addWidget(self._sysinfo)
        crow = QHBoxLayout()
        crow.addWidget(QLabel(tr("Send error details to the assistant:"), access))
        self._consent = QComboBox(access)
        for value, text in (("ask", tr("Ask every time")), ("yes", tr("Yes")), ("no", tr("No"))):
            self._consent.addItem(text, value)
        self._consent.setCurrentIndex(max(self._consent.findData(settings.send_errors_to_ai), 0))
        self._consent.currentIndexChanged.connect(self._on_consent)
        crow.addWidget(self._consent)
        crow.addStretch(1)
        al.addLayout(crow)
        note = QLabel(
            tr("Personal information such as user names and addresses is hidden before sending."),
            access,
        )
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        al.addWidget(note)
        layout.addWidget(access)

    def _save(self) -> None:
        app_settings.save(self._settings)

    def _on_retention(self) -> None:
        from linwas.ai.chat_history import ChatHistoryDB

        self._settings.ai_retention = self._retention.currentData()
        self._save()
        ChatHistoryDB().apply_retention(self._settings.ai_retention)
        self.changed.emit()

    def _clear_chats(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from linwas.ai.chat_history import ChatHistoryDB

        answer = QMessageBox.question(
            self, tr("Delete all conversations"), tr("Delete all saved conversations?")
        )
        if answer == QMessageBox.StandardButton.Yes:
            ChatHistoryDB().clear_all()
            self.changed.emit()

    def _on_sysinfo(self, on: bool) -> None:
        self._settings.ai_allow_system_info = on
        self._save()
        self.changed.emit()

    def _on_consent(self) -> None:
        self._settings.send_errors_to_ai = self._consent.currentData()
        self._save()


class AISettingsDialog(QDialog):
    """Karşılama sihirbazından açılan pencere: aynı bölüm, değişiklikler anında kaydedilir."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("AI assistant"))
        self.setMinimumWidth(640)
        layout = QVBoxLayout(self)
        layout.addWidget(AISettingsSection(app_settings.load(), self))
        close = QPushButton(tr("Close"), self)
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
