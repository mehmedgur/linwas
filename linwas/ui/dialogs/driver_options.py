# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sürücü sürüm seçimi ("Diğer seçenekler") ve Secure Boot şifre pencereleri."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.driver_options import DriverOption


def tr(text: str) -> str:
    return QCoreApplication.translate("DriverOptionsDialog", text)


def option_label(option: DriverOption) -> str:
    if not option.package:
        text = tr("Open-source driver (nouveau)")
    else:
        text = option.package
        if option.version:
            text += f" ({option.version})"
        if option.open_kernel:
            text += " · " + tr("open kernel modules")
        if "legacy" in option.package:
            text += " · " + tr("only for older cards")
    tags = []
    if option.recommended:
        tags.append(tr("Recommended"))
    if option.installed:
        tags.append(tr("In use"))
    return text + (" — " + ", ".join(tags) if tags else "")


class DriverOptionsDialog(QDialog):
    """Seçenekler arasından birini seçtirir; `selected` sonuç."""

    def __init__(self, device: str, options: list[DriverOption], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("Choose a driver"))
        self.setMinimumWidth(520)
        self.selected: DriverOption | None = None
        self._options = options
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        head = QLabel(device, self)
        head.setObjectName("H2")
        head.setWordWrap(True)
        layout.addWidget(head)
        info = QLabel(
            tr(
                "The recommended driver suits most computers. Choose another version only if "
                "the recommended one causes problems. A system backup is taken first when "
                "Timeshift is installed, and you can return to the previous driver later."
            ),
            self,
        )
        info.setObjectName("Secondary")
        info.setWordWrap(True)
        layout.addWidget(info)
        self._group = QButtonGroup(self)
        for i, option in enumerate(options):
            radio = QRadioButton(option_label(option), self)
            radio.setChecked(option.installed)
            self._group.addButton(radio, i)
            layout.addWidget(radio)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(tr("Apply"), self)
        ok.setProperty("primary", True)
        ok.clicked.connect(self._accept)
        row.addWidget(ok)
        cancel = QPushButton(tr("Cancel"), self)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

    def _accept(self) -> None:
        index = self._group.checkedId()
        if index < 0:
            return
        option = self._options[index]
        if option.installed:
            self.reject()  # zaten kullanılıyor
            return
        self.selected = option
        self.accept()


def confirm_mok_password(password: str, parent: QWidget | None = None) -> bool:
    """Secure Boot açıkken tek kullanımlık şifreyi gösterir; kullanıcı not ettiyse True."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(tr("Secure Boot"))
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(
        tr("Secure Boot is on. Write down this one-time password:")
        + f"<p style='font-size:28px; font-weight:bold; letter-spacing:4px'>{password}</p>"
    )
    box.setInformativeText(
        tr(
            "For the driver to work, its signing key must be registered. When the computer "
            "restarts, a blue screen (MOK management) appears:\n"
            "1. Choose “Enroll MOK”, then “Continue” and “Yes”.\n"
            "2. Type the password above (the numbers do not appear while typing).\n"
            "3. Choose “Reboot”.\n"
            "If you miss the screen, the driver will not load; you can register the key "
            "again from the Drivers page."
        )
    )
    ok = box.addButton(tr("I wrote it down, continue"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is ok
