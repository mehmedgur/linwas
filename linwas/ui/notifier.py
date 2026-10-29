# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Arka plan bildirimleri: güncellemeler, yeniden başlatma, otomatik güncelleme sonucu, aygıt
sorunları. Saatte bir denetlenir; aynı durum için bir kez bildirilir (notify_state.json).
Ayarlar › Bildirimler ve başlangıç'taki seçimlere ve sessiz saatlere uyulur.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QThread, QTimer, Signal

from linwas.backend import notify
from linwas.core import app_settings

CHECK_INTERVAL_MS = 60 * 60 * 1000
FIRST_CHECK_MS = 90 * 1000


def tr(text: str) -> str:
    return QCoreApplication.translate("Notifier", text)


def _state_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "linwas" / "notify_state.json"


def _load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state: dict) -> None:
    path = _state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


@dataclass
class _Facts:
    updates: int = 0
    reboot: bool = False
    auto_run: str = ""
    auto_result: str = ""
    auto_count: int = 0
    device_problems: int = 0
    nvidia_current: int = 0  # kurulu NVIDIA serisi (ör. 535)
    nvidia_newer: int = 0  # depodaki daha yeni seri; 0 = yok


class _CheckWorker(QThread):
    done = Signal(object)  # _Facts

    def run(self) -> None:
        from linwas.backend.devices import list_devices
        from linwas.backend.packages import list_upgradable
        from linwas.core import autoupdate

        facts = _Facts()
        try:
            facts.updates = len(list_upgradable())
            facts.reboot = autoupdate.reboot_required()
            state = autoupdate.load_state()
            facts.auto_run, facts.auto_result = state.last_run, state.result
            facts.auto_count = len(state.packages)
            devices = list_devices()
            facts.device_problems = sum(1 for d in devices if d.problem)
            self._check_nvidia(facts, devices)
        except Exception:
            pass
        self.done.emit(facts)

    @staticmethod
    def _check_nvidia(facts: _Facts, devices: list) -> None:
        """Yeni NVIDIA serisi: günde en çok bir kez (ubuntu-drivers yavaş)."""
        if not any(d.group == "display" and d.vendor == "10de" for d in devices):
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if _load_state().get("nvidia_checked") == today:
            facts.nvidia_current = -1  # bugün denetlendi; durum değişmez
            return
        from linwas.backend import driver_options

        facts.nvidia_current, facts.nvidia_newer = driver_options.newer_series(
            driver_options.nvidia_options()
        )


class Notifier(QObject):
    """Bildirimleri gönderir ve bildirimdeki "Aç" düğmesini dinler."""

    open_requested = Signal(str)  # sayfa kimliği

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: dict[int, str] = {}  # bildirim kimliği → açılacak sayfa
        self._procs: list[QProcess] = []
        self._monitor: QProcess | None = None
        self._worker: _CheckWorker | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self.check)
        self._buffer = b""

    def start(self) -> None:
        """Periyodik denetimi ve düğme dinleyicisini başlatır (bir kez)."""
        if self._timer.isActive() or not notify.available():
            return
        self._start_monitor()
        self._timer.start()
        QTimer.singleShot(FIRST_CHECK_MS, self.check)

    def stop(self) -> None:
        self._timer.stop()
        if self._monitor is not None:
            self._monitor.kill()
            self._monitor = None

    # --- Gönderme ---

    def send(self, summary: str, body: str, page: str = "") -> None:
        if not notify.available():
            return
        actions = [("default", tr("Open"))] if page else []
        proc = QProcess(self)
        argv = notify.notify_command(summary, body, actions)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        self._procs.append(proc)

        def finished(*_args) -> None:  # noqa: ANN002
            out = bytes(proc.readAllStandardOutput()).decode(errors="replace")
            notification = notify.parse_notify_id(out)
            if notification and page:
                self._pending[notification] = page
            self._procs.remove(proc)
            proc.deleteLater()

        proc.finished.connect(finished)
        proc.start()

    def _start_monitor(self) -> None:
        proc = QProcess(self)
        argv = notify.monitor_command()
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        proc.readyReadStandardOutput.connect(self._on_monitor_output)
        proc.start()
        self._monitor = proc

    def _on_monitor_output(self) -> None:
        if self._monitor is None:
            return
        self._buffer += bytes(self._monitor.readAllStandardOutput())
        *lines, self._buffer = self._buffer.split(b"\n")
        for raw in lines:
            parsed = notify.parse_action(raw.decode(errors="replace"))
            if parsed and parsed[0] in self._pending:
                self.open_requested.emit(self._pending.pop(parsed[0]))

    # --- Denetim ---

    def check(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = _CheckWorker(self)
        self._worker.done.connect(self._on_facts)
        self._worker.start()

    def _on_facts(self, facts: _Facts) -> None:
        settings = app_settings.load()
        if app_settings.in_quiet_hours(settings, datetime.now().strftime("%H:%M")):
            return  # sessiz saatlerde bildirim yok; sonraki denetimde yeniden bakılır
        state = _load_state()

        if settings.notify_updates and facts.updates and facts.updates != state.get("updates"):
            self.send(
                tr("Updates are ready"),
                tr("{n} update(s) can be installed.").format(n=facts.updates),
                "updates",
            )
        state["updates"] = facts.updates

        boot = _boot_id()
        if settings.notify_restart and facts.reboot and state.get("reboot_boot") != boot:
            self.send(
                tr("Restart required"),
                tr("Restart the computer to finish installing updates."),
                "updates",
            )
            state["reboot_boot"] = boot

        if facts.auto_run and facts.auto_run != state.get("auto_run"):
            if settings.notify_autoupdate and facts.auto_result == "updated":
                self.send(
                    tr("Automatic updates installed"),
                    tr("{n} package(s) were updated.").format(n=facts.auto_count),
                    "updates",
                )
            elif settings.notify_autoupdate and facts.auto_result == "failed":
                self.send(
                    tr("Automatic update failed"),
                    tr("Open the Update center to see what went wrong."),
                    "updates",
                )
            state["auto_run"] = facts.auto_run

        problems = facts.device_problems
        if settings.notify_devices and problems and problems != state.get("device_problems"):
            self.send(
                tr("A device has no driver"),
                tr("{n} device(s) have no driver. Linwas can look for one.").format(n=problems),
                "hardware",
            )
        state["device_problems"] = problems

        if facts.nvidia_current >= 0:
            state["nvidia_checked"] = datetime.now().strftime("%Y-%m-%d")
            newer = facts.nvidia_newer
            if (
                settings.notify_updates
                and facts.nvidia_current
                and newer
                and newer != state.get("nvidia_notified")
            ):
                self.send(
                    tr("A newer NVIDIA driver is available"),
                    tr(
                        "NVIDIA driver {new} is available; you use {current}. Open Drivers to "
                        "switch; a system backup is taken first."
                    ).format(new=newer, current=facts.nvidia_current),
                    "drivers",
                )
                state["nvidia_notified"] = newer
        _save_state(state)
