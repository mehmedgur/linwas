# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Hotspot (erişim noktası): telefon ve başka cihazlar bu bilgisayarın Wi-Fi'ına bağlanabilsin."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import network
from linwas.backend.network import HotspotInfo
from linwas.ui import icons
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.password_row import PasswordRow


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkHotspot", text)


def error_text(code: str) -> str:
    """Doğrulama hata kodunun sade dille açıklaması."""
    return {
        "bad_ssid": tr(
            "The network name is empty or too long (at most 32 bytes; letters like ş and ğ count "
            "double)."
        ),
        "bad_password": tr(
            "The password must be 8 to 63 characters long and use only basic characters "
            "(no ş, ğ, ı or emoji)."
        ),
    }.get(code, tr("These settings are not valid."))


class HotspotDialog(QDialog):
    """Hotspot açılırken ağ adı ve şifre sorar; şifre hazır önerilir, istenirse yenilenir."""

    def __init__(self, ssid: str, password: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Turn on hotspot"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            tr("Phones and other devices can join this network with the password."), self
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._ssid = QLineEdit(ssid, self)
        form.addRow(tr("Network name:"), self._ssid)
        row = QHBoxLayout()
        self._password = QLineEdit(password, self)
        new_password = QPushButton(tr("New password"), self)
        new_password.clicked.connect(
            lambda: self._password.setText(network.generate_hotspot_password())
        )
        row.addWidget(self._password, 1)
        row.addWidget(new_password)
        form.addRow(tr("Password:"), row)
        layout.addLayout(form)

        warning = QLabel(
            tr(
                "Turning on the hotspot disconnects this computer from its current Wi-Fi network. "
                "Other devices get internet only if this computer has another connection, such as "
                "a network cable."
            ),
            self,
        )
        warning.setObjectName("Secondary")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self._error = QLabel("", self)
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {icons.color_for('danger')};")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Turn on"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str]:
        return self._ssid.text().strip(), self._password.text()

    def accept(self) -> None:
        ssid, password = self.values()
        try:
            network.validate_hotspot(ssid, password)
        except network.HotspotError as exc:
            self._error.setText(error_text(exc.code))
            self._error.setVisible(True)
            self.adjustSize()  # satır sarmalı etiketler yüzünden pencere kendiliğinden büyümez
            return
        super().accept()


class HotspotCard(Card):
    """Kapalıyken tek satır ("Aç…"); açıkken ağ adı, gizli şifre ve "Kapat"."""

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info: HotspotInfo | None = None
        header = QHBoxLayout()
        heading = QLabel(tr("Hotspot"), self)
        heading.setObjectName("H2")
        header.addWidget(heading)
        header.addStretch(1)
        self._button = QPushButton("", self)
        self._button.clicked.connect(self._clicked)
        header.addWidget(self._button)
        self.layout.addLayout(header)
        self._text = QLabel("", self)
        self._text.setObjectName("Secondary")
        self._text.setWordWrap(True)
        self.layout.addWidget(self._text)
        # Şifre yalnızca "Göster"e basılınca okunur (süzülmüş görünüm: varsayılan gizli)
        self._password = PasswordRow(self._read_password, self)
        self._password.setVisible(False)
        self.layout.addWidget(self._password)
        self.show_info(None)

    @property
    def info(self) -> HotspotInfo | None:
        return self._info

    def _read_password(self) -> str | None:
        return network.wifi_password(self._info.name) if self._info else None

    def show_info(self, info: HotspotInfo | None) -> None:
        """Hotspot açık mı kapalı mı; aynı bilgiyle tekrar çağrılınca ekran değişmez."""
        if self._info is not None and (info is None or info.name != self._info.name):
            self._password.hide_password()
        self._info = info
        if info is None:
            self._text.setText(
                tr("Create a Wi-Fi network that your phone and other devices can join.")
            )
            self._button.setText(tr("Turn on…"))
        else:
            self._text.setText(tr("Other devices can join with the password below."))
            self._button.setText(tr("Turn off"))
        self._password.setVisible(info is not None)
        self._button.setEnabled(True)

    def set_busy(self) -> None:
        self._button.setEnabled(False)

    def _clicked(self) -> None:
        (self.stop_requested if self._info is not None else self.start_requested).emit()
