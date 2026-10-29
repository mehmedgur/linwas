# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Windows programı (.exe/.msi) açma: risk analizi, Linux alternatifi, Bottles/Wine ile açma."""

from __future__ import annotations

import html
from urllib.parse import urlparse

from PySide6.QtCore import QCoreApplication, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.exe_inspect import ExeInfo, virustotal_url
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("ExeOpenDialog", text)


def _reason_texts() -> dict[str, str]:
    return {
        "not_windows_program": tr("This is not a valid Windows program. Don't open it."),
        "disguised": tr(
            "The file name hides its real type (for example document.pdf.exe). Harmful "
            "files often use this trick."
        ),
        "arm": tr("Made for ARM processors; it will not work on this computer."),
        "unsigned": tr("It has no digital signature, so its maker can't be confirmed."),
        "unknown_publisher": tr("The maker's name is not written in the file."),
    }


def _installer_text(info: ExeInfo) -> str:
    names = {
        "inno": "Inno Setup",
        "nsis": "NSIS",
        "msi": "Windows Installer (MSI)",
        "installshield": "InstallShield",
        "wix": "WiX",
    }
    if info.installer:
        return tr("Setup program ({kind})").format(kind=names.get(info.installer, info.installer))
    return tr("Program")


class ExeOpenDialog(QDialog):
    """Sonuç: `action` ("run" | "install_wine" | "install_bottles" | "alternative" | ""),
    `separate` (Wine) ve `gaming` (Bottles oyun profili)."""

    def __init__(
        self,
        info: ExeInfo,
        alternative: tuple[str, dict],
        wine_ok: bool,
        parent: QWidget | None = None,
        engine: str = "wine",  # "bottles" | "wine"
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Open a Windows program"))
        self.setMinimumWidth(560)
        self.action = ""
        self.separate = False
        self.gaming = False
        self._info = info
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        if info.error:
            layout.addWidget(
                QLabel(tr("This file can't be read: {error}").format(error=info.error))
            )
            self._add_close(layout)
            return

        title = QLabel(html.escape(info.display_name) + (f"  {html.escape(info.version)}"), self)
        title.setObjectName("H2")
        title.setWordWrap(True)
        layout.addWidget(title)

        facts = [_installer_text(info)]
        if info.arch in ("x86", "x64"):
            facts.append(tr("64-bit") if info.arch == "x64" else tr("32-bit"))
        facts.append(f"{info.size / 1024 / 1024:.1f} MB")
        made_by = info.company or tr("unknown")
        facts.append(tr("Made by: {who}").format(who=html.escape(made_by)))
        sub = QLabel(" · ".join(facts), self)
        sub.setObjectName("Secondary")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        if info.origin_url:
            host = urlparse(info.origin_url).hostname or info.origin_url
            origin = QLabel(tr("Downloaded from: {site}").format(site=html.escape(host)), self)
            origin.setObjectName("Secondary")
            origin.setToolTip(info.origin_url)
            layout.addWidget(origin)

        # Risk
        risk_text = {
            "low": (tr("Low risk"), "#0e7a0e"),
            "medium": (tr("Medium risk — open only if you trust where it came from"), "#9d5d00"),
            "high": (tr("High risk"), "#c42b1c"),
        }[info.risk]
        risk = QLabel(risk_text[0], self)
        risk.setStyleSheet(f"color:{risk_text[1]}; font-weight:bold;")
        layout.addWidget(risk)

        texts = _reason_texts()
        lines = [f"• {texts[r]}" for r in info.reasons if r in texts]
        if info.signed:
            lines.append(
                "• " + tr("It has a digital signature (Linux can't check if it is valid).")
            )
        if info.dotnet:
            lines.append(
                "• " + tr(".NET program: Wine may need extra parts and it may not work well.")
            )
        if lines:
            details = QLabel("<br>".join(lines), self)
            details.setTextFormat(Qt.TextFormat.RichText)
            details.setWordWrap(True)
            layout.addWidget(details)

        # VirusTotal: yalnızca özet gönderilir, kullanıcı isterse
        vt_row = QHBoxLayout()
        sha = QLabel(f"SHA256: {info.sha256[:16]}…", self)
        sha.setObjectName("Secondary")
        sha.setToolTip(info.sha256)
        sha.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vt_row.addWidget(sha, 1)
        vt_btn = QPushButton(tr("Check on VirusTotal"), self)
        vt_btn.setToolTip(
            tr("Opens VirusTotal in your browser. Only the file's fingerprint is sent.")
        )
        vt_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(virustotal_url(info.sha256))))
        vt_row.addWidget(vt_btn)
        layout.addLayout(vt_row)

        # Linux alternatifi
        key, alt = alternative
        if key:
            card = Card(self)
            apps = ", ".join(alt.get("apt", []) + alt.get("flatpak", [])[:1])
            note = QLabel(
                tr(
                    "{program} has Linux alternatives ({apps}). They work better than the "
                    "Windows version under Wine and get updates automatically."
                ).format(program=html.escape(alt.get("label", key)), apps=html.escape(apps)),
                card,
            )
            note.setWordWrap(True)
            card.layout.addWidget(note)
            alt_btn = QPushButton(tr("Show Linux alternatives"), card)
            alt_btn.setProperty("primary", True)
            alt_btn.clicked.connect(lambda: self._finish("alternative"))
            card.layout.addWidget(alt_btn, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(card)

        blocked = bool({"not_windows_program", "arm"} & set(info.reasons))
        buttons = QHBoxLayout()
        buttons.addStretch(1)

        if engine == "bottles":
            self._add_bottles_actions(layout, buttons, wine_ok, blocked, bool(key))
        elif not wine_ok:
            need = QLabel(
                tr(
                    "Windows programs open with Wine, which is not installed yet. Linwas can "
                    "install it from your system's software sources."
                ),
                self,
            )
            need.setWordWrap(True)
            layout.addWidget(need)
            wine_btn = QPushButton(tr("Install Wine"), self)
            wine_btn.setProperty("primary", not key)
            wine_btn.setEnabled(not blocked)
            wine_btn.clicked.connect(lambda: self._finish("install_wine"))
            buttons.addWidget(wine_btn)
        else:
            self._separate = QCheckBox(tr("Open in a separate environment"), self)
            if info.risk == "high":
                self._separate.setChecked(True)
                self._separate.setEnabled(False)
                hint = tr(
                    "Risky files always open in a separate environment, so they can't affect "
                    "your other Windows programs."
                )
            else:
                hint = tr(
                    "Normally all Windows programs share one environment (like one C: drive). "
                    "A separate one keeps this program apart and is removed completely with it."
                )
            self._separate.setToolTip(hint)
            layout.addWidget(self._separate)
            hint_lbl = QLabel(hint, self)
            hint_lbl.setObjectName("Secondary")
            hint_lbl.setWordWrap(True)
            layout.addWidget(hint_lbl)

            run_text = tr("Run setup with Wine") if info.installer else tr("Open with Wine")
            run_btn = QPushButton(run_text, self)
            run_btn.setProperty("primary", not key and info.risk != "high")
            run_btn.setEnabled(not blocked)
            run_btn.clicked.connect(lambda: self._finish("run"))
            buttons.addWidget(run_btn)

        self._add_close(layout, buttons)

    def _add_bottles_actions(
        self, layout: QVBoxLayout, buttons: QHBoxLayout, ready: bool, blocked: bool, alt: bool
    ) -> None:
        if not ready:
            need = QLabel(
                tr(
                    "Windows programs open with Bottles, which is not installed yet. Linwas can "
                    "install it from Flathub; it brings its own Wine."
                ),
                self,
            )
            need.setWordWrap(True)
            layout.addWidget(need)
            btn = QPushButton(tr("Install Bottles"), self)
            btn.setProperty("primary", not alt)
            btn.setEnabled(not blocked)
            btn.clicked.connect(lambda: self._finish("install_bottles"))
            buttons.addWidget(btn)
            return
        self._gaming = QCheckBox(tr("This is a game"), self)
        layout.addWidget(self._gaming)
        hint = QLabel(
            tr(
                "The program gets its own Windows environment, so it can't affect your other "
                "programs and is removed completely with it."
            ),
            self,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        run_text = tr("Run setup with Bottles") if self._info.installer else tr("Open with Bottles")
        run_btn = QPushButton(run_text, self)
        run_btn.setProperty("primary", not alt and self._info.risk != "high")
        run_btn.setEnabled(not blocked)
        run_btn.clicked.connect(lambda: self._finish("run"))
        buttons.addWidget(run_btn)

    def _add_close(self, layout: QVBoxLayout, row: QHBoxLayout | None = None) -> None:
        if row is None:
            row = QHBoxLayout()
            row.addStretch(1)
        cancel = QPushButton(tr("Cancel"), self)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

    def _finish(self, action: str) -> None:
        self.action = action
        box = getattr(self, "_separate", None)
        self.separate = bool(box and box.isChecked())
        gaming = getattr(self, "_gaming", None)
        self.gaming = bool(gaming and gaming.isChecked())
        self.accept()
