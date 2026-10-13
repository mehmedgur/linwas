"""Donanım bilgisi eklentisinin arayüz parçaları: bileşen kartları, ayrıntı pencereleri, rapor."""

from __future__ import annotations

import html
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import devices as devs
from linwas.plugins.hardware_info import probe
from linwas.ui import icons
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("HardwareInfo", text)


def size_text(n: int) -> str:
    return QLocale().formattedDataSize(n, 1, QLocale.DataSizeFormat.DataSizeSIFormat)


# Durum rozeti renkleri: açık ve koyu temada okunur
_STATE_STYLE = {
    probe.OK: ("#1e6b1e", "#e3f5e1"),
    probe.WARN: ("#8a5300", "#fff1cc"),
    probe.BAD: ("#a4161a", "#fde2e4"),
    "info": ("#0050a8", "#e1ecfb"),
}


def state_text(state: str) -> str:
    return {
        probe.OK: tr("Good"),
        probe.WARN: tr("Check"),
        probe.BAD: tr("Needs attention"),
    }.get(state, "")


class Pill(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hide()

    def set_state(self, state: str, text: str | None = None) -> None:
        fg, bg = _STATE_STYLE.get(state, _STATE_STYLE["info"])
        self.setText(text or state_text(state))
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:10px; padding:2px 10px;"
            " font-size: 13px; font-weight: bold;"
        )
        self.setVisible(bool(self.text()))


class Meter(QWidget):
    """Ad · çubuk · değer satırı."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        name = QLabel(label, self)
        name.setObjectName("Secondary")
        name.setMinimumWidth(90)
        row.addWidget(name)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setAccessibleName(label)
        row.addWidget(self._bar, 1)
        self._value = QLabel("", self)
        self._value.setMinimumWidth(72)
        row.addWidget(self._value)

    def set(self, percent: int, text: str) -> None:
        self._bar.setValue(max(0, min(100, percent)))
        self._value.setText(text)


class Tile(Card):
    """Bileşen kartı: simge, başlık, durum rozeti, içerik ve "Ayrıntılar"."""

    details = Signal()

    def __init__(self, title: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = QLabel(self)
        icons.bind(ic, icon, "tile", 34)
        head.addWidget(ic)
        t = QLabel(title, self)
        t.setObjectName("H2")
        head.addWidget(t, 1)
        self.pill = Pill(self)
        head.addWidget(self.pill)
        self.layout.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self.layout.addLayout(self.body)
        self.layout.addStretch(1)
        foot = QHBoxLayout()
        self.link = QToolButton(self)
        self.link.setObjectName("SettingLink")
        self.link.setText(tr("Details"))
        self.link.setAccessibleName(tr("Details") + ": " + title)
        self.link.clicked.connect(self.details)
        foot.addWidget(self.link)
        foot.addStretch(1)
        self.layout.addLayout(foot)

    def clear(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def big(self, text: str) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setStyleSheet("font-size: 20px; font-weight: 600;")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)
        return lbl

    def line(self, text: str, secondary: bool = True) -> QLabel:
        lbl = QLabel(text, self)
        if secondary:
            lbl.setObjectName("Secondary")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)
        return lbl

    def sub(self, name: str, detail: str) -> None:
        n = QLabel(name, self)
        n.setStyleSheet("font-weight: 600;")
        n.setWordWrap(True)
        self.body.addWidget(n)
        self.line(detail)

    def meter(self, label: str) -> Meter:
        m = Meter(label, self)
        self.body.addWidget(m)
        return m


# --- Veri ---


@dataclass
class StaticInfo:
    machine: probe.Machine
    cpu: probe.Cpu
    disks: list[probe.Disk]
    displays: list[probe.Display]
    batteries: list[probe.Battery]
    devices: list[devs.Device]
    distro: str = ""
    desktop: str = ""
    memory_report: probe.MemoryReport | None = None
    root_usage: tuple[int, int] = (0, 0)  # (kullanılan, toplam)
    extra: dict[str, str] = field(default_factory=dict)


def load_static() -> StaticInfo:
    from linwas.backend.desktop import detect_desktop
    from linwas.backend.distro import detect_distro

    try:
        du = shutil.disk_usage("/")
        root = (du.total - du.free, du.total)
    except OSError:
        root = (0, 0)
    return StaticInfo(
        machine=probe.machine_info(),
        cpu=probe.cpu_info(),
        disks=probe.disks(),
        displays=probe.displays(),
        batteries=probe.batteries(),
        devices=devs.list_devices(),
        distro=detect_distro().display_name,
        desktop=detect_desktop(os.environ).value,
        memory_report=probe.read_memory_report(),
        root_usage=root,
    )


_VENDOR_SHORT = (
    (r"^Intel Corporation\b", "Intel"),
    (r"^NVIDIA Corporation\b", "NVIDIA"),
    (r"^Advanced Micro Devices, Inc\. \[AMD/ATI\]", "AMD"),
    (r"^Advanced Micro Devices, Inc\. \[AMD\]", "AMD"),
    (r"^Realtek Semiconductor Co\., Ltd\.", "Realtek"),
    (r"^Qualcomm Atheros", "Qualcomm"),
    (r"^MEDIATEK Corp\.", "MediaTek"),
    (r"^Broadcom Inc\. and subsidiaries", "Broadcom"),
)


def short_device_name(name: str) -> str:
    """Kısa ad: "NVIDIA Corporation TU117M [GeForce GTX 1650 Mobile]" → "NVIDIA GeForce…"."""
    vendor = ""
    for pattern, short in _VENDOR_SHORT:
        if re.match(pattern, name):
            vendor = short
            name = re.sub(pattern, "", name).strip()
            break
    m = re.search(r"\[([^\]]+)\]", name)
    model = m.group(1) if m else name
    return f"{vendor} {model}".strip()


class _Loader(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(load_static())
        except Exception:
            self.done.emit(None)


# --- Ayrıntı penceresi ---

Section = tuple[str, list[tuple[str, str]]]


class DetailsDialog(QDialog):
    """Bileşen ya da aygıt ayrıntıları (ayrı pencere)."""

    def __init__(
        self,
        title: str,
        sections: list[Section],
        parent: QWidget | None = None,
        actions: list[tuple[str, object]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 560)
        self._text = title + "\n"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)
        h = QLabel(title, self)
        h.setObjectName("H1")
        h.setWordWrap(True)
        outer.addWidget(h)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 6, 0)
        body.setSpacing(12)
        for name, rows in sections:
            if not rows:
                continue
            card = Card(content)
            st = QLabel(name, card)
            st.setObjectName("H2")
            card.layout.addWidget(st)
            form = QFormLayout()
            form.setHorizontalSpacing(18)
            form.setVerticalSpacing(8)
            self._text += f"\n{name}\n"
            for key, value in rows:
                k = QLabel(key, card)
                k.setObjectName("Secondary")
                v = QLabel(value or "—", card)
                v.setWordWrap(True)
                v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                form.addRow(k, v)
                self._text += f"  {key}: {value or '—'}\n"
            card.layout.addLayout(form)
            body.addWidget(card)
        body.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        row = QHBoxLayout()
        for label, slot in actions or []:
            b = QPushButton(label, self)
            b.clicked.connect(slot)  # type: ignore[arg-type]
            row.addWidget(b)
        row.addStretch(1)
        copy = QPushButton(tr("Copy"), self)
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._text))
        row.addWidget(copy)
        close = QPushButton(tr("Close"), self)
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        outer.addLayout(row)


def device_status(d: devs.Device) -> str:
    if d.driver:
        return tr("Working")
    if d.module:
        return tr("Driver available but not loaded")
    if d.problem:
        return tr("No driver")
    return tr("No driver needed")


def device_sections(d: devs.Device) -> list[Section]:
    vendor, _, product = d.ids.partition(":")
    return [
        (
            tr("Device"),
            [
                (tr("Name"), d.name),
                (tr("Connection"), "USB" if d.bus == "usb" else "PCI"),
                (tr("Vendor ID"), vendor),
                (tr("Product ID"), product),
            ],
        ),
        (
            tr("Driver"),
            [
                (tr("Status"), device_status(d)),
                (tr("Loaded driver"), d.driver),
                (tr("Available module"), d.module),
            ],
        ),
    ]


# --- Genel bakış ---


class HardwareOverview(QWidget):
    """Bilgisayar kartı + bileşen kartları; işlemci ve bellek 2 sn'de bir güncellenir."""

    page_requested = Signal(str)
    memory_report_requested = Signal()  # sayfa root görevini başlatır (parola sorulur)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info: StaticInfo | None = None
        self._loader: _Loader | None = None
        self._sampler = probe.CpuSampler()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._tick)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        # Bilgisayar kartı
        self._hero = Card(self)
        row = QHBoxLayout()
        row.setSpacing(20)
        pc = QLabel(self._hero)
        icons.bind(pc, "laptop", "tile", 88)
        row.addWidget(pc)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        self._title = QLabel(tr("Reading hardware…"), self._hero)
        self._title.setStyleSheet("font-size: 24px; font-weight: 700;")
        texts.addWidget(self._title)
        self._subtitle = QLabel("", self._hero)
        self._subtitle.setObjectName("Secondary")
        self._subtitle.setWordWrap(True)
        texts.addWidget(self._subtitle)
        self._chips = QLabel("", self._hero)
        self._chips.setObjectName("Caption")
        self._chips.setWordWrap(True)
        texts.addWidget(self._chips)
        row.addLayout(texts, 1)
        side = QVBoxLayout()
        self._summary_pill = Pill(self._hero)
        side.addWidget(self._summary_pill)
        self._summary = QLabel("", self._hero)
        self._summary.setObjectName("Secondary")
        side.addWidget(self._summary)
        side.addStretch(1)
        row.addLayout(side)
        self._hero.layout.addLayout(row)
        lay.addWidget(self._hero)

        sec = QLabel(tr("Components"), self)
        sec.setObjectName("Secondary")
        lay.addWidget(sec)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cpu = Tile(tr("Processor"), "cpu", self)
        self.mem = Tile(tr("Memory (RAM)"), "memory", self)
        self.gpu = Tile(tr("Graphics cards"), "gpu", self)
        self.disk = Tile(tr("Storage"), "storage", self)
        self.screen = Tile(tr("Display"), "display", self)
        self.battery = Tile(tr("Battery"), "battery", self)
        self.net = Tile(tr("Network and Bluetooth"), "network", self)
        self.av = Tile(tr("Sound and camera"), "sound", self)
        tiles = [
            self.cpu,
            self.mem,
            self.gpu,
            self.disk,
            self.screen,
            self.battery,
            self.net,
            self.av,
        ]
        for i, tile in enumerate(tiles):
            grid.addWidget(tile, i // 2, i % 2)
        lay.addLayout(grid)
        self.cpu.details.connect(self._cpu_details)
        self.mem.details.connect(self._mem_details)
        self.gpu.details.connect(lambda: self._group_details(tr("Graphics cards"), ("display",)))
        self.disk.details.connect(self._disk_details)
        self.screen.details.connect(lambda: self.page_requested.emit("display"))
        self.battery.details.connect(self._battery_details)
        self.net.details.connect(
            lambda: self._group_details(tr("Network and Bluetooth"), ("network", "bluetooth"))
        )
        self.av.details.connect(
            lambda: self._group_details(tr("Sound and camera"), ("audio", "camera"))
        )
        self._cpu_load: Meter | None = None
        self._cpu_temp: Meter | None = None
        self._mem_use: Meter | None = None
        self._swap_use: Meter | None = None

    # Yükleme ve canlı güncelleme

    def refresh(self) -> None:
        if self._loader is not None and self._loader.isRunning():
            return
        self._loader = _Loader()
        self._loader.done.connect(self._on_loaded)
        self._loader.start()

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        if self.info is None:
            self.refresh()
        self._timer.start()
        super().showEvent(event)  # type: ignore[misc]

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[misc]

    def reload_memory_report(self) -> None:
        if self.info is not None:
            self.info.memory_report = probe.read_memory_report()
            self._fill_memory()

    def _tick(self) -> None:
        if self._cpu_load is not None:
            load = self._sampler.sample()
            self._cpu_load.set(load, f"%{load}")
            temp = probe.cpu_temperature()
            if self._cpu_temp is not None and temp is not None:
                self._cpu_temp.set(round(temp), f"{temp:.0f} °C")
                self.cpu.pill.set_state(probe.cpu_temp_state(temp))
        mem = probe.memory_usage()
        if self._mem_use is not None and mem.total:
            self._mem_use.set(mem.percent, size_text(mem.used))
            self.mem.pill.set_state(probe.usage_state(mem.percent))
        if self._swap_use is not None and mem.swap_total:
            pct = round(mem.swap_used * 100 / mem.swap_total)
            self._swap_use.set(pct, size_text(mem.swap_used))

    def _on_loaded(self, info: object) -> None:
        if not isinstance(info, StaticInfo):
            self._title.setText(tr("Hardware information could not be read."))
            return
        self.info = info
        m = info.machine
        self._title.setText(m.title or tr("This computer"))
        kind = {"laptop": tr("Laptop"), "desktop": tr("Desktop computer")}.get(m.chassis, "")
        self._subtitle.setText(" · ".join(x for x in (m.product, kind) if x))
        desktop = info.desktop.upper() if len(info.desktop) <= 5 else info.desktop.title()
        chips = [f"{info.distro} · {desktop}"]
        if m.bios_version:
            bios = tr("BIOS %1").replace("%1", m.bios_version)
            if m.bios_date:
                bios += " · " + QLocale().toString(m.bios_date, QLocale.FormatType.ShortFormat)
            chips.append(bios)
        if m.board:
            chips.append(tr("Board %1").replace("%1", m.board))
        self._chips.setText("   ·   ".join(chips))
        problems = [d for d in info.devices if d.problem]
        if problems:
            self._summary_pill.set_state(
                probe.BAD, tr("%1 device(s) without a driver").replace("%1", str(len(problems)))
            )
        else:
            self._summary_pill.set_state(probe.OK, tr("Everything is working"))
        self._summary.setText(tr("%1 devices").replace("%1", str(len(info.devices))))
        self._fill_cpu()
        self._fill_memory()
        self._fill_gpu()
        self._fill_disks()
        self._fill_display()
        self._fill_battery()
        self._fill_group(self.net, ("network", "bluetooth"), "network")
        self._fill_group(self.av, ("audio", "camera"), "")
        self._tick()

    # Kartları doldurma

    def _fill_cpu(self) -> None:
        assert self.info is not None
        c = self.info.cpu
        t = self.cpu
        t.clear()
        t.big(c.model or tr("Unknown processor"))
        parts = []
        if c.cores:
            parts.append(tr("%1 cores").replace("%1", str(c.cores)))
        if c.threads:
            parts.append(tr("%1 threads").replace("%1", str(c.threads)))
        if c.max_mhz:
            ghz = QLocale().toString(c.max_mhz / 1000, "f", 1)
            parts.append(tr("up to %1 GHz").replace("%1", ghz))
        t.line(" · ".join(parts))
        self._cpu_load = t.meter(tr("Load"))
        self._cpu_temp = t.meter(tr("Temperature")) if probe.cpu_temperature() is not None else None
        t.pill.set_state(probe.OK)

    def _fill_memory(self) -> None:
        assert self.info is not None
        t = self.mem
        t.clear()
        mem = probe.memory_usage()
        report = self.info.memory_report
        installed = _installed_memory(report)
        t.big(installed or size_text(mem.total))
        if report and report.modules:
            t.line(_modules_text(report))
        else:
            t.line(tr("%1 usable").replace("%1", size_text(mem.total)))
            show = QPushButton(tr("Show module details…"), t)
            show.setToolTip(tr("Type, speed and slots; needs the administrator password."))
            show.clicked.connect(self.memory_report_requested)
            t.body.addWidget(show)
        self._mem_use = t.meter(tr("In use"))
        self._swap_use = t.meter(tr("Swap")) if mem.swap_total else None
        t.pill.set_state(probe.usage_state(mem.percent))

    def _fill_gpu(self) -> None:
        assert self.info is not None
        t = self.gpu
        t.clear()
        gpus = [d for d in self.info.devices if d.group == "display"]
        for d in gpus:
            t.sub(short_device_name(d.name), _driver_text(d))
        if not gpus:
            t.line(tr("No graphics card found."))
        if len(gpus) > 1:
            link = QToolButton(t)
            link.setObjectName("SettingLink")
            link.setText(tr("Hybrid graphics settings"))
            link.clicked.connect(lambda: self.page_requested.emit("drivers"))
            t.body.addWidget(link)
        t.pill.set_state(probe.BAD if any(d.problem for d in gpus) else probe.OK)

    def _fill_disks(self) -> None:
        assert self.info is not None
        t = self.disk
        t.clear()
        kinds = {"nvme": tr("NVMe SSD"), "ssd": tr("SSD"), "hdd": tr("Hard disk")}
        for d in self.info.disks:
            name = " · ".join(x for x in (d.model or d.name, d.size, kinds.get(d.kind, "")) if x)
            detail = []
            detail.append(tr("External (USB)") if d.transport == "usb" else tr("Internal"))
            if d.system:
                detail.append(tr("system disk"))
            if d.temperature is not None:
                detail.append(f"{d.temperature:.0f} °C")
            t.sub(name, " · ".join(detail))
        used, total = self.info.root_usage
        if total:
            pct = round(used * 100 / total)
            t.meter(tr("System")).set(pct, f"%{pct}")
            t.pill.set_state(probe.usage_state(pct, 85, 95))
        else:
            t.pill.set_state(probe.OK)

    def _fill_display(self) -> None:
        assert self.info is not None
        t = self.screen
        t.clear()
        for d in self.info.displays:
            name = tr("Built-in display") if d.internal else d.output
            if d.diagonal_in:
                name += " · " + QLocale().toString(d.diagonal_in, "f", 1) + "″"
            t.sub(name, f"{d.width} × {d.height} · {d.refresh:.0f} Hz")
        if not self.info.displays:
            t.line(tr("Display details are not available in this session."))
        t.link.setText(tr("Display & Scaling"))
        t.pill.hide()

    def _fill_battery(self) -> None:
        assert self.info is not None
        t = self.battery
        t.clear()
        bats = [b for b in self.info.batteries if b.health is not None]
        t.setVisible(bool(self.info.batteries))
        for b in bats:
            t.big(tr("Health %1%").replace("%1", str(b.health)))
            parts = []
            if b.cycles:
                parts.append(tr("%1 charge cycles").replace("%1", str(b.cycles)))
            if b.full_wh and b.design_wh:
                parts.append(f"{b.full_wh:.0f} / {b.design_wh:.0f} Wh")
            if parts:
                t.line(" · ".join(parts))
            t.meter(tr("Capacity")).set(b.health or 0, f"%{b.health}")
            t.pill.set_state(probe.battery_state(b.health))
        t.link.setText(tr("Battery care"))

    def _fill_group(self, t: Tile, groups: tuple[str, ...], page: str) -> None:
        assert self.info is not None
        t.clear()
        items = [d for d in self.info.devices if d.group in groups]
        for d in items[:4]:
            t.sub(short_device_name(d.name), _driver_text(d))
        if not items:
            t.line(tr("No device found."))
        t.pill.set_state(probe.BAD if any(d.problem for d in items) else probe.OK)

    # Ayrıntı pencereleri

    def _cpu_details(self) -> None:
        if self.info is None:
            return
        c = self.info.cpu
        temp = probe.cpu_temperature()
        rows = [
            (tr("Model"), c.model),
            (tr("Cores"), str(c.cores or "")),
            (tr("Threads"), str(c.threads or "")),
            (tr("Maximum speed"), f"{c.max_mhz} MHz" if c.max_mhz else ""),
            (tr("Temperature"), f"{temp:.0f} °C" if temp is not None else ""),
        ]
        DetailsDialog(tr("Processor"), [(tr("Processor"), rows)], self).exec()

    def _mem_details(self) -> None:
        if self.info is None:
            return
        mem = probe.memory_usage()
        sections: list[Section] = [
            (
                tr("Usage"),
                [
                    (tr("Usable"), size_text(mem.total)),
                    (tr("In use"), size_text(mem.used)),
                    (tr("Swap"), size_text(mem.swap_total) if mem.swap_total else tr("none")),
                ],
            )
        ]
        report = self.info.memory_report
        actions: list[tuple[str, object]] = []
        if report and report.modules:
            sections.append(
                (
                    tr("Slots"),
                    [
                        (tr("Slots"), str(report.slots or "")),
                        (tr("Maximum supported"), report.max_capacity),
                    ],
                )
            )
            for mod in report.modules:
                sections.append(
                    (
                        mod.locator or tr("Module"),
                        [
                            (tr("Size"), mod.size),
                            (tr("Type"), mod.type),
                            (tr("Speed"), mod.speed),
                            (tr("Manufacturer"), mod.manufacturer),
                            (tr("Part number"), mod.part),
                        ],
                    )
                )
        else:
            actions.append((tr("Show module details…"), self.memory_report_requested.emit))
        DetailsDialog(tr("Memory (RAM)"), sections, self, actions).exec()

    def _disk_details(self) -> None:
        if self.info is None:
            return
        kinds = {"nvme": tr("NVMe SSD"), "ssd": tr("SSD"), "hdd": tr("Hard disk")}
        sections: list[Section] = []
        for d in self.info.disks:
            sections.append(
                (
                    d.model or d.name,
                    [
                        (tr("Device"), "/dev/" + d.name),
                        (tr("Size"), d.size),
                        (tr("Type"), kinds.get(d.kind, d.kind)),
                        (tr("Connection"), d.transport.upper()),
                        (tr("System disk"), tr("Yes") if d.system else tr("No")),
                        (
                            tr("Temperature"),
                            f"{d.temperature:.0f} °C" if d.temperature is not None else "",
                        ),
                    ],
                )
            )
        DetailsDialog(
            tr("Storage"),
            sections,
            self,
            [(tr("Disk Cleanup"), lambda: self.page_requested.emit("cleanup"))],
        ).exec()

    def _battery_details(self) -> None:
        self.page_requested.emit("power")

    def _group_details(self, title: str, groups: tuple[str, ...]) -> None:
        if self.info is None:
            return
        sections: list[Section] = []
        for d in self.info.devices:
            if d.group in groups:
                sections.extend(
                    (f"{short_device_name(d.name)} — {name}", rows)
                    for name, rows in device_sections(d)
                )
        DetailsDialog(
            title,
            sections,
            self,
            [(tr("Find drivers"), lambda: self.page_requested.emit("drivers"))],
        ).exec()

    # Rapor ve kopyalama

    def summary_lines(self) -> list[tuple[str, str]]:
        if self.info is None:
            return []
        i = self.info
        mem = probe.memory_usage()
        lines = [
            (tr("Computer"), f"{i.machine.title} ({i.machine.product})"),
            (tr("System"), f"{i.distro} · {i.desktop}"),
            (tr("BIOS"), i.machine.bios_version),
            (tr("Processor"), f"{i.cpu.model} · {i.cpu.cores}/{i.cpu.threads}"),
            (tr("Memory (RAM)"), size_text(mem.total)),
        ]
        if i.memory_report and i.memory_report.modules:
            lines.append((tr("Memory modules"), _modules_text(i.memory_report)))
        for d in i.devices:
            if d.group in ("display", "network", "bluetooth", "audio", "camera"):
                lines.append(
                    (tr("Device"), f"{short_device_name(d.name)} [{d.ids}] · {_driver_text(d)}")
                )
        for d in i.disks:
            lines.append((tr("Disk"), f"{d.model or d.name} · {d.size} · {d.kind}"))
        for s in i.displays:
            lines.append((tr("Display"), f"{s.output} · {s.width}×{s.height} · {s.refresh:.0f} Hz"))
        for b in i.batteries:
            if b.health is not None:
                lines.append((tr("Battery"), f"%{b.health} · {b.cycles or '—'}"))
        return lines

    def copy_summary(self) -> None:
        text = "\n".join(f"{k}: {v}" for k, v in self.summary_lines())
        QGuiApplication.clipboard().setText(text)

    def open_report(self) -> None:
        rows = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>"
            for k, v in self.summary_lines()
        )
        page = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(tr('System report'))}</title>"
            "<style>body{font-family:'Noto Sans',sans-serif;margin:40px;color:#1d1d1f}"
            "table{border-collapse:collapse}"
            "th{text-align:left;color:#6e6e73;padding:6px 18px 6px 0;vertical-align:top}"
            "td{padding:6px 0}</style></head><body>"
            f"<h1>{html.escape(tr('System report'))}</h1><table>{rows}</table></body></html>"
        )
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        path = Path(base) / "linwas" / "system-report.html"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page, encoding="utf-8")
        except OSError:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _driver_text(d: devs.Device) -> str:
    if d.driver:
        return tr("Driver %1 · working").replace("%1", d.driver)
    return device_status(d)


def _installed_memory(report: probe.MemoryReport | None) -> str:
    if not report or not report.modules:
        return ""
    total_gb = 0
    for mod in report.modules:
        m = re.match(r"^(\d+)\s*(GB|MB)", mod.size)
        if m:
            total_gb += int(m.group(1)) / (1024 if m.group(2) == "MB" else 1)
    return f"{total_gb:g} GB" if total_gb else ""


def _modules_text(report: probe.MemoryReport) -> str:
    first = report.modules[0]
    kind = " ".join(x for x in (first.type, first.speed) if x)
    text = f"{len(report.modules)} × {first.size}"
    if kind:
        text += f" {kind}"
    if report.slots:
        text += " · " + tr("%1 of %2 slots used").replace("%1", str(len(report.modules))).replace(
            "%2", str(report.slots)
        )
    return text
