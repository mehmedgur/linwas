"""Donanım ve yazıcı sayfası: bilgisayar özeti, Aygıt Yöneticisi, yazıcılar, tarayıcılar."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QCoreApplication, QLocale, QProcess, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import devices, hardware
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


def _load_printers() -> tuple[list[hardware.Printer], list[str], list]:
    from linwas.backend.drivers import dpkg_installed

    suggestions = [
        s for s in devices.printer_suggestions(devices.list_usb()) if not dpkg_installed(s.package)
    ]
    return hardware.list_printers(), hardware.detect_usb_printers(), suggestions


def _group_name(group: str) -> str:
    return {
        "display": tr("Display adapters"),
        "network": tr("Network adapters"),
        "bluetooth": tr("Bluetooth"),
        "audio": tr("Sound"),
        "camera": tr("Cameras"),
        "printer": tr("Printers and scanners"),
        "storage": tr("Storage controllers and disks"),
        "input": tr("Keyboards, mice and other input devices"),
        "usb": tr("USB controllers and hubs"),
        "system": tr("System devices"),
        "other": tr("Other devices"),
    }.get(group, group)


def _clear(layout) -> None:  # noqa: ANN001 - QLayout
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())  # öneri satırları gibi iç içe düzenler


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
        outer.setContentsMargins(36, 28, 36, 28)
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

        # Aygıt Yöneticisi
        self._dev_card = Card(content)
        head = QHBoxLayout()
        h = QLabel(tr("Device Manager"), self._dev_card)
        h.setObjectName("H2")
        head.addWidget(h)
        head.addStretch(1)
        refresh = QPushButton(tr("Refresh"), self._dev_card)
        refresh.clicked.connect(self._load_devices)
        head.addWidget(refresh)
        drivers_btn = QPushButton(tr("Find drivers"), self._dev_card)
        drivers_btn.clicked.connect(lambda: self.page_requested.emit("drivers"))
        head.addWidget(drivers_btn)
        self._dev_card.layout.addLayout(head)
        self._dev_summary = QLabel(tr("Looking for devices…"), self._dev_card)
        self._dev_summary.setWordWrap(True)
        self._dev_card.layout.addWidget(self._dev_summary)
        self._dev_tree = QTreeWidget(self._dev_card)
        self._dev_tree.setHeaderLabels([tr("Device"), tr("Driver"), tr("Status")])
        self._dev_tree.setRootIsDecorated(True)
        self._dev_tree.setMinimumHeight(320)
        header = self._dev_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._dev_card.layout.addWidget(self._dev_tree)
        outer.addWidget(self._dev_card)

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
            self._load_devices()
            self._load_printers()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            self._load_devices()
            self._load_printers()

    def _load_devices(self) -> None:
        self._dev_summary.setText(tr("Looking for devices…"))
        self._start(devices.list_devices, self._on_devices)

    def _on_devices(self, items: list[devices.Device] | None) -> None:
        self._dev_tree.clear()
        items = items or []
        problems = [d for d in items if d.problem]
        if not items:
            self._dev_summary.setText(tr("Device information could not be read."))
            return
        if problems:
            self._dev_summary.setText(
                tr("{n} device(s) have no driver. Press “Find drivers”.").format(n=len(problems))
            )
            self._dev_summary.setObjectName("Warning")
        else:
            self._dev_summary.setText(
                tr("{n} devices found; all important devices have a driver.").format(n=len(items))
            )
            self._dev_summary.setObjectName("Secondary")
        self._dev_summary.style().unpolish(self._dev_summary)
        self._dev_summary.style().polish(self._dev_summary)

        groups: dict[str, QTreeWidgetItem] = {}
        if problems:
            top = QTreeWidgetItem([tr("Devices without a driver"), "", ""])
            self._dev_tree.addTopLevelItem(top)
            for d in problems:
                QTreeWidgetItem(top, self._device_columns(d))
            top.setExpanded(True)
        for d in items:
            if d.problem:
                continue
            group = groups.get(d.group)
            if group is None:
                group = QTreeWidgetItem([_group_name(d.group), "", ""])
                self._dev_tree.addTopLevelItem(group)
                groups[d.group] = group
            QTreeWidgetItem(group, self._device_columns(d))
        for group_id, item in groups.items():
            item.setText(0, f"{_group_name(group_id)} ({item.childCount()})")

    @staticmethod
    def _device_columns(d: devices.Device) -> list[str]:
        if d.driver:
            status = tr("Working")
        elif d.module:
            status = tr("Driver available but not loaded")
        elif d.problem:
            status = "⚠ " + tr("No driver")
        else:
            status = tr("No driver needed")
        bus = "USB" if d.bus == "usb" else "PCI"
        return [f"{d.name}  [{bus} {d.ids}]", d.driver or d.module or "—", status]

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

    def _on_printers(self, result: tuple | None) -> None:
        _clear(self._printer_body)
        printers, usb, suggestions = result or ([], [], [])
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
        # Takılı aygıtın üreticisine göre önerilen sürücü paketleri
        for s in suggestions:
            row = QHBoxLayout()
            lbl = QLabel(
                tr("Recommended driver for {device}: {pkg}").format(device=s.device, pkg=s.package),
                self._printer_card,
            )
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
            btn = QPushButton(tr("Install"), self._printer_card)
            btn.setProperty("primary", True)
            btn.clicked.connect(lambda _=False, p=s.package: self._install_package(p))
            row.addWidget(btn)
            self._printer_body.addLayout(row)

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

    def _install_package(self, pkg: str) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install {pkg}").format(pkg=pkg),
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
