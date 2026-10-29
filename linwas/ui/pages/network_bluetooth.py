# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Bluetooth: cihaz ayarları (ad, otomatik bağlan, ses) ve bu bilgisayarın görünürlüğü.

Süzülmüş görünüm: ham profil adları gösterilmez (iki sade ses modu), kopma özeti yalnızca anlamlıysa
çıkar, güvenilmeyen cihaz dışında ek not yoktur.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import btaudio, network
from linwas.backend.btaudio import BtAudio
from linwas.backend.network import BluetoothAdapter, BluetoothDevice
from linwas.core import netlog
from linwas.core.netadvice import SLEEPY_ICONS
from linwas.core.netlog import BluetoothSummary
from linwas.ui import icons
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.jobs import Jobs

# Bu kadar kopmadan azı gürültü sayılır (cihaz kapatılmış ya da uyumuş olabilir)
DROPS_NOTICE = 3


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


def mode_text(mode: str) -> str:
    return {
        btaudio.MUSIC: tr("Music (best sound quality)"),
        btaudio.CALLS: tr("Calls (uses the microphone)"),
    }.get(mode, mode)


def error_text(code: str) -> str:
    return {
        "too_long": tr("The name is too long (at most 64 characters)."),
    }.get(code, tr("This name is not valid."))


@dataclass
class BluetoothChange:
    """Yalnızca değişen alanlar dolu; None "değişmedi" demektir."""

    name: str | None = None  # "" cihazın kendi adına döndürür
    trusted: bool | None = None
    audio_mode: str | None = None  # btaudio.MUSIC | btaudio.CALLS
    make_output: bool = False  # bu cihazı varsayılan ses çıkışı yap


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

        # Ses bölümü: yalnızca bağlı bir ses cihazıysa ve ses sunucusu kartı görüyorsa gelir
        self._audio: BtAudio | None = None
        self._sound = QWidget(self)
        sound = QVBoxLayout(self._sound)
        sound.setContentsMargins(0, 0, 0, 0)
        sound.setSpacing(6)
        sound.addWidget(QLabel(tr("Sound mode:"), self._sound))
        self._mode = QComboBox(self._sound)
        sound.addWidget(self._mode)
        self._output = QCheckBox(tr("Play sound through this device"), self._sound)
        sound.addWidget(self._output)
        self._sound.setVisible(False)
        layout.addWidget(self._sound)

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

        # Kopma özeti ve ses durumu arka planda gelir; pencere beklemez
        self._jobs.run(lambda: device_history(device.mac), self._on_history)
        if device.connected:
            self._jobs.run(lambda: btaudio.audio_info(device.mac), self._on_audio)

    def _on_history(self, result: object) -> None:
        if not isinstance(result, BluetoothSummary):
            return
        text = history_text(result, self._device.icon)
        self._history.setText(text)
        self._history.setVisible(bool(text))

    def _on_audio(self, result: object) -> None:
        if not isinstance(result, BtAudio) or not result.modes:
            return
        self._audio = result
        for mode in result.modes:
            self._mode.addItem(mode_text(mode), mode)
        self._mode.setCurrentIndex(self._mode.findData(result.mode))  # bilinmiyorsa boş kalır
        self._output.setChecked(result.is_output)
        self._output.setEnabled(not result.is_output)  # zaten çıkış: kapatılacak bir şey yok
        self._sound.setVisible(True)

    def change(self) -> BluetoothChange:
        """Penceredeki seçimlerden değişiklik (adı temizlenmiş halde)."""
        change = BluetoothChange()
        name = _normalize(self._name.text())
        if name != self._initial_name:
            change.name = name
        if self._auto.isChecked() != self._device.trusted:
            change.trusted = self._auto.isChecked()
        if self._audio is not None:
            mode = self._mode.currentData()
            if mode and mode != self._audio.mode:
                change.audio_mode = str(mode)
            change.make_output = self._output.isChecked() and not self._audio.is_output
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


class ComputerCard(Card):
    """Bu bilgisayarın Bluetooth adı ve görünürlüğü: telefonlar bilgisayarla eşleşebilsin diye."""

    visibility_requested = Signal(bool)  # True: görünür yap, False: gizle
    rename_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info: BluetoothAdapter | None = None
        header = QHBoxLayout()
        heading = QLabel(tr("This computer"), self)
        heading.setObjectName("H2")
        header.addWidget(heading)
        header.addStretch(1)
        self._rename = QPushButton(tr("Rename…"), self)
        self._rename.clicked.connect(self.rename_requested)
        header.addWidget(self._rename)
        self._toggle = QPushButton("", self)
        self._toggle.clicked.connect(self._clicked)
        header.addWidget(self._toggle)
        self.layout.addLayout(header)
        self._name = QLabel("", self)
        self._name.setWordWrap(True)
        self.layout.addWidget(self._name)
        self._state = QLabel("", self)
        self._state.setObjectName("Secondary")
        self._state.setWordWrap(True)
        self.layout.addWidget(self._state)

    @property
    def info(self) -> BluetoothAdapter | None:
        return self._info

    def show_adapter(self, info: BluetoothAdapter | None) -> None:
        self._info = info
        if info is None:
            return
        self._name.setText(
            tr("Other devices see this computer as “{name}”.").format(name=info.alias)
        )
        if info.discoverable:
            self._state.setText(tr("It is visible to nearby devices for a few minutes."))
            self._toggle.setText(tr("Hide now"))
        else:
            self._state.setText(
                tr("It is hidden from nearby devices. Make it visible to pair a phone with it.")
            )
            self._toggle.setText(tr("Make visible"))
        self._toggle.setProperty("primary", not info.discoverable)
        self._toggle.style().unpolish(self._toggle)
        self._toggle.style().polish(self._toggle)
        self._toggle.setEnabled(True)
        self._rename.setEnabled(True)

    def set_busy(self) -> None:
        self._toggle.setEnabled(False)
        self._rename.setEnabled(False)

    def _clicked(self) -> None:
        if self._info is not None:
            self.visibility_requested.emit(not self._info.discoverable)
