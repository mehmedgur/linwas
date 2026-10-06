"""Görev ilerleme iletişim kutusu.

Görevler QThread içinde çalışır; her adım ve helper çıktısı canlı gösterilir.
Pencere işlem sürerken kapatılamaz; arka plana alınabilir (durum çubuğu › Detay geri açar).
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
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
    # QThread'in kendi `finished` sinyalini gölgelememek için ayrı ad
    completed = Signal(bool, str)  # (başarılı, hata mesajı)

    def __init__(self, queue: TaskQueue, parent: QWidget) -> None:
        # Ebeveyn: iş parçacığı nesnesi pencereyle yaşar (çalışırken silinirse Qt çöker)
        super().__init__(parent)
        self._queue = queue

    def run(self) -> None:
        error_msg = ""
        success = True
        try:
            # İlerleme canlı yayınlanır; apply() olayları ancak görev bitince döndürür
            for prog in self._queue.apply(
                executor=_privilege_executor, on_progress=self.progress.emit
            ):
                if prog.error:
                    success = False
                    error_msg = prog.error
        except Exception as exc:
            success = False
            error_msg = str(exc)
        self.completed.emit(success, error_msg)


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

        # Komut çıktısı (dpkg/apt satırları); "Ayrıntıları göster" ile açılır
        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._log.setMinimumHeight(220)
        self._log.setVisible(False)
        layout.addWidget(self._log, 1)

        buttons = QHBoxLayout()
        self._details_btn = QPushButton(tr("Show details"), self)
        self._details_btn.clicked.connect(self._toggle_details)
        buttons.addWidget(self._details_btn)
        buttons.addStretch(1)
        # Pencere gizlenir, işlem sürer; durum çubuğundaki "Detay" geri açar
        bg_btn = QPushButton(tr("Continue in background"), self)
        bg_btn.clicked.connect(self.hide)
        buttons.addWidget(bg_btn)
        layout.addLayout(buttons)

        self._worker = _TaskWorker(queue, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.completed.connect(self._on_finished)
        self._worker.start()

    def _toggle_details(self) -> None:
        show = not self._log.isVisible()
        self._log.setVisible(show)
        self._details_btn.setText(tr("Hide details") if show else tr("Show details"))
        if show:
            self.resize(max(self.width(), 640), self.height())
        else:
            self.adjustSize()

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
        if prog.message:
            self._log.appendPlainText(prog.message)
        if prog.error:
            self._detail_lbl.setText(prog.error)
            self._log.appendPlainText(prog.error)
        self.step_progress.emit(prog.step_index + 1, prog.step_total, prog.step_label)

    def _on_finished(self, success: bool, error: str) -> None:
        # run() completed'i yayınlayıp hemen döner; pencere silinmeden önce iş parçacığı bitsin
        self._worker.wait(5000)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.done.emit(success, error)
        self.accept()

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        # Çalışan worker varsa kapatmayı engelle
        if self._worker.isRunning():
            event.ignore()  # type: ignore[union-attr]
        else:
            super().closeEvent(event)  # type: ignore[misc]
