"""Görev onay iletişim kutusu.

Kuyruktaki görevleri, adımları ve risk düzeyini gösterir.
Kullanıcı yedek seçeneğini seçer ve onaylar.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linwas.core.tasks import Task
from linwas.core.whitelist import RiskLevel


def tr(text: str) -> str:
    return QCoreApplication.translate("ConfirmDialog", text)


class BackupChoice(Enum):
    NONE = "none"
    QUICK = "quick"  # Linwas değişiklik yedeği
    TIMESHIFT = "timeshift"  # Tam Timeshift anlık görüntüsü


class ConfirmDialog(QDialog):
    """Uygula öncesi onay penceresi."""

    def __init__(self, tasks: list[Task], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Confirm Changes"))
        self.setMinimumWidth(460)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Başlık
        title = QLabel(tr("The following changes will be applied:"), self)
        title.setObjectName("H2")
        layout.addWidget(title)

        # Görev/adım listesi
        has_high_risk = False
        for task in tasks:
            task_lbl = QLabel(f"• {task.label}", self)
            task_lbl.setStyleSheet("font-weight: bold;")
            layout.addWidget(task_lbl)
            for step in task.steps:
                step_lbl = QLabel(f"    — {step.label}", self)
                step_lbl.setObjectName("Secondary")
                layout.addWidget(step_lbl)
            if task.risk_level == RiskLevel.HIGH:
                has_high_risk = True

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Yedek seçeneği
        backup_title = QLabel(tr("Backup before applying:"), self)
        backup_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(backup_title)

        self._backup_group = QButtonGroup(self)

        r_none = QRadioButton(tr("No backup (not recommended for risky changes)"), self)
        r_quick = QRadioButton(
            tr("Quick rollback — Linwas saves changed files and package list"), self
        )
        r_timeshift = QRadioButton(
            tr("Full backup (Timeshift) — safest, may take a few minutes"), self
        )

        for rb in (r_none, r_quick, r_timeshift):
            rb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(rb)
            self._backup_group.addButton(rb)

        # Varsayılan seçim: yüksek riskli görev varsa Timeshift, değilse hızlı
        if has_high_risk:
            r_timeshift.setChecked(True)
        else:
            r_quick.setChecked(True)

        self._r_none = r_none
        self._r_quick = r_quick
        self._r_timeshift = r_timeshift

        # Onay/iptal düğmeleri
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText(tr("Apply"))
        ok_btn.setProperty("primary", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def backup_choice(self) -> BackupChoice:
        if self._r_timeshift.isChecked():
            return BackupChoice.TIMESHIFT
        if self._r_quick.isChecked():
            return BackupChoice.QUICK
        return BackupChoice.NONE
