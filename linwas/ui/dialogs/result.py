# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Görev sonuç iletişim kutusu.

Başarılı/başarısız adımları gösterir. Hızlı geri alma seçildiyse
'Değişiklikleri geri al' düğmesi sunar.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def tr(text: str) -> str:
    return QCoreApplication.translate("ResultDialog", text)


class ResultDialog(QDialog):
    """Görev tamamlandıktan sonra gösterilen sonuç penceresi."""

    undo_requested = Signal()
    retry_requested = Signal()
    help_requested = Signal()
    report_requested = Signal()

    def __init__(
        self,
        success: bool,
        error: str = "",
        has_rollback: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Done") if success else tr("Error"))
        self.setMinimumWidth(400)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        if success:
            icon_lbl = QLabel("✓", self)
            icon_lbl.setStyleSheet("font-size: 32px; color: #0e7a0e;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_lbl)
            title = QLabel(tr("Changes applied successfully"), self)
        else:
            icon_lbl = QLabel("✗", self)
            icon_lbl.setStyleSheet("font-size: 32px; color: #c42b1c;")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_lbl)
            title = QLabel(tr("Some changes could not be applied"), self)

        title.setObjectName("H2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        if error:
            sep = QFrame(self)
            sep.setFrameShape(QFrame.Shape.HLine)
            layout.addWidget(sep)

            from linwas.core.sanitizer import sanitize

            err_lbl = QLabel(sanitize(error), self)
            err_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            err_lbl.setObjectName("Secondary")
            err_lbl.setWordWrap(True)
            layout.addWidget(err_lbl)

        buttons = QDialogButtonBox(self)

        if has_rollback and success:
            undo_btn = QPushButton(tr("Undo changes"), self)
            undo_btn.clicked.connect(self._request_undo)
            buttons.addButton(undo_btn, QDialogButtonBox.ButtonRole.ActionRole)

        if not success:
            for text, signal in (
                (tr("Try again"), self.retry_requested),
                (tr("Ask the assistant"), self.help_requested),
                (tr("Report a problem"), self.report_requested),
            ):
                btn = QPushButton(text, self)
                btn.clicked.connect(signal)
                btn.clicked.connect(self.accept)
                buttons.addButton(btn, QDialogButtonBox.ButtonRole.ActionRole)

        close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        close_btn.setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        close_btn.clicked.connect(self.accept)

        layout.addWidget(buttons)

    def _request_undo(self) -> None:
        self.undo_requested.emit()
        self.accept()
