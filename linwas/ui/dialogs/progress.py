"""Görev ilerleme iletişim kutusu.

Görevler QThread içinde çalışır; her adım için UI güncellenir.
Pencere kapatılamaz (arka plana alınabilir: TODO).
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.core import privilege
from linwas.core.tasks import Task, TaskProgress, TaskQueue


def _privilege_executor(task: Task, on_progress: object) -> None:
    """Root helper aracılığıyla görevi çalıştırır."""
    privilege.run_task(task, on_progress=on_progress)  # type: ignore[arg-type]


def tr(text: str) -> str:
    return QCoreApplication.translate("ProgressDialog", text)


class _TaskWorker(QThread):
    """Görevi arka planda çalıştırır; ilerleme sinyali yayar."""

    progress = Signal(TaskProgress)
    finished = Signal(bool, str)  # (başarılı, hata mesajı)

    def __init__(self, queue: TaskQueue) -> None:
        super().__init__()
        self._queue = queue

    def run(self) -> None:
        error_msg = ""
        success = True
        try:
            for prog in self._queue.apply(executor=_privilege_executor):
                self.progress.emit(prog)
                if prog.error:
                    success = False
                    error_msg = prog.error
        except Exception as exc:
            success = False
            error_msg = str(exc)
        self.finished.emit(success, error_msg)


class ProgressDialog(QDialog):
    """Görev çalışırken gösterilen ilerleme penceresi."""

    done = Signal(bool, str)  # (başarılı, hata)
    step_progress = Signal(int, int, str)  # durum çubuğu için (adım, toplam, etiket)

    def __init__(self, queue: TaskQueue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Applying changes…"))
        self.setMinimumWidth(400)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        # Kapatma düğmesini devre dışı bırak (işlem devam ederken)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._title_lbl = QLabel(tr("Preparing…"), self)
        self._title_lbl.setObjectName("H2")
        layout.addWidget(self._title_lbl)

        self._step_lbl = QLabel("", self)
        self._step_lbl.setObjectName("Secondary")
        layout.addWidget(self._step_lbl)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)  # belirsiz başlangıç
        layout.addWidget(self._progress)

        self._detail_lbl = QLabel("", self)
        self._detail_lbl.setObjectName("Secondary")
        self._detail_lbl.setWordWrap(True)
        layout.addWidget(self._detail_lbl)

        # Pencere gizlenir, işlem sürer; durum çubuğundaki "Detay" geri açar
        bg_btn = QPushButton(tr("Continue in background"), self)
        bg_btn.clicked.connect(self.hide)
        layout.addWidget(bg_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._worker = _TaskWorker(queue)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, prog: TaskProgress) -> None:
        self._title_lbl.setText(prog.task_label)
        self._step_lbl.setText(
            tr("Step {current} of {total}: {label}").format(
                current=prog.step_index + 1,
                total=prog.step_total,
                label=prog.step_label,
            )
        )
        if prog.step_total > 0:
            self._progress.setRange(0, prog.step_total)
            self._progress.setValue(prog.step_index + 1)
        if prog.error:
            self._detail_lbl.setText(prog.error)
        self.step_progress.emit(prog.step_index + 1, prog.step_total, prog.step_label)

    def _on_finished(self, success: bool, error: str) -> None:
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.done.emit(success, error)
        self.accept()

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        # Çalışan worker varsa kapatmayı engelle
        if self._worker.isRunning():
            event.ignore()  # type: ignore[union-attr]
        else:
            super().closeEvent(event)  # type: ignore[misc]
