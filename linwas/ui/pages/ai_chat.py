"""AI Soru sayfası: yardımcı panelin geniş ekran hali."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from linwas.core.tasks import Task, TaskStep
from linwas.core.whitelist import ValidationError, validate
from linwas.ui.ai_panel import AIPanel
from linwas.ui.pages.base import BasePage

# QWidget'ın en büyük boyutu (QWIDGETSIZE_MAX)
_MAX_WIDTH = 16777215


def tr(text: str) -> str:
    return QCoreApplication.translate("AIChatPage", text)


class AIChatPage(BasePage):
    """Geniş sohbet ekranı. Önerilen görevler kuyruğa eklenir (kullanıcı Uygula'ya basar)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        title = QLabel(tr("AI Question"), self)
        title.setObjectName("H1")
        layout.addWidget(title)
        hint = QLabel(
            tr(
                "Ask anything about your computer. Suggested actions are only added to the "
                "queue; nothing runs until you press Apply."
            ),
            self,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._panel = AIPanel(self)
        # Yan paneldeki sabit genişlik burada kaldırılır
        self._panel.setMinimumWidth(0)
        self._panel.setMaximumWidth(_MAX_WIDTH)
        self._panel.task_add_requested.connect(self._on_task)
        layout.addWidget(self._panel, 1)

    def _on_task(self, op_id: str, params: dict) -> None:
        clean = {str(k): str(v) for k, v in params.items()}
        try:
            # AI önerisi kuyruğa girmeden izin listesine karşı doğrulanır
            validate(op_id, clean)
            step = TaskStep(op_id=op_id, params=clean)
            self.task_requested.emit(Task(label=step.label, steps=[step]))
        except ValidationError as exc:
            QMessageBox.warning(self, "Linwas", str(exc))
