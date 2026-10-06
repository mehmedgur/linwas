"""Donanım ve yazıcı sayfası: bilgisayar özeti, yazıcılar, tarayıcılar."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QCoreApplication, QLocale, QProcess, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import hardware
from linwas.backend.desktop import detect_desktop
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("HardwarePage", text)


class _Worker(QThread):
    """Verilen işlevi arka planda çalıştırır, sonucu `done` ile döner."""

    done = Signal(object)

    def __init__(self, fn) -> None:  # noqa: ANN001
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception:
            self.done.emit(None)


def _load_printers() -> tuple[list[hardware.Printer], list[str]]:
    return hardware.list_printers(), hardware.detect_usb_printers()


def _clear(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()


class HardwarePage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[_Worker] = []
        self._loaded = False

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        title = QLabel(tr("Hardware & Printers"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Bilgisayarım
        self._pc_card = Card(content)
        h = QLabel(tr("My computer"), self._pc_card)
        h.setObjectName("H2")
        self._pc_card.layout.addWidget(h)
        self._pc_body = QVBoxLayout()
        self._pc_card.layout.addLayout(self._pc_body)
        outer.addWidget(self._pc_card)

        # Yazıcılar
        self._printer_card = Card(content)
        h = QLabel(tr("Printers"), self._printer_card)
        h.setObjectName("H2")
        self._printer_card.layout.addWidget(h)
        self._printer_body = QVBoxLayout()
        self._printer_card.layout.addLayout(self._printer_body)
        row = QHBoxLayout()
        self._settings_cmd = hardware.printer_settings_command(detect_desktop(os.environ).value)
        add_btn = QPushButton(tr("Add or manage printers"), self._printer_card)
        add_btn.setProperty("primary", True)
        add_btn.setEnabled(self._settings_cmd is not None)
        add_btn.clicked.connect(self._open_printer_settings)
        row.addWidget(add_btn)
        drv_btn = QPushButton(tr("Install printer drivers"), self._printer_card)
        drv_btn.setToolTip(tr("Installs drivers for most printer brands (HP, Canon, Epson…)."))
        drv_btn.clicked.connect(self._install_drivers)
        row.addWidget(drv_btn)
        restart_btn = QPushButton(tr("Restart printing service"), self._printer_card)
        restart_btn.clicked.connect(self._restart_cups)
        row.addWidget(restart_btn)
        row.addStretch(1)
        self._printer_card.layout.addLayout(row)
        outer.addWidget(self._printer_card)

        # Tarayıcılar
        self._scanner_card = Card(content)
        h = QLabel(tr("Scanners"), self._scanner_card)
        h.setObjectName("H2")
        self._scanner_card.layout.addWidget(h)
        self._scanner_lbl = QLabel(
            tr("Press “Find scanners” to look for connected scanners."), self._scanner_card
        )
        self._scanner_lbl.setObjectName("Secondary")
        self._scanner_lbl.setWordWrap(True)
        self._scanner_card.layout.addWidget(self._scanner_lbl)
        row = QHBoxLayout()
        self._scan_btn = QPushButton(tr("Find scanners"), self._scanner_card)
        self._scan_btn.clicked.connect(self._find_scanners)
        row.addWidget(self._scan_btn)
        sane_btn = QPushButton(tr("Install scanner support"), self._scanner_card)
        sane_btn.clicked.connect(self._install_scanner_support)
        row.addWidget(sane_btn)
        row.addStretch(1)
        self._scanner_card.layout.addLayout(row)
        outer.addWidget(self._scanner_card)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    # --- Yükleme ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if not self._loaded:
            self._loaded = True
            self._start(hardware.hardware_summary, self._on_summary)
            self._load_printers()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            self._load_printers()

    def _start(self, fn, slot) -> None:  # noqa: ANN001
        worker = _Worker(fn)
        worker.done.connect(slot)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _load_printers(self) -> None:
        _clear(self._printer_body)
        self._printer_body.addWidget(QLabel(tr("Looking for printers…"), self._printer_card))
        self._start(_load_printers, self._on_printers)

    def _line(self, layout: QVBoxLayout, label: str, value: str) -> None:
        lbl = QLabel(f"<b>{html.escape(label)}:</b> {html.escape(value)}", self)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

    def _on_summary(self, summary: hardware.HardwareSummary | None) -> None:
        _clear(self._pc_body)
        if summary is None:
            self._pc_body.addWidget(QLabel(tr("Hardware information could not be read."), self))
            return
        locale = QLocale()
        if summary.cpu:
            cpu = summary.cpu
            if summary.cpu_cores:
                cpu += " " + tr("({n} threads)").format(n=summary.cpu_cores)
            self._line(self._pc_body, tr("Processor"), cpu)
        if summary.memory_bytes:
            self._line(
                self._pc_body,
                tr("Memory (RAM)"),
                locale.formattedDataSize(summary.memory_bytes, 1),
            )
        for gpu in summary.gpus:
            self._line(self._pc_body, tr("Graphics card"), gpu)
        for disk in summary.disks:
            kind = tr("SSD") if disk.ssd else tr("Hard disk")
            self._line(self._pc_body, kind, f"{disk.model or disk.name} — {disk.size}")

    def _on_printers(self, result: tuple[list[hardware.Printer], list[str]] | None) -> None:
        _clear(self._printer_body)
        printers, usb = result or ([], [])
        if not printers:
            msg = tr("No printers are set up yet.")
            lbl = QLabel(msg, self._printer_card)
            lbl.setObjectName("Secondary")
            self._printer_body.addWidget(lbl)
        for p in printers:
            state = tr("Ready") if p.enabled else tr("Stopped")
            text = f"🖨 <b>{html.escape(p.name)}</b> — {state}"
            if p.is_default:
                text += " · " + tr("default")
            self._printer_body.addWidget(QLabel(text, self._printer_card))
        # Takılı ama adı kurulu yazıcılarda geçmeyen USB yazıcılar
        names = " ".join(p.name.lower() for p in printers)
        for dev in usb:
            first = dev.split()[0].lower() if dev.split() else ""
            if first and first in names:
                continue
            warn = QLabel(
                tr("Connected but not set up: {name}. Press “Add or manage printers”.").format(
                    name=dev
                ),
                self._printer_card,
            )
            warn.setStyleSheet("color:#9d5d00;")
            warn.setWordWrap(True)
            self._printer_body.addWidget(warn)

    # --- İşlemler ---

    def _open_printer_settings(self) -> None:
        if self._settings_cmd:
            QProcess.startDetached(self._settings_cmd[0], self._settings_cmd[1:])

    def _install_drivers(self) -> None:
        pkg = hardware.PRINTER_DRIVER_PACKAGE
        self.task_run_now.emit(
            Task(
                label=tr("Install printer drivers"),
                steps=[TaskStep(op_id="package.install", params={"name": pkg})],
            )
        )

    def _restart_cups(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Restart printing service"),
                steps=[TaskStep(op_id="service.restart", params={"name": "cups"})],
            )
        )

    def _install_scanner_support(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install scanner support"),
                steps=[
                    TaskStep(op_id="package.install", params={"name": pkg})
                    for pkg in hardware.SCANNER_PACKAGES
                ],
            )
        )

    def _find_scanners(self) -> None:
        self._scan_btn.setEnabled(False)
        self._scanner_lbl.setText(tr("Looking for scanners… this can take a few seconds."))
        self._start(hardware.list_scanners, self._on_scanners)

    def _on_scanners(self, scanners: list[str] | None) -> None:
        self._scan_btn.setEnabled(True)
        if scanners:
            self._scanner_lbl.setText("\n".join(f"• {s}" for s in scanners))
        else:
            self._scanner_lbl.setText(
                tr(
                    "No scanner found. Make sure it is switched on and connected, then try "
                    "“Install scanner support”."
                )
            )
