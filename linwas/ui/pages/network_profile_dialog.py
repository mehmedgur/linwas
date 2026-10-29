# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kayıtlı Wi-Fi ağının ayarları: otomatik bağlan, veri kullanımı, DNS; IP "Gelişmiş" arkasında."""

from __future__ import annotations

import ipaddress

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import network
from linwas.backend.network import ProfileChange, WifiProfile
from linwas.ui import icons
from linwas.ui.widgets.details_toggle import DetailsToggle
from linwas.ui.widgets.password_row import PasswordRow


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkProfileDialog", text)


def error_text(code: str) -> str:
    """Doğrulama hata kodunun sade dille açıklaması."""
    return {
        "bad_address": tr("Enter a valid IP address, for example 192.168.1.50."),
        "bad_mask": tr("Enter a valid subnet mask, for example 255.255.255.0 (or 24)."),
        "bad_gateway": tr("Enter a valid router address, for example 192.168.1.1."),
        "gateway_outside": tr("The router address must be in the same network as the IP address."),
        "bad_dns": tr("Enter valid DNS server addresses (up to three, all different)."),
        "too_many_dns": tr("You can use at most three DNS servers."),
        "no_dns": tr(
            "With a manual IP address, choose a DNS server too (for example your router's address)."
        ),
    }.get(code, tr("These settings are not valid."))


def _mask_text(prefix: int | None) -> str:
    if prefix is None:
        return "255.255.255.0"
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


class NetworkSettingsDialog(QDialog):
    """Önce günlük kullanıcının işine yarayanlar; elle IP "Gelişmiş: IP adresi" arkasında."""

    def __init__(
        self,
        profile: WifiProfile,
        active: bool,
        parent: QWidget | None = None,
        secured: bool = False,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self.setWindowTitle(tr("Settings for {name}").format(name=profile.name))
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._auto = QCheckBox(tr("Connect automatically when this network is in range"), self)
        self._auto.setChecked(profile.autoconnect)
        layout.addWidget(self._auto)

        form = self._form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._metered = QComboBox(self)
        self._metered.addItem(tr("Let the system decide"), "unknown")
        self._metered.addItem(tr("Metered connection (limit data use)"), "yes")
        self._metered.addItem(tr("Unlimited connection"), "no")
        self._metered.setCurrentIndex(max(0, self._metered.findData(profile.metered)))
        form.addRow(tr("Data usage:"), self._metered)

        self._dns = QComboBox(self)
        self._dns.addItem(tr("Automatic (from the router)"), "auto")
        self._dns.addItem(tr("Cloudflare (1.1.1.1)"), "cloudflare")
        self._dns.addItem(tr("Google (8.8.8.8)"), "google")
        self._dns.addItem(tr("Custom…"), "custom")
        self._dns.setCurrentIndex(max(0, self._dns.findData(profile.dns_choice)))
        form.addRow(tr("DNS server:"), self._dns)
        if secured:
            # Şifre yalnızca "Göster"e basılınca okunur (süzülmüş görünüm: varsayılan gizli)
            self._password = PasswordRow(lambda: network.wifi_password(profile.name), self)
            form.addRow(tr("Password:"), self._password)
        self._dns_custom = QWidget(self)
        custom = QVBoxLayout(self._dns_custom)
        custom.setContentsMargins(0, 0, 0, 0)
        custom.setSpacing(6)
        self._dns1 = QLineEdit(self._dns_custom)
        self._dns2 = QLineEdit(self._dns_custom)
        self._dns1.setPlaceholderText(tr("Preferred DNS server"))
        self._dns2.setPlaceholderText(tr("Alternate DNS server (optional)"))
        if profile.dns_choice == "custom":
            self._dns1.setText(profile.dns[0])
            self._dns2.setText(profile.dns[1] if len(profile.dns) > 1 else "")
        custom.addWidget(self._dns1)
        custom.addWidget(self._dns2)
        form.addRow("", self._dns_custom)
        layout.addLayout(form)

        # Gelişmiş: elle IP (varsayılan kapalı; elle IP kullanan profilde açık)
        self._toggle = DetailsToggle(tr("Advanced: IP address"), self)
        layout.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self._advanced = QWidget(self)
        adv = self._adv_form = QFormLayout(self._advanced)
        adv.setContentsMargins(0, 0, 0, 0)
        adv.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._ip_mode = QComboBox(self._advanced)
        self._ip_mode.addItem(tr("Automatic (DHCP)"), "auto")
        self._ip_mode.addItem(tr("Manual"), "manual")
        self._ip_mode.setCurrentIndex(1 if profile.ipv4_method == "manual" else 0)
        adv.addRow(tr("IP address:"), self._ip_mode)
        self._address = QLineEdit(profile.address, self._advanced)
        self._address.setPlaceholderText("192.168.1.50")
        self._mask = QLineEdit(_mask_text(profile.prefix), self._advanced)
        self._gateway = QLineEdit(profile.gateway, self._advanced)
        self._gateway.setPlaceholderText("192.168.1.1")
        self._manual_rows = [
            (tr("Address:"), self._address),
            (tr("Subnet mask:"), self._mask),
            (tr("Router:"), self._gateway),
        ]
        for label, edit in self._manual_rows:
            adv.addRow(label, edit)
        self._special = QLabel(
            tr(
                "This network uses a special IP mode, so its address settings are not changed here."
            ),
            self._advanced,
        )
        self._special.setObjectName("Secondary")
        self._special.setWordWrap(True)
        adv.addRow(self._special)
        layout.addWidget(self._advanced)
        self._toggle.add_target(self._advanced)
        self._toggle.setChecked(profile.ipv4_method == "manual" or not profile.ip_editable)

        if active:
            note = QLabel(
                tr("Changes to the IP address or DNS reconnect this network for a moment."), self
            )
            note.setObjectName("Secondary")
            note.setWordWrap(True)
            layout.addWidget(note)

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

        self._dns.currentIndexChanged.connect(self._update_visibility)
        self._ip_mode.currentIndexChanged.connect(self._update_visibility)
        self._update_visibility()

    def _update_visibility(self) -> None:
        self._form.setRowVisible(self._dns_custom, self._dns.currentData() == "custom")
        editable = self._profile.ip_editable
        manual = editable and self._ip_mode.currentData() == "manual"
        self._adv_form.setRowVisible(self._ip_mode, editable)
        self._adv_form.setRowVisible(self._special, not editable)
        for _label, edit in self._manual_rows:
            self._adv_form.setRowVisible(edit, manual)

    def change(self) -> ProfileChange:
        """Penceredeki seçimlerden değişiklik; geçersizse `accept` hata gösterir."""
        return ProfileChange(
            autoconnect=self._auto.isChecked(),
            metered=str(self._metered.currentData()),
            ipv4_method=str(self._ip_mode.currentData()) if self._profile.ip_editable else None,
            address=self._address.text(),
            netmask=self._mask.text(),
            gateway=self._gateway.text(),
            dns_choice=str(self._dns.currentData()),
            dns=[self._dns1.text(), self._dns2.text()],
        )

    def accept(self) -> None:
        try:
            network.build_modify_args(self._profile.name, self.change())
        except network.ProfileError as exc:
            self._error.setText(error_text(exc.code))
            self._error.setVisible(True)
            if exc.code in ("bad_address", "bad_mask", "bad_gateway", "gateway_outside"):
                self._toggle.setChecked(True)  # hatalı alan gizli kalmasın
            return
        super().accept()
