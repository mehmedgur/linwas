# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Windows'tan taşıma rehberleri: şifreler, Wi-Fi, Outlook.

Wi-Fi profilleri, Windows'ta dışa aktarılan XML dosyalarından otomatik eklenir.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.wifi_import import import_profile, parse_profile


def tr(text: str) -> str:
    return QCoreApplication.translate("MigrateGuides", text)


def _tab(text: str) -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    layout = QVBoxLayout(page)
    lbl = QLabel(text, page)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(lbl.textInteractionFlags())
    layout.addWidget(lbl)
    return page, layout


class MigrateGuidesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Step-by-step guides"))
        self.setMinimumSize(560, 420)
        layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        layout.addWidget(tabs)

        page, _ = _tab(
            tr(
                "Saved passwords in Chrome or Edge can't be read from the Windows disk; they "
                "are encrypted for Windows.\n\n"
                "On Windows:\n"
                "1. Chrome: Settings › Passwords (Google Password Manager) › Settings › "
                "Export passwords. Edge: Settings › Passwords › … › Export passwords.\n"
                "2. Save the CSV file to a USB stick.\n\n"
                "On Linux:\n"
                "3. Firefox: about:logins › … › Import from a file.\n"
                "   Chrome: Settings › Passwords › Settings › Import passwords.\n"
                "4. Delete the CSV file afterwards — it contains your passwords as plain text."
            )
        )
        tabs.addTab(page, tr("Passwords"))

        page, wifi_layout = _tab(
            tr(
                "On Windows, open Command Prompt and run:\n\n"
                "    netsh wlan export profile key=clear folder=E:\\\n\n"
                "(E: is your USB stick.) Then choose those XML files here; Linwas adds the "
                "networks with their passwords. Delete the XML files afterwards."
            )
        )
        pick = QPushButton(tr("Choose Wi-Fi XML files…"), page)
        pick.setProperty("primary", True)
        pick.clicked.connect(self._import_wifi)
        wifi_layout.addWidget(pick)
        self._wifi_result = QLabel("", page)
        self._wifi_result.setWordWrap(True)
        wifi_layout.addWidget(self._wifi_result)
        wifi_layout.addStretch(1)
        tabs.addTab(page, tr("Wi-Fi"))

        page, _ = _tab(
            tr(
                "Outlook e-mails can be moved to Thunderbird.\n\n"
                "On Windows (Outlook): File › Open & Export › Import/Export › Export to a file "
                "› Outlook Data File (.pst). Save it to a USB stick.\n\n"
                "On Linux: install Thunderbird (Software page), add the “ImportExportTools NG” "
                "add-on, then use Tools › ImportExportTools NG › Import PST/mbox."
            )
        )
        tabs.addTab(page, tr("Outlook"))

        close = QPushButton(tr("Close"), self)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def _import_wifi(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Choose Wi-Fi XML files"), str(Path.home()), tr("Wi-Fi profiles (*.xml)")
        )
        lines = []
        for f in files:
            profile = parse_profile(Path(f))
            if profile is None:
                lines.append("✗ " + tr("{file}: not a Wi-Fi profile").format(file=Path(f).name))
                continue
            if not profile.supported:
                lines.append(
                    "✗ "
                    + tr("{ssid}: password missing or network type not supported").format(
                        ssid=profile.ssid
                    )
                )
                continue
            ok, msg = import_profile(profile)
            lines.append(("✓ " if ok else "✗ ") + profile.ssid + ("" if ok else f" ({msg})"))
        self._wifi_result.setText("\n".join(lines))
