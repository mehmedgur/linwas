"""Sorun Giderme: tek tıkla tarama ve belirti kartları.

Çözümler ya izin listesindeki görevlerdir (kuyruk + onay) ya da ilgili Linwas sayfasına
gidiştir. Ses servisi kullanıcı düzeyinde olduğu için doğrudan yeniden başlatılır.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import troubleshoot
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("TroubleshootPage", text)


class _Worker(QThread):
    done = Signal(object)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception:
            self.done.emit(None)


def _check_texts() -> dict[str, tuple[str, str]]:
    """kontrol → (sorun yoksa, sorun varsa)."""
    return {
        "internet": (tr("Internet connection works"), tr("No internet connection")),
        "disk": (tr("Enough free disk space"), tr("Disk is almost full")),
        "packages": (tr("Programs are installed correctly"), tr("An installation was interrupted")),
        "services": (tr("System services are running"), tr("Some system services failed")),
        "sound": (tr("Sound system is running"), tr("Sound system is not responding")),
        "printing": (tr("Printing service is running"), tr("Printing service is stopped")),
        "updates": (tr("No security updates waiting"), tr("Security updates are waiting")),
    }


class TroubleshootPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[_Worker] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        title = QLabel(tr("Troubleshooting"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Tarama
        scan_card = Card(content)
        row = QHBoxLayout()
        info = QLabel(
            tr("Checks internet, disk space, installations, services, sound and printing."),
            scan_card,
        )
        info.setWordWrap(True)
        row.addWidget(info, 1)
        self._scan_btn = QPushButton(tr("Scan my computer"), scan_card)
        self._scan_btn.setProperty("primary", True)
        self._scan_btn.clicked.connect(self._scan)
        row.addWidget(self._scan_btn)
        scan_card.layout.addLayout(row)
        self._results = QVBoxLayout()
        scan_card.layout.addLayout(self._results)
        outer.addWidget(scan_card)

        # Belirti kartları
        h = QLabel(tr("What's the problem?"), content)
        h.setObjectName("H2")
        outer.addWidget(h)
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (title_text, desc, actions) in enumerate(self._symptoms()):
            grid.addWidget(self._symptom_card(content, title_text, desc, actions), i // 2, i % 2)
        outer.addLayout(grid)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    # --- Çözümler ---

    def _task(self, label: str, op_id: str, params: dict[str, str] | None = None) -> Callable:
        def run() -> None:
            self.task_run_now.emit(
                Task(label=label, steps=[TaskStep(op_id=op_id, params=params or {})])
            )

        return run

    def _go(self, page_id: str) -> Callable:
        return lambda: self.page_requested.emit(page_id)

    def _restart_sound(self) -> None:
        self._run(troubleshoot.restart_sound, self._on_sound_restarted)

    def _on_sound_restarted(self, ok: object) -> None:
        self._add_result(
            bool(ok),
            tr("Sound system restarted") if ok else tr("Sound system could not be restarted"),
        )

    def _fixes(self) -> dict[str, list[tuple[str, Callable]]]:
        restart_net = self._task(
            tr("Restart network service"), "service.restart", {"name": "NetworkManager"}
        )
        repair = self._task(tr("Repair interrupted installations"), "package.fix_broken")
        restart_cups = self._task(
            tr("Restart printing service"), "service.restart", {"name": "cups"}
        )
        return {
            "internet": [
                (tr("Restart network service"), restart_net),
                (tr("Wi-Fi settings"), self._go("network")),
            ],
            "disk": [(tr("Free up space"), self._go("cleanup"))],
            "packages": [(tr("Repair"), repair)],
            "services": [],
            "sound": [(tr("Restart sound"), self._restart_sound)],
            "printing": [(tr("Restart printing service"), restart_cups)],
            "updates": [(tr("Show updates"), self._go("updates"))],
        }

    def _symptoms(self) -> list[tuple[str, str, list[tuple[str, Callable]]]]:
        fixes = self._fixes()
        return [
            (
                tr("No internet"),
                tr("Web pages don't open or Wi-Fi keeps disconnecting."),
                fixes["internet"],
            ),
            (tr("No sound"), tr("Videos and music play silently."), fixes["sound"]),
            (
                tr("Printer doesn't print"),
                tr("Documents stay in the queue or the printer isn't found."),
                [*fixes["printing"], (tr("Printers"), self._go("hardware"))],
            ),
            (
                tr("Computer is slow"),
                tr("Programs open slowly or the fan is loud."),
                [(tr("Task Manager"), self._go("taskmgr")), *fixes["disk"]],
            ),
            (
                tr("Can't install programs"),
                tr("Installing or updating stops with an error."),
                fixes["packages"],
            ),
            (
                tr("Screen or graphics problem"),
                tr("Wrong resolution, flickering or games run badly."),
                [(tr("Drivers"), self._go("drivers")), (tr("Display"), self._go("display"))],
            ),
        ]

    def _symptom_card(
        self, parent: QWidget, title: str, desc: str, actions: list[tuple[str, Callable]]
    ) -> Card:
        card = Card(parent)
        h = QLabel(title, card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        d = QLabel(desc, card)
        d.setObjectName("Secondary")
        d.setWordWrap(True)
        card.layout.addWidget(d)
        row = QHBoxLayout()
        for text, fn in actions:
            btn = QPushButton(text, card)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        return card

    # --- Tarama ---

    def _run(self, fn: Callable[[], object], slot: Callable) -> None:
        worker = _Worker(fn)
        worker.done.connect(slot)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _clear_results(self) -> None:
        while self._results.count():
            item = self._results.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _scan(self) -> None:
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText(tr("Scanning…"))
        self._clear_results()
        self._run(troubleshoot.run_all, self._on_scanned)

    def _add_result(self, ok: bool, text: str, detail: str = "") -> QHBoxLayout:
        row_widget = QWidget(self)
        row_widget.setObjectName("CardRow")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 2, 0, 2)
        mark = QLabel("✓" if ok else "⚠", row_widget)
        mark.setStyleSheet(f"color:{'#0e7a0e' if ok else '#c42b1c'}; font-weight:bold;")
        row.addWidget(mark)
        lbl = QLabel(text, row_widget)
        if detail:
            lbl.setToolTip(detail)
        row.addWidget(lbl, 1)
        self._results.addWidget(row_widget)
        return row

    def _on_scanned(self, results: list[troubleshoot.CheckResult] | None) -> None:
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText(tr("Scan again"))
        texts = _check_texts()
        fixes = self._fixes()
        results = results or []
        problems = [r for r in results if not r.ok]
        # Önce sorunlar, sonra sorunsuz kontroller
        for r in problems + [r for r in results if r.ok]:
            ok_text, bad_text = texts.get(r.id, (r.id, r.id))
            row = self._add_result(r.ok, ok_text if r.ok else bad_text, r.detail)
            if not r.ok:
                for text, fn in fixes.get(r.id, []):
                    btn = QPushButton(text, self)
                    btn.clicked.connect(fn)
                    row.addWidget(btn)
        summary = QLabel(
            tr("No problems found.")
            if not problems
            else tr("{n} problem(s) found.").format(n=len(problems)),
            self,
        )
        summary.setObjectName("H2")
        self._results.insertWidget(0, summary)
