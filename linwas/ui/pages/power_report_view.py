# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Güç sayfasındaki "Güç tanılaması" kartı: özet, bulgular (tek tıkla düzelt) ve HTML rapor."""

from __future__ import annotations

import html
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import power_report
from linwas.backend.power_report import Finding, PowerReport
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages import power_texts as texts
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("PowerPage", text)


def _level_text(level: str) -> str:
    return {
        "error": tr("Error"),
        "warning": tr("Warning"),
        "suggestion": tr("Suggestion"),
        "info": tr("Information"),
    }.get(level, level)


def finding_text(f: Finding) -> str:
    p = f.params
    if f.code == "service_stopped":
        return tr("The Linwas power plan service is not running, so plans are not applied.")
    if f.code == "apply_errors":
        names = ", ".join(texts.setting_name(s) for s in p.get("settings", "").split(",") if s)
        return tr("Some settings could not be applied: {names}").format(names=names)
    if f.code == "conflict":
        return tr(
            "{name} is also managing power settings; the two can override each other."
        ).format(name=p.get("name", ""))
    if f.code == "battery_worn":
        return tr("The battery holds {n}% of its original capacity; consider replacing it.").format(
            n=p.get("n", "")
        )
    if f.code == "battery_aging":
        return tr("The battery holds {n}% of its original capacity.").format(n=p.get("n", ""))
    if f.code == "high_drain":
        return tr("The computer is using {w} W on battery, which is high.").format(w=p.get("w", ""))
    if f.code == "busy_process":
        return tr('"{name}" is keeping the processor busy ({cpu}% of one core).').format(
            name=p.get("name", ""), cpu=p.get("cpu", "")
        )
    if f.code == "battery_saver_off":
        return tr("Automatic switching to a power saving plan on low battery is off.")
    if f.code == "bat_usb_autosuspend":
        return tr("USB selective suspend is not turned on for battery in the current plan.")
    if f.code == "bat_wifi_powersave":
        return tr("Wi-Fi power saving is not turned on for battery in the current plan.")
    if f.code == "bat_pci_runtime_pm":
        return tr("PCI device power management is not turned on for battery in the current plan.")
    if f.code == "bat_brightness":
        return tr("The current plan sets the screen brightness to {n}% on battery.").format(
            n=p.get("n", "")
        )
    if f.code == "install_ppd":
        return tr("Install power-profiles-daemon to use the system power modes.")
    if f.code == "no_hibernate":
        reasons = [texts.hibernate_reason_text(r) for r in p.get("reasons", "").split(",") if r]
        return tr("Hibernate is not available.") + (" " + " ".join(reasons) if reasons else "")
    if f.code == "many_wake_devices":
        return tr("{n} devices can wake the computer from sleep.").format(n=p.get("n", ""))
    if f.code == "install_powertop":
        return tr("Install powertop for a detailed measurement of power use.")
    return f.code


def _fix_text(f: Finding) -> str:
    if f.fix and f.fix[0] == "ui":
        return tr("Show")
    if f.code.startswith("install_"):
        return tr("Install")
    if f.code == "conflict":
        return tr("Remove")
    return tr("Fix")


class _CollectWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        self.done.emit(power_report.collect())


class PowerReportCard(Card):
    task_run_now = Signal(Task)
    ui_action = Signal(str)  # "automation" | "advanced"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._report: PowerReport | None = None
        self._worker: _CollectWorker | None = None

        h = QLabel(tr("Power diagnostics"), self)
        h.setObjectName("H2")
        self.layout.addWidget(h)
        desc = QLabel(
            tr("Finds what uses power, checks the settings and suggests improvements."), self
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        self.layout.addWidget(desc)

        row = QHBoxLayout()
        self._run_btn = QPushButton(tr("Run diagnostics"), self)
        self._run_btn.clicked.connect(self.run)
        row.addWidget(self._run_btn)
        self._powertop_btn = QPushButton(tr("Detailed measurement (powertop, 20 s)"), self)
        self._powertop_btn.clicked.connect(self._run_powertop)
        row.addWidget(self._powertop_btn)
        self._html_btn = QPushButton(tr("Save as HTML…"), self)
        self._html_btn.clicked.connect(self._save_html)
        self._html_btn.setEnabled(False)
        row.addWidget(self._html_btn)
        row.addStretch(1)
        self.layout.addLayout(row)

        self._summary = QLabel("", self)
        self._summary.setWordWrap(True)
        self.layout.addWidget(self._summary)
        self._list = QVBoxLayout()
        self.layout.addLayout(self._list)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._powertop_btn.setVisible(bool(shutil.which("powertop")))

    def run(self) -> None:
        if self._worker is not None:
            return
        self._run_btn.setEnabled(False)
        self._summary.setText(tr("Measuring…"))
        self._worker = _CollectWorker()
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self) -> None:
        self._worker = None
        self._run_btn.setEnabled(True)

    def _on_done(self, report: PowerReport) -> None:
        self._report = report
        self._html_btn.setEnabled(True)
        counts = {
            lvl: sum(f.level == lvl for f in report.findings)
            for lvl in ("error", "warning", "suggestion")
        }
        lines = [
            tr("{e} errors, {w} warnings, {s} suggestions").format(
                e=counts["error"], w=counts["warning"], s=counts["suggestion"]
            )
        ]
        if report.watts is not None:
            lines.append(tr("Current power use on battery: {w} W").format(w=report.watts))
        self._summary.setText("\n".join(lines))
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        for f in report.findings:
            row = QHBoxLayout()
            lbl = QLabel(f"{_level_text(f.level)}: {finding_text(f)}", self)
            lbl.setWordWrap(True)
            if f.level in ("error", "warning"):
                lbl.setObjectName("Warning")
            row.addWidget(lbl, 1)
            if f.fix:
                btn = QPushButton(_fix_text(f), self)
                btn.clicked.connect(lambda _c=False, fi=f: self._apply_fix(fi))
                row.addWidget(btn)
            self._list.addLayout(row)

    def _clear_layout(self, layout: object) -> None:
        while layout.count():  # type: ignore[attr-defined]
            item = layout.takeAt(0)  # type: ignore[attr-defined]
            if item.widget():
                item.widget().deleteLater()

    def _apply_fix(self, f: Finding) -> None:
        if f.fix[0] == "ui":
            self.ui_action.emit(f.fix[1])
            return
        steps = [TaskStep(op_id=op, params=params) for op, params in f.fix[1]]
        self.task_run_now.emit(Task(label=finding_text(f), steps=steps))

    def _run_powertop(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Detailed power measurement (powertop)"),
                steps=[TaskStep(op_id="power.powertop_report", params={})],
            )
        )

    def _save_html(self) -> None:
        if self._report is None:
            return
        stamp = datetime.now().strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Save power report"),
            str(Path.home() / f"linwas-power-report-{stamp}.html"),
            tr("Web page (*.html)"),
        )
        if not path:
            return
        try:
            Path(path).write_text(build_html(self._report), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, tr("Power diagnostics"), str(exc))


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><tr>{head}</tr>{body}</table>"


def build_html(r: PowerReport) -> str:
    when = datetime.fromtimestamp(r.time).strftime("%Y-%m-%d %H:%M")
    plan = r.plan_name or {
        "power-saver": tr("Power saver"),
        "balanced": tr("Balanced"),
        "performance": tr("Performance"),
    }.get(r.plan_id, r.plan_id)
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(tr('Power report'))}</title>",
        "<style>body{font-family:sans-serif;max-width:900px;margin:24px auto;padding:0 16px;"
        "color:#1b1b1b}h1{font-size:24px}h2{font-size:18px;margin-top:28px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px;"
        "text-align:left;vertical-align:top}th{background:#f2f2f2}"
        ".error{color:#b00020}.warning{color:#8a5a00}</style></head><body>",
        f"<h1>{html.escape(tr('Power report'))}</h1>",
        f"<p>{html.escape(when)} · Linwas</p>",
        f"<h2>{html.escape(tr('Summary'))}</h2>",
        _table(
            [tr("Item"), tr("Value")],
            [
                [tr("Power plan"), plan],
                [tr("Power source"), tr("plugged in") if r.source == "ac" else tr("on battery")],
                [
                    tr("Power plan service"),
                    tr("Running") if r.service_running else tr("Not running"),
                ],
                *(
                    [[tr("Current power use on battery"), f"{r.watts} W"]]
                    if r.watts is not None
                    else []
                ),
            ],
        ),
        f"<h2>{html.escape(tr('Findings'))}</h2>",
    ]
    if r.findings:
        parts.append("<ul>")
        for f in r.findings:
            parts.append(
                f"<li class='{f.level}'><b>{html.escape(_level_text(f.level))}:</b> "
                f"{html.escape(finding_text(f))}</li>"
            )
        parts.append("</ul>")
    else:
        parts.append(f"<p>{html.escape(tr('No problems found.'))}</p>")
    if r.batteries:
        parts.append(f"<h2>{html.escape(tr('Battery'))}</h2>")
        parts.append(
            _table(
                [tr("Battery"), tr("Charge"), tr("Health"), tr("Charge cycles")],
                [
                    [
                        b.name,
                        tr("{n}%").format(n=b.capacity) if b.capacity is not None else "—",
                        tr("{n}%").format(n=b.health) if b.health is not None else "—",
                        str(b.cycle_count or "—"),
                    ]
                    for b in r.batteries
                ],
            )
        )
    parts.append(f"<h2>{html.escape(tr('Programs using the processor'))}</h2>")
    parts.append(
        _table(
            [tr("Program"), tr("Process ID"), tr("Processor (% of one core)")],
            [[p.name, str(p.pid), str(p.cpu)] for p in r.processes],
        )
    )
    if r.wake_devices:
        parts.append(f"<h2>{html.escape(tr('Devices that can wake the computer'))}</h2>")
        parts.append(_table([tr("Device")], [[d] for d in r.wake_devices]))
    for section, rows in r.powertop.items():
        parts.append(f"<h2>powertop: {html.escape(section)}</h2>")
        width = max(len(row) for row in rows)
        parts.append(_table([""] * width, [row + [""] * (width - len(row)) for row in rows]))
    parts.append("</body></html>")
    return "\n".join(parts)
