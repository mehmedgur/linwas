"""Bluetooth cihaz ayarları: ad, otomatik bağlan; ölçüm açıksa kopma özeti (yalnızca anlamlıysa)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import network
from linwas.backend.network import BluetoothDevice
from linwas.core import netlog
from linwas.core.netlog import BluetoothSummary
from linwas.ui import icons
from linwas.ui.widgets.jobs import Jobs

# Bu kadar kopmadan azı gürültü sayılır (cihaz kapatılmış ya da uyumuş olabilir)
DROPS_NOTICE = 3
# Boştayken kendiliğinden uyuyan/kopan cihazlar: kopma bir arıza değildir, sayılmaz
SLEEPY_ICONS = ("input-mouse", "input-keyboard", "input-tablet", "input-gaming")


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkBluetooth", text)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def device_history(mac: str, now: int | None = None) -> BluetoothSummary:
    """Son 7 günün özeti (disk okur; arka plan işinde çağrılır)."""
    ts = int(time.time()) if now is None else now
    samples = netlog.load(since=ts - netlog.RETENTION_DAYS * 86400, kind=netlog.KIND_BT)
    return netlog.summarize_bluetooth(samples, mac)


def history_text(summary: BluetoothSummary, icon: str) -> str:
    """Kopma özeti; yetersiz veri, az kopma ya da uyuyan cihaz türünde boş (süzülmüş görünüm)."""
    if icon in SLEEPY_ICONS or summary.disconnects < DROPS_NOTICE:
        return ""
    return tr("The connection dropped {n} times in the last 7 days.").format(n=summary.disconnects)


def error_text(code: str) -> str:
    return {
        "too_long": tr("The name is too long (at most 64 characters)."),
    }.get(code, tr("This name is not valid."))


@dataclass
class BluetoothChange:
    """Yalnızca değişen alanlar dolu; None "değişmedi" demektir."""

    name: str | None = None  # "" cihazın kendi adına döndürür
    trusted: bool | None = None


class BluetoothDeviceDialog(QDialog):
    """Cihazın adı ve "otomatik bağlan"ı; ölçüm açıksa sık kopuyorsa bir not."""

    def __init__(self, device: BluetoothDevice, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._device = device
        self._jobs = Jobs()
        self.setWindowTitle(tr("Settings for {name}").format(name=device.name or device.mac))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel(tr("Name:"), self))
        self._name = QLineEdit(device.name, self)
        self._name.setMaxLength(network.ALIAS_MAX)
        self._initial_name = _normalize(self._name.text())  # kısaltılmış halini temel al
        layout.addWidget(self._name)
        hint = QLabel(tr("Leave empty to use the name the device reports."), self)
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._auto = QCheckBox(tr("Connect automatically when this device is nearby"), self)
        self._auto.setChecked(device.trusted)
        layout.addWidget(self._auto)

        self._history = QLabel("", self)
        self._history.setObjectName("Secondary")
        self._history.setWordWrap(True)
        self._history.setVisible(False)
        layout.addWidget(self._history)

        self._error = QLabel("", self)
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {icons.color_for('danger')};")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Kopma özeti yalnızca ölçüm açık ve veri varsa gelir; pencere beklemez
        self._jobs.run(lambda: device_history(device.mac), self._on_history)

    def _on_history(self, result: object) -> None:
        if not isinstance(result, BluetoothSummary):
            return
        text = history_text(result, self._device.icon)
        self._history.setText(text)
        self._history.setVisible(bool(text))

    def change(self) -> BluetoothChange:
        """Penceredeki seçimlerden değişiklik (adı temizlenmiş halde)."""
        change = BluetoothChange()
        name = _normalize(self._name.text())
        if name != self._initial_name:
            change.name = name
        if self._auto.isChecked() != self._device.trusted:
            change.trusted = self._auto.isChecked()
        return change

    def accept(self) -> None:
        try:
            network.validate_alias(self._name.text())
        except network.AliasError as exc:
            self._error.setText(error_text(exc.code))
            self._error.setVisible(True)
            self.adjustSize()
            return
        super().accept()
