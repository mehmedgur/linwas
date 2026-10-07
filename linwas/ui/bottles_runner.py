"""Bottles ile Windows programı kurma/açma akışı (kullanıcı yetkisiyle, kabuksuz).

Akış: şişe oluştur → dosyayı şişede çalıştır → programları oku (JSON) → menüye kısayol ekle.
Kurulum dosyası değilse program şişeye eklenir (bottles-cli add). Hata çıkarsa ayrıntı
gösterilir ve istenirse AI asistanına sorulur.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QProcess, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QWidget

from linwas.backend import bottles


def tr(text: str) -> str:
    return QCoreApplication.translate("BottlesRunner", text)


class BottlesRunner(QObject):
    finished = Signal()  # liste yenilensin
    ai_help_requested = Signal(str, str)  # (görev adı, hata çıktısı)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._parent = parent
        self._procs: list[QProcess] = []
        self._busy: QProgressDialog | None = None

    # --- Süreç yardımcıları ---

    def _start(self, argv: list[str], on_done=None, capture: bool = False) -> QProcess:  # noqa: ANN001
        proc = QProcess(self)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        if not capture:
            # Çıktı okunmaz; tampon dolup programı durdurmasın
            proc.setStandardOutputFile(QProcess.nullDevice())
            proc.setStandardErrorFile(QProcess.nullDevice())
        self._procs.append(proc)

        def done(code: int, status: QProcess.ExitStatus) -> None:
            out = bytes(proc.readAllStandardOutput()).decode(errors="replace") if capture else ""
            err = bytes(proc.readAllStandardError()).decode(errors="replace") if capture else ""
            ok = status == QProcess.ExitStatus.NormalExit and code == 0
            self._forget(proc)
            if on_done:
                on_done(ok, out, err)

        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda _e: self._on_error(proc))
        proc.start()
        return proc

    def _forget(self, proc: QProcess) -> None:
        if proc in self._procs:
            self._procs.remove(proc)
            proc.deleteLater()

    def _on_error(self, proc: QProcess) -> None:
        if proc.error() == QProcess.ProcessError.FailedToStart:
            self._forget(proc)
            self._hide_busy()
            QMessageBox.warning(
                self._parent,
                tr("Windows program"),
                tr("Bottles could not be started. Is Bottles installed?"),
            )

    def _show_busy(self, text: str) -> None:
        self._hide_busy()
        dlg = QProgressDialog(text, "", 0, 0, self._parent)
        dlg.setWindowTitle(tr("Windows program"))
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()
        self._busy = dlg

    def _hide_busy(self) -> None:
        if self._busy is not None:
            self._busy.close()
            self._busy.deleteLater()
            self._busy = None

    def _fail(self, label: str, error: str) -> None:
        self._hide_busy()
        box = QMessageBox(
            QMessageBox.Icon.Warning, tr("Windows program"), label, parent=self._parent
        )
        box.setInformativeText(tr("Bottles reported an error."))
        if error.strip():
            box.setDetailedText(error.strip()[-4000:])
        ask = box.addButton(tr("Ask the assistant"), QMessageBox.ButtonRole.HelpRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is ask:
            self.ai_help_requested.emit(label, error)
        self.finished.emit()

    # --- Akış ---

    def install(self, exe: str, name: str, installer: bool, gaming: bool, risky: bool) -> None:
        """Yeni şişe oluşturur, dosyayı içinde çalıştırır."""
        bottle = bottles.Bottle(
            id=bottles.new_bottle_id(name),
            name=name,
            environment="gaming" if gaming else "application",
            reason="risk" if risky else "",
        )
        self._show_busy(
            tr(
                "Preparing a Windows environment for {name}…\n"
                "The first time this can take several minutes (Wine is downloaded)."
            ).format(name=name)
        )

        def created(ok: bool, _out: str, err: str) -> None:
            if not ok:
                self._fail(
                    tr("The Windows environment for {name} could not be created.").format(
                        name=name
                    ),
                    err,
                )
                return
            bottles.register(bottle)
            self._hide_busy()
            self._run(bottle, exe, installer)

        self._start(bottles.new_command(bottle.id, bottle.environment), created, capture=True)

    def _run(self, bottle: bottles.Bottle, exe: str, installer: bool) -> None:
        def ran(ok: bool, _out: str, err: str) -> None:
            if installer:
                self.add_shortcuts(bottle.id, notify=True)
                return
            # Kurulum dosyası değil: program şişeye eklenir, kendi klasöründen açılır
            read_dir = str(Path(exe).resolve().parent)
            bottles.set_read_dir(bottle.id, read_dir)

            def added(ok2: bool, _o: str, err2: str) -> None:
                if not ok2:
                    self._fail(tr("{name} could not be added.").format(name=bottle.name), err2)
                    return
                bottles.write_shortcut(bottle.id, bottle.name, read_dir)
                self.finished.emit()

            self._start(
                bottles.add_program_command(bottle.id, bottle.name, exe), added, capture=True
            )

        # Uzun süren programın çıktısı bellekte birikmesin diye yakalanmaz
        self._start(bottles.run_exe_command(bottle.id, exe), ran)

    def add_shortcuts(self, bottle_id: str, notify: bool = False) -> None:
        """Şişedeki programları okur, eksik menü kısayollarını ekler."""
        read_dir = next((b.read_dir for b in bottles.list_bottles() if b.id == bottle_id), "")

        def listed(ok: bool, out: str, err: str) -> None:
            if not ok:
                self._fail(tr("The programs in this environment could not be read."), err)
                return
            programs = bottles.parse_programs(out)
            for program in programs:
                if not bottles.has_shortcut(bottle_id, program["name"]):
                    bottles.write_shortcut(bottle_id, program["name"], read_dir)
            if notify and not programs:
                QMessageBox.information(
                    self._parent,
                    tr("Windows program"),
                    tr(
                        "Setup finished, but no installed program was found. If setup was "
                        "cancelled you can delete this environment under Windows programs."
                    ),
                )
            self.finished.emit()

        self._start(bottles.programs_command(bottle_id), listed, capture=True)

    def run_program(self, bottle_id: str, program: str, read_dir: str = "") -> None:
        self._start(bottles.run_program_command(bottle_id, program, read_dir))

    def run_uninstaller(self, bottle_id: str) -> None:
        self._start(bottles.uninstaller_command(bottle_id), lambda *_: self.finished.emit())
