"""AI ayarları: sağlayıcı başına API anahtarı, anahtar testi ve aylık token sınırı."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
        clear.clicked.connect(self.key.clear)
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
        grid.addWidget(self.limit, 3, 1)
        used = QLabel(tr("Used this month: {n} tokens").format(n=f"{month.total:,}"), self)
        used.setObjectName("Secondary")
        grid.addWidget(used, 3, 2)

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


class AISettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("AI Settings"))
        self.setMinimumWidth(620)
        self._usage = UsageDB()
        layout = QVBoxLayout(self)

        info = QLabel(
            tr(
                "Keys are stored in the system keyring and never written to disk as plain "
                "text. “Test” only lists models and uses no tokens."
            ),
            self,
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

        self._sections = [_ProviderSection(p, self._usage, self) for p in ALL_PROVIDERS]
        for section in self._sections:
            layout.addWidget(section)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        for section in self._sections:
            pid = section.provider.provider_id
            key = section.key.text().strip()
            if key:
                set_key(pid, key)
            else:
                delete_key(pid)
            self._usage.set_limit(pid, section.limit.value())
        self.accept()
