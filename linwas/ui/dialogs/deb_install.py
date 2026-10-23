""".deb dosyası kurulumu: önce risk analizi, sonra onayla kuyruğa."""

from __future__ import annotations

import html

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from linwas.backend.deb_inspect import DebInfo


def tr(text: str) -> str:
    return QCoreApplication.translate("DebInstallDialog", text)


def _reason_texts() -> dict[str, str]:
    return {
        "scripts": tr("Runs its own setup scripts with administrator rights."),
        "repo": tr("Adds a software source or signing key to your system."),
        "service": tr("Installs a background service that starts with the computer."),
        "sensitive": tr(
            "Changes sensitive system areas (administrator rights, startup, kernel or home "
            "folders)."
        ),
        "arch": tr("Made for a different processor type; it will probably not work."),
    }


class DebInstallDialog(QDialog):
    """Analiz sonucunu gösterir; kabul edilirse çağıran deb.install görevini oluşturur."""

    def __init__(self, info: DebInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Install a .deb file"))
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        if info.error:
            layout.addWidget(
                QLabel(tr("This file can't be read: {error}").format(error=info.error))
            )
            buttons = QDialogButtonBox(self)
            buttons.addButton(tr("Close"), QDialogButtonBox.ButtonRole.RejectRole)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            return

        title = QLabel(f"{html.escape(info.package)} {html.escape(info.version)}", self)
        title.setObjectName("H2")
        layout.addWidget(title)
        if info.description:
            layout.addWidget(QLabel(html.escape(info.description), self))
        who = QLabel(tr("Made by: {who}").format(who=html.escape(info.maintainer or "?")), self)
        who.setObjectName("Secondary")
        layout.addWidget(who)

        risk_text = {
            "low": (tr("Low risk"), "#0e7a0e"),
            "medium": (tr("Medium risk"), "#9d5d00"),
            "high": (tr("High risk — install only if you trust the source"), "#c42b1c"),
        }[info.risk]
        risk = QLabel(risk_text[0], self)
        risk.setStyleSheet(f"color:{risk_text[1]}; font-weight:bold;")
        layout.addWidget(risk)

        texts = _reason_texts()
        lines = [f"• {texts[r]}" for r in info.reasons if r in texts]
        if not lines:
            lines.append("• " + tr("Only copies program files; no scripts or system changes."))
        for reason, paths in info.flagged_files.items():
            if reason in ("repo", "sensitive", "service"):
                shown = ", ".join(paths[:3]) + (" …" if len(paths) > 3 else "")
                lines.append(f"    {html.escape(shown)}")
        details = QLabel("<br>".join(lines), self)
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setWordWrap(True)
        layout.addWidget(details)

        if info.repo_version:
            note = QLabel(
                tr(
                    "This program is also in your system's software sources (version "
                    "{version}). Installing from there is safer and it updates automatically."
                ).format(version=html.escape(info.repo_version)),
                self,
            )
            note.setWordWrap(True)
            note.setStyleSheet("color:#0067c0;")
            layout.addWidget(note)
        if info.installed_version:
            layout.addWidget(
                QLabel(
                    tr("Installed now: {version}").format(
                        version=html.escape(info.installed_version)
                    ),
                    self,
                )
            )

        buttons = QDialogButtonBox(self)
        install = buttons.addButton(tr("Install"), QDialogButtonBox.ButtonRole.AcceptRole)
        install.setProperty("primary", info.risk != "high")
        install.setEnabled("arch" not in info.reasons)
        buttons.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
