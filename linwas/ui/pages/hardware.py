# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Donanım ve yazıcılar sayfası: Genel bakış / Aygıtlar / Yazıcılar ve tarayıcılar.

Donanım bilgisi `linwas.plugins.hardware_info` eklentisinden gelir (kararlar.md › Donanım ve
yazıcılar yenilemesi, 13 Ekim 2026).
"""

from __future__ import annotations

import os

from PySide6.QtCore import QCoreApplication, QProcess, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import devices, hardware
from linwas.backend.desktop import detect_desktop
from linwas.core.tasks import Task, TaskStep
from linwas.plugins.hardware_info.widgets import (
    DetailsDialog,
    HardwareOverview,
    Meter,
    Pill,
    device_sections,
    device_status,
)
from linwas.translations import percent
from linwas.ui import icons
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


def _load_printers() -> tuple[list[hardware.Printer], list, list[str], list]:
    from linwas.backend.drivers import dpkg_installed

    suggestions = [
        s for s in devices.printer_suggestions(devices.list_usb()) if not dpkg_installed(s.package)
    ]
    printers = hardware.list_printers()
    return printers, hardware.printer_details(printers), hardware.detect_usb_printers(), suggestions


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
            _clear(item.layout())


def _scroll(widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll


def _section(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("Secondary")
    return lbl


class HardwarePage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[_Worker] = []
        self._loaded = False
        self._devices: list[devices.Device] = []
        self._settings_cmd = hardware.printer_settings_command(detect_desktop(os.environ).value)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 28, 36, 0)
        outer.setSpacing(12)
        head = QHBoxLayout()
        title = QLabel(tr("Hardware & Printers"), self)
        title.setObjectName("H1")
        head.addWidget(title, 1)
        report = QPushButton(tr("System report"), self)
        report.setToolTip(tr("Opens a summary of this computer's hardware in the browser."))
        head.addWidget(report)
        copy = QPushButton(tr("Copy details"), self)
        copy.setToolTip(tr("Copies a hardware summary, e.g. to paste into a help forum."))
        head.addWidget(copy)
        outer.addLayout(head)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        outer.addWidget(self._tabs, 1)

        # Genel bakış (donanım bilgisi eklentisi)
        ov = QWidget()
        ov_lay = QVBoxLayout(ov)
        ov_lay.setContentsMargins(0, 8, 8, 28)
        self._overview = HardwareOverview(ov)
        self._overview.page_requested.connect(self.page_requested)
        self._overview.memory_report_requested.connect(self._memory_report)
        ov_lay.addWidget(self._overview)
        ov_lay.addStretch(1)
        self._tabs.addTab(_scroll(ov), tr("Overview"))
        report.clicked.connect(self._overview.open_report)
        copy.clicked.connect(self._overview.copy_summary)

        self._tabs.addTab(self._build_devices(), tr("Devices"))
        self._tabs.addTab(self._build_printers(), tr("Printers & scanners").replace("&", "&&"))

    # --- Aygıtlar ---

    def _build_devices(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 8, 28)
        lay.setSpacing(12)
        bar = QHBoxLayout()
        self._search = QLineEdit(page)
        self._search.setPlaceholderText(tr("Search devices"))
        self._search.setClearButtonEnabled(True)
        self._search.setAccessibleName(tr("Search devices"))
        self._search.setMaximumWidth(320)
        self._search.textChanged.connect(self._fill_tree)
        bar.addWidget(self._search)
        self._filter = QButtonGroup(page)
        self._chips: dict[str, QPushButton] = {}
        for key in ("all", "problem", "nodriver"):
            chip = QPushButton(page)
            chip.setObjectName("Chip")
            chip.setCheckable(True)
            chip.setChecked(key == "all")
            self._filter.addButton(chip)
            self._chips[key] = chip
            chip.toggled.connect(lambda on: on and self._fill_tree())
            bar.addWidget(chip)
        bar.addStretch(1)
        refresh = QPushButton(tr("Refresh"), page)
        refresh.clicked.connect(self._load_devices)
        bar.addWidget(refresh)
        find = QPushButton(tr("Find drivers"), page)
        find.setProperty("primary", True)
        find.clicked.connect(lambda: self.page_requested.emit("drivers"))
        bar.addWidget(find)
        lay.addLayout(bar)
        self._dev_summary = QLabel(tr("Looking for devices…"), page)
        self._dev_summary.setWordWrap(True)
        lay.addWidget(self._dev_summary)
        self._dev_tree = QTreeWidget(page)
        self._dev_tree.setHeaderLabels([tr("Device"), tr("Driver"), tr("Status")])
        self._dev_tree.setRootIsDecorated(True)
        header = self._dev_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._dev_tree.itemActivated.connect(self._device_details)
        lay.addWidget(self._dev_tree, 1)
        row = QHBoxLayout()
        hint = QLabel(tr("Double-click a device to see its details."), page)
        hint.setObjectName("Caption")
        row.addWidget(hint, 1)
        details = QPushButton(tr("Details"), page)
        details.clicked.connect(lambda: self._device_details(self._dev_tree.currentItem()))
        row.addWidget(details)
        lay.addLayout(row)
        self._update_chips()
        return page

    def _update_chips(self) -> None:
        n_all = len(self._devices)
        n_problem = sum(1 for d in self._devices if d.problem)
        n_nodriver = sum(1 for d in self._devices if not d.driver)
        self._chips["all"].setText(tr("All %1").replace("%1", str(n_all)))
        self._chips["problem"].setText(tr("Problems %1").replace("%1", str(n_problem)))
        self._chips["nodriver"].setText(tr("No driver %1").replace("%1", str(n_nodriver)))

    def _load_devices(self) -> None:
        self._dev_summary.setText(tr("Looking for devices…"))
        self._start(devices.list_devices, self._on_devices)

    def _on_devices(self, items: list[devices.Device] | None) -> None:
        self._devices = items or []
        problems = [d for d in self._devices if d.problem]
        if not self._devices:
            self._dev_summary.setText(tr("Device information could not be read."))
        elif problems:
            self._dev_summary.setText(
                tr("{n} device(s) have no driver. Press “Find drivers”.").format(n=len(problems))
            )
        else:
            self._dev_summary.setText(
                tr("{n} devices found; all important devices have a driver.").format(
                    n=len(self._devices)
                )
            )
        self._dev_summary.setObjectName("Warning" if problems else "Secondary")
        self._dev_summary.style().unpolish(self._dev_summary)
        self._dev_summary.style().polish(self._dev_summary)
        self._update_chips()
        self._fill_tree()

    def _fill_tree(self) -> None:
        self._dev_tree.clear()
        text = self._search.text().strip().lower()
        mode = next(k for k, c in self._chips.items() if c.isChecked())
        groups: dict[str, QTreeWidgetItem] = {}
        for d in self._devices:
            if mode == "problem" and not d.problem:
                continue
            if mode == "nodriver" and d.driver:
                continue
            if text and text not in f"{d.name} {d.driver} {d.module} {d.ids}".lower():
                continue
            key = "_problem" if d.problem else d.group
            group = groups.get(key)
            if group is None:
                name = tr("Devices without a driver") if d.problem else _group_name(d.group)
                group = QTreeWidgetItem([name, "", ""])
                group.setData(0, Qt.ItemDataRole.UserRole, None)
                self._dev_tree.addTopLevelItem(group)
                groups[key] = group
            status = device_status(d)
            if d.problem:
                status = "⚠ " + status
            child = QTreeWidgetItem(group, [d.name, d.driver or d.module or "—", status])
            child.setData(0, Qt.ItemDataRole.UserRole, d)
        for key, item in groups.items():
            item.setText(0, f"{item.text(0)} ({item.childCount()})")
            item.setExpanded(key == "_problem" or key == "display" or bool(text) or mode != "all")

    def _device_details(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        d = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(d, devices.Device):
            item.setExpanded(not item.isExpanded())
            return
        DetailsDialog(
            d.name,
            device_sections(d),
            self,
            [(tr("Find drivers"), lambda: self.page_requested.emit("drivers"))],
        ).exec()

    # --- Yazıcılar ve tarayıcılar ---

    def _build_printers(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 8, 8, 28)
        lay.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(_section(tr("Printers"), content), 1)
        add = QPushButton(tr("+ Add printer"), content)
        add.setProperty("primary", True)
        add.setEnabled(self._settings_cmd is not None)
        add.clicked.connect(self._open_printer_settings)
        top.addWidget(add)
        lay.addLayout(top)
        self._printer_box = QVBoxLayout()
        self._printer_box.setSpacing(12)
        lay.addLayout(self._printer_box)

        # Tarayıcılar
        lay.addWidget(_section(tr("Scanners"), content))
        sc = Card(content)
        row = QHBoxLayout()
        ic = QLabel(sc)
        icons.bind(ic, "scanner", "tile", 34)
        row.addWidget(ic)
        self._scanner_lbl = QLabel(tr("Press “Find scanners” to look for connected scanners."), sc)
        self._scanner_lbl.setWordWrap(True)
        row.addWidget(self._scanner_lbl, 1)
        self._scan_btn = QPushButton(tr("Find scanners"), sc)
        self._scan_btn.clicked.connect(self._find_scanners)
        row.addWidget(self._scan_btn)
        sc.layout.addLayout(row)
        self._scan_app = hardware.scan_app_command()
        if self._scan_app:
            r2 = QHBoxLayout()
            r2.addWidget(QLabel(tr("Scanning program"), sc), 1)
            open_btn = QPushButton(tr("Open"), sc)
            open_btn.clicked.connect(
                lambda: QProcess.startDetached(self._scan_app[0], self._scan_app[1:])
            )
            r2.addWidget(open_btn)
            sc.layout.addLayout(r2)
        r3 = QHBoxLayout()
        support = QLabel(tr("Scanner support: drivers for most brands (SANE, driverless)"), sc)
        support.setObjectName("Secondary")
        support.setWordWrap(True)
        r3.addWidget(support, 1)
        sane_btn = QPushButton(tr("Install"), sc)
        sane_btn.clicked.connect(self._install_scanner_support)
        r3.addWidget(sane_btn)
        sc.layout.addLayout(r3)
        lay.addWidget(sc)

        # Sorun giderme
        lay.addWidget(_section(tr("Having trouble?"), content))
        tc = Card(content)
        for text, desc, button, slot in (
            (
                tr("Printer troubleshooter"),
                tr("Checks the connection, driver and printing service."),
                tr("Run"),
                lambda: self.page_requested.emit("troubleshoot"),
            ),
            (
                tr("Restart printing service"),
                tr("Helps when the print queue is stuck."),
                tr("Restart"),
                self._restart_cups,
            ),
            (
                tr("Printer drivers"),
                tr("Installs drivers for most printer brands (HP, Canon, Epson…)."),
                tr("Install"),
                self._install_drivers,
            ),
        ):
            r = QHBoxLayout()
            t = QVBoxLayout()
            t.addWidget(QLabel(text, tc))
            d = QLabel(desc, tc)
            d.setObjectName("Secondary")
            d.setWordWrap(True)
            t.addWidget(d)
            r.addLayout(t, 1)
            b = QPushButton(button, tc)
            b.clicked.connect(slot)
            r.addWidget(b)
            tc.layout.addLayout(r)
        lay.addWidget(tc)
        lay.addStretch(1)
        return _scroll(content)

    def _load_printers(self) -> None:
        _clear(self._printer_box)
        self._printer_box.addWidget(QLabel(tr("Looking for printers…")))
        self._start(_load_printers, self._on_printers)

    def _on_printers(self, result: tuple | None) -> None:
        _clear(self._printer_box)
        printers, details, usb, suggestions = result or ([], [], [], [])
        by_name = {d.name: d for d in details}
        for p in printers:
            self._printer_box.addWidget(self._printer_card(p, by_name.get(p.name)))
        # Takılı ama kurulmamış USB yazıcılar
        names = " ".join(p.name.lower() for p in printers)
        for dev in usb:
            first = dev.split()[0].lower() if dev.split() else ""
            if first and first in names:
                continue
            self._printer_box.addWidget(
                self._found_card(
                    tr("A printer is connected but not set up: %1").replace("%1", dev),
                    tr("Press Add to set it up."),
                    tr("Add"),
                    self._open_printer_settings,
                )
            )
        for s in suggestions:
            self._printer_box.addWidget(
                self._found_card(
                    tr("Recommended driver for %1").replace("%1", s.device),
                    tr(
                        "Package %1 is in the repository. Press Install, then add the printer."
                    ).replace("%1", s.package),
                    tr("Install"),
                    lambda _=False, pkg=s.package: self._install_package(pkg),
                )
            )
        if not printers:
            empty = Card()
            el = QVBoxLayout()
            el.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            t = QLabel(tr("No printers yet"))
            t.setObjectName("H2")
            t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            el.addWidget(t)
            d = QLabel(
                tr(
                    "Connect the printer with USB or to the same Wi-Fi; Linwas finds it. "
                    "Then press “Add printer”."
                )
            )
            d.setObjectName("Secondary")
            d.setWordWrap(True)
            d.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            el.addWidget(d)
            empty.layout.addLayout(el)
            self._printer_box.addWidget(empty)

    def _printer_card(self, p: hardware.Printer, info: hardware.PrinterDetails | None) -> Card:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(18)
        ic = QLabel(card)
        icons.bind(ic, "printer", "tile", 64)
        row.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(6)
        head = QHBoxLayout()
        name = QLabel(p.name, card)
        name.setStyleSheet("font-size: 19px; font-weight: 700;")
        head.addWidget(name)
        state = Pill(card)
        state.set_state("ok" if p.enabled else "bad", tr("Ready") if p.enabled else tr("Stopped"))
        head.addWidget(state)
        if p.is_default:
            default = Pill(card)
            default.set_state("info", tr("Default"))
            head.addWidget(default)
        head.addStretch(1)
        texts.addLayout(head)
        if info is not None:
            conn = {
                "usb": tr("Connected with USB"),
                "network": tr("Network printer"),
            }.get(info.connection, "")
            line = " · ".join(x for x in (info.model, conn, info.location) if x)
            if line:
                d = QLabel(line, card)
                d.setObjectName("Secondary")
                d.setWordWrap(True)
                texts.addWidget(d)
            for s in info.supplies:
                m = Meter(s.name, card)
                m.set(s.level, percent(s.level))
                texts.addWidget(m)
            jobs = (
                tr("%1 document(s) waiting").replace("%1", str(info.jobs))
                if info.jobs
                else tr("No documents waiting")
            )
            j = QLabel(jobs, card)
            j.setObjectName("Secondary")
            texts.addWidget(j)
        row.addLayout(texts, 1)
        card.layout.addLayout(row)
        acts = QHBoxLayout()
        acts.addStretch(1)
        test = QPushButton(tr("Test page"), card)
        test.clicked.connect(lambda: self._test_page(p.name))
        acts.addWidget(test)
        queue = QPushButton(tr("Queue"), card)
        queue.clicked.connect(lambda: self._show_queue(p.name))
        acts.addWidget(queue)
        if not p.is_default:
            make_default = QPushButton(tr("Make default"), card)
            make_default.clicked.connect(lambda: self._make_default(p.name))
            acts.addWidget(make_default)
        options = QPushButton(tr("Options and removal…"), card)
        options.setEnabled(self._settings_cmd is not None)
        options.clicked.connect(self._open_printer_settings)
        acts.addWidget(options)
        card.layout.addLayout(acts)
        return card

    def _found_card(self, title: str, desc: str, button: str, slot) -> Card:  # noqa: ANN001
        card = Card()
        row = QHBoxLayout()
        ic = QLabel(card)
        icons.bind(ic, "printer", "tile", 34)
        row.addWidget(ic)
        t = QVBoxLayout()
        a = QLabel(title, card)
        a.setStyleSheet("font-weight: 600;")
        a.setWordWrap(True)
        t.addWidget(a)
        b = QLabel(desc, card)
        b.setObjectName("Secondary")
        b.setWordWrap(True)
        t.addWidget(b)
        row.addLayout(t, 1)
        btn = QPushButton(button, card)
        btn.setProperty("primary", True)
        btn.clicked.connect(slot)
        row.addWidget(btn)
        card.layout.addLayout(row)
        return card

    def _test_page(self, name: str) -> None:
        ok = hardware.print_test_page(name)
        QMessageBox.information(
            self,
            tr("Test page"),
            tr("The test page was sent to %1.").replace("%1", name)
            if ok
            else tr("The test page could not be sent. Try “Printer troubleshooter”."),
        )
        self._load_printers()

    def _make_default(self, name: str) -> None:
        hardware.set_default_printer(name)
        self._load_printers()

    def _show_queue(self, name: str) -> None:
        jobs = hardware.list_jobs(name)
        rows = [(str(i + 1), job) for i, job in enumerate(jobs)] or [(tr("Queue"), tr("empty"))]

        def cancel_all() -> None:
            hardware.cancel_jobs(name)
            dialog.accept()
            self._load_printers()

        actions = [(tr("Cancel all my documents"), cancel_all)] if jobs else []
        dialog = DetailsDialog(
            tr("Print queue: %1").replace("%1", name), [(tr("Documents"), rows)], self, actions
        )
        dialog.exec()

    # --- Yükleme ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if not self._loaded:
            self._loaded = True
            self._load_devices()
            self._load_printers()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            self._overview.reload_memory_report()
            self._load_devices()
            self._load_printers()

    def _start(self, fn, slot) -> None:  # noqa: ANN001
        worker = _Worker(fn)
        worker.done.connect(slot)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    # --- İşlemler ---

    def _memory_report(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Read memory module details"),
                steps=[TaskStep(op_id="hardware.memory_report", params={})],
            )
        )

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
                    "installing scanner support."
                )
            )
