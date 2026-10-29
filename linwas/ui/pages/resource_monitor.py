# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kaynak izleyici sayfası: CPU, bellek, GPU, disk ve ağ kullanımının canlı grafikleri."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
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

from linwas.backend.resource_monitor import (
    GpuStats,
    ResourceSampler,
    ResourceSnapshot,
    format_bytes,
)
from linwas.translations import percent
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.fit import fit_width
from linwas.ui.widgets.line_chart import LineChart

_INTERVAL_MS = 1000
_HISTORY = 60  # bir dakikalık grafik


def tr(text: str) -> str:
    return QCoreApplication.translate("ResourceMonitorPage", text)


def _rate(value: float) -> str:
    return tr("{value}/s").format(value=format_bytes(value))


def _pct(used: float, total: float) -> float:
    return 100.0 * used / total if total else 0.0


class _SampleWorker(QThread):
    done = Signal(object)

    def __init__(self, sampler: ResourceSampler) -> None:
        super().__init__()
        self._sampler = sampler

    def run(self) -> None:
        try:
            self.done.emit(self._sampler.sample())
        except Exception:
            self.done.emit(None)


class _MetricCard(Card):
    """Başlık + büyük değer + grafik + ayrıntı satırı."""

    def __init__(
        self,
        title: str,
        roles: tuple[str, ...] = ("accent",),
        maximum: float | None = 100.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        head = QHBoxLayout()
        name = QLabel(title, self)
        name.setObjectName("SectionTitle")
        head.addWidget(name)
        head.addStretch(1)
        self.value = QLabel("—", self)
        self.value.setObjectName("H2")
        head.addWidget(self.value)
        self.layout.addLayout(head)
        self.chart = LineChart(roles, maximum, _HISTORY, self)
        self.layout.addWidget(self.chart)
        self.detail = QLabel("", self)
        self.detail.setObjectName("Secondary")
        self.detail.setWordWrap(True)
        self.layout.addWidget(self.detail)


class ResourceMonitorPage(BasePage):
    """Kaynak izleyici: sayfa görünürken saniyede bir ölçer, gizlenince durur."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sampler = ResourceSampler(top_count=8)
        self._worker: _SampleWorker | None = None
        self._paused = False

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        head = QHBoxLayout()
        title = QLabel(tr("Resource Monitor"), content)
        title.setObjectName("H1")
        head.addWidget(title)
        head.addStretch(1)
        self._pause_btn = QPushButton(tr("Pause"), content)
        self._pause_btn.clicked.connect(self._toggle_pause)
        fit_width(self._pause_btn, tr("Pause"), tr("Resume"))
        head.addWidget(self._pause_btn)
        outer.addLayout(head)
        sub = QLabel(tr("Live usage, updated every second. Graphs show the last minute."), content)
        sub.setObjectName("Secondary")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        self._cpu = _MetricCard(tr("Processor (CPU)"), parent=content)
        self._mem = _MetricCard(tr("Memory (RAM)"), ("success",), parent=content)
        self._disk = _MetricCard(tr("Disk"), ("accent", "warning"), None, content)
        self._net = _MetricCard(tr("Network"), ("accent", "success"), None, content)
        self._grid.addWidget(self._cpu, 0, 0)
        self._grid.addWidget(self._mem, 0, 1)
        self._grid.addWidget(self._disk, 1, 0)
        self._grid.addWidget(self._net, 1, 1)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        outer.addLayout(self._grid)
        # GPU kartları ilk ölçümde kurulur (sayısı makineye göre değişir)
        self._gpu_cards: list[_MetricCard] = []

        procs = Card(content)
        name = QLabel(tr("Top processes"), procs)
        name.setObjectName("SectionTitle")
        procs.layout.addWidget(name)
        self._tree = QTreeWidget(procs)
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels([tr("Name"), "PID", "CPU %", tr("Memory")])
        self._tree.setRootIsDecorated(False)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setMinimumHeight(260)
        procs.layout.addWidget(self._tree)
        note = QLabel(tr("CPU % is per core: a process using two full cores shows 200%."), procs)
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        procs.layout.addWidget(note)
        outer.addWidget(procs)
        outer.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._refresh)

    # --- Ölçüm döngüsü ---

    def _refresh(self) -> None:
        if self._worker and self._worker.isRunning():
            return  # önceki ölçüm sürüyor (ör. nvidia-smi yavaş)
        self._worker = _SampleWorker(self._sampler)
        self._worker.done.connect(self._on_sample)
        self._worker.start()

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._pause_btn.setText(tr("Resume") if self._paused else tr("Pause"))
        if self._paused:
            self._timer.stop()
        else:
            self._timer.start()
            self._refresh()

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        if not self._paused:
            self._timer.start()
            self._refresh()
        super().showEvent(event)  # type: ignore[misc]

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[misc]

    # --- Gösterim ---

    def _on_sample(self, snap: object) -> None:
        if not isinstance(snap, ResourceSnapshot):
            return
        self._show_cpu(snap)
        self._show_memory(snap)
        self._show_disk(snap)
        self._show_network(snap)
        self._show_gpus(snap.gpus)
        self._show_processes(snap)

    def _show_cpu(self, s: ResourceSnapshot) -> None:
        self._cpu.value.setText(percent(f"{s.cpu_pct:.0f}"))
        self._cpu.chart.add(s.cpu_pct)
        parts = [tr("{n} cores").format(n=len(s.cpu_cores))]
        if s.cpu_freq_mhz:
            parts.append(tr("{mhz} MHz").format(mhz=s.cpu_freq_mhz))
        if s.cpu_temp_c is not None:
            parts.append(f"{s.cpu_temp_c:.0f} °C")
        parts.append(
            tr("Load: {a:.2f} {b:.2f} {c:.2f}").format(
                a=s.load_avg[0], b=s.load_avg[1], c=s.load_avg[2]
            )
        )
        busiest = max(s.cpu_cores, default=0.0)
        parts.append(tr("Busiest core: {pct:.0f}%").format(pct=busiest))
        self._cpu.detail.setText(" · ".join(parts))

    def _show_memory(self, s: ResourceSnapshot) -> None:
        pct = _pct(s.mem_used, s.mem_total)
        self._mem.value.setText(
            tr("{used} of {total}").format(
                used=format_bytes(s.mem_used), total=format_bytes(s.mem_total)
            )
        )
        self._mem.chart.add(pct)
        parts = [percent(f"{pct:.0f}"), tr("Cache: {size}").format(size=format_bytes(s.mem_cache))]
        if s.swap_total:
            parts.append(
                tr("Swap: {used} of {total}").format(
                    used=format_bytes(s.swap_used), total=format_bytes(s.swap_total)
                )
            )
        self._mem.detail.setText(" · ".join(parts))

    def _show_disk(self, s: ResourceSnapshot) -> None:
        self._disk.value.setText(percent(f"{s.disk_busy_pct:.0f}"))
        self._disk.chart.add(s.disk_read_bps, s.disk_write_bps)
        lines = [
            tr("Read {read} · Write {write}").format(
                read=_rate(s.disk_read_bps), write=_rate(s.disk_write_bps)
            )
        ]
        for mount, used, total in s.disk_usage:
            lines.append(
                tr("{mount}: {used} of {total} used").format(
                    mount=mount, used=format_bytes(used), total=format_bytes(total)
                )
            )
        self._disk.detail.setText("\n".join(lines))
        self._disk.value.setToolTip(tr("Share of time the disks were busy"))

    def _show_network(self, s: ResourceSnapshot) -> None:
        self._net.value.setText(f"↓ {_rate(s.net_rx_bps)}  ↑ {_rate(s.net_tx_bps)}")
        self._net.chart.add(s.net_rx_bps, s.net_tx_bps)
        lines = [
            tr("Since startup: received {rx} · sent {tx}").format(
                rx=format_bytes(s.net_rx_total), tx=format_bytes(s.net_tx_total)
            )
        ]
        if s.net_interfaces:
            lines.append(", ".join(s.net_interfaces))
        else:
            lines.append(tr("No network adapter found"))
        self._net.detail.setText("\n".join(lines))

    def _show_gpus(self, gpus: list[GpuStats]) -> None:
        if len(gpus) != len(self._gpu_cards):
            for card in self._gpu_cards:
                self._grid.removeWidget(card)
                card.deleteLater()
            self._gpu_cards = []
            for i in range(len(gpus)):
                card = _MetricCard(
                    tr("Graphics (GPU)"), ("warning",), parent=self._cpu.parentWidget()
                )
                self._grid.addWidget(card, 2 + i // 2, i % 2)
                self._gpu_cards.append(card)
        for card, gpu in zip(self._gpu_cards, gpus, strict=True):
            self._show_gpu(card, gpu)

    def _show_gpu(self, card: _MetricCard, gpu: GpuStats) -> None:
        parts = [gpu.name]
        if gpu.state == "sleeping":
            card.value.setText(tr("Sleeping"))
            card.chart.add(0)
            parts.append(tr("Not queried so it can stay asleep and save power"))
        elif gpu.busy_pct is not None:
            card.value.setText(percent(f"{gpu.busy_pct:.0f}"))
            card.chart.add(gpu.busy_pct)
        elif gpu.freq_mhz is not None and gpu.freq_max_mhz:
            # Intel: kullanım root olmadan okunamaz, frekans oranı çizilir
            card.value.setText(tr("{mhz} MHz").format(mhz=gpu.freq_mhz))
            card.chart.add(_pct(gpu.freq_mhz, gpu.freq_max_mhz))
            parts.append(tr("Usage needs administrator rights; the graph shows clock speed"))
        else:
            card.value.setText("—")
            card.chart.add(0)
            parts.append(tr("Usage cannot be measured with this driver"))
        if gpu.mem_used is not None and gpu.mem_total:
            parts.append(
                tr("Video memory: {used} of {total}").format(
                    used=format_bytes(gpu.mem_used), total=format_bytes(gpu.mem_total)
                )
            )
        if gpu.temp_c is not None:
            parts.append(f"{gpu.temp_c:.0f} °C")
        card.detail.setText(" · ".join(parts))

    def _show_processes(self, s: ResourceSnapshot) -> None:
        self._tree.clear()
        for p in s.top_processes:
            item = QTreeWidgetItem([p.name, str(p.pid), f"{p.cpu_pct:.1f}", format_bytes(p.rss)])
            self._tree.addTopLevelItem(item)
