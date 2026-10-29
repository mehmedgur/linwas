# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sorun bildir: maskeli raporu gösterir; GitHub'da aç, kopyala veya kaydet."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.core.error_report import issue_url


def tr(text: str) -> str:
    return QCoreApplication.translate("ReportDialog", text)


class ReportDialog(QDialog):
    def __init__(self, title: str, report: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Report a problem"))
        self.setMinimumSize(560, 420)
        self._title = title
        layout = QVBoxLayout(self)

        info = QLabel(
            tr(
                "Personal information (user names, addresses, keys) has been hidden. Check the "
                "report, then open it on GitHub. No GitHub account? Copy or save it and send "
                "it another way."
            ),
            self,
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._text = QTextEdit(self)
        self._text.setPlainText(report)
        self._text.setAccessibleName(tr("Report"))
        layout.addWidget(self._text, 1)

        row = QHBoxLayout()
        github = QPushButton(tr("Open on GitHub"), self)
        github.setProperty("primary", True)
        github.clicked.connect(self._open_github)
        row.addWidget(github)
        copy = QPushButton(tr("Copy"), self)
        copy.clicked.connect(self._copy)
        row.addWidget(copy)
        save = QPushButton(tr("Save…"), self)
        save.clicked.connect(self._save)
        row.addWidget(save)
        row.addStretch(1)
        close = QPushButton(tr("Close"), self)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self._status = QLabel("", self)
        self._status.setObjectName("Secondary")
        layout.addWidget(self._status)

    def _open_github(self) -> None:
        QDesktopServices.openUrl(QUrl(issue_url(self._title, self._text.toPlainText())))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text.toPlainText())
        self._status.setText(tr("Copied."))

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save report"), str(Path.home() / "linwas-rapor.txt"), "*.txt"
        )
        if path:
            try:
                Path(path).write_text(self._text.toPlainText(), encoding="utf-8")
                self._status.setText(tr("Saved: {path}").format(path=path))
            except OSError as exc:
                self._status.setText(str(exc))
