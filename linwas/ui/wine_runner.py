"""Wine ile program başlatma ve izleme (kullanıcı yetkisiyle, kabuksuz).

Ortak ortamda başlatılan program kısa sürede hata koduyla kapanırsa kullanıcıya
"ayrı ortamda yeniden dene" önerilir (karma ortam yaklaşımı).
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QProcessEnvironment, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from linwas.backend import wine

# Bu süreden önce hata koduyla kapanan program "sorun çıkardı" sayılır
_EARLY_EXIT_SECONDS = 60


def tr(text: str) -> str:
    return QCoreApplication.translate("WineRunner", text)


class WineRunner(QObject):
    """Başlatılan Wine süreçlerini tutar; bitince `finished` yayar (liste yenilensin diye)."""

    finished = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._parent = parent
        self._procs: list[QProcess] = []

    def _start(self, argv: list[str], env_vars: dict[str, str], cwd: str = "") -> QProcess:
        proc = QProcess(self)
        env = QProcessEnvironment()
        for key, value in env_vars.items():
            env.insert(key, value)
        proc.setProcessEnvironment(env)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        if cwd:
            proc.setWorkingDirectory(cwd)
        # Çıktı okunmaz; tampon dolup programı durdurmasın
        proc.setStandardOutputFile(QProcess.nullDevice())
        proc.setStandardErrorFile(QProcess.nullDevice())
        self._procs.append(proc)
        proc.start()
        return proc

    def run_file(self, exe: str, env: wine.WineEnv, name: str) -> None:
        """Dosyayı ortamda açar; ortak ortamda erken çökerse ayrı ortam önerir."""
        argv, env_vars = wine.build_command(exe, env)
        proc = self._start(argv, env_vars, str(Path(exe).resolve().parent))
        started = time.monotonic()

        def done(code: int, status: QProcess.ExitStatus) -> None:
            self._forget(proc)
            failed = status == QProcess.ExitStatus.CrashExit or code != 0
            if env.shared and failed and time.monotonic() - started < _EARLY_EXIT_SECONDS:
                self._offer_separate(exe, name)

        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda _e: self._on_error(proc))

    def run_shortcut(self, shortcut: wine.WineShortcut) -> None:
        argv, env_vars = wine.shortcut_command(shortcut)
        proc = self._start(argv, env_vars)
        proc.finished.connect(lambda *_: self._forget(proc))
        proc.errorOccurred.connect(lambda _e: self._on_error(proc))

    def run_uninstaller(self, env: wine.WineEnv) -> None:
        argv, env_vars = wine.uninstaller_command(env)
        proc = self._start(argv, env_vars)
        proc.finished.connect(lambda *_: self._forget(proc))

    def _forget(self, proc: QProcess) -> None:
        if proc in self._procs:
            self._procs.remove(proc)
            proc.deleteLater()
        self.finished.emit()

    def _on_error(self, proc: QProcess) -> None:
        if proc.error() == QProcess.ProcessError.FailedToStart:
            self._forget(proc)
            QMessageBox.warning(
                self._parent,
                tr("Windows program"),
                tr("Wine could not be started. Is Wine installed?"),
            )

    def _offer_separate(self, exe: str, name: str) -> None:
        answer = QMessageBox.question(
            self._parent,
            tr("Windows program"),
            tr(
                "{name} closed unexpectedly. Some programs only work in their own environment. "
                "Try again in a separate environment?"
            ).format(name=name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            env = wine.ensure_env(name, separate=True, reason="retry")
            self.run_file(exe, env, name)
