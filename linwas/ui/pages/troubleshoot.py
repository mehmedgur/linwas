"""Sorun Giderme: tek tıkla tarama ve belirti kartları.

Çözümler ya izin listesindeki görevlerdir (kuyruk + onay) ya da ilgili Linwas sayfasına
gidiştir. Ses servisi kullanıcı düzeyinde olduğu için doğrudan yeniden başlatılır.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
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
from linwas.backend.desktop import detect_desktop
from linwas.backend.settings_launcher import command_for, open_settings
from linwas.core.plugins import ScanCheck
from linwas.core.plugins.loader import active as active_plugins
from linwas.core.tasks import Task, TaskStep
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.plugin_actions import action_callable
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
        "dns": (
            tr("Web addresses are found (DNS)"),
            tr("Connected, but web addresses are not found (DNS)"),
        ),
        "clock": (tr("The clock is set automatically"), tr("The clock is not synchronized")),
        "readonly": (
            tr("The system disk can be written"),
            tr("The system disk is read-only; nothing can be saved"),
        ),
        "home_space": (
            tr("Enough free space for your files"),
            tr("The disk with your files is almost full"),
        ),
        "boot_space": (
            tr("Enough space for system updates (/boot)"),
            tr("The boot partition (/boot) is full; kernel updates will fail"),
        ),
        "memory": (tr("Enough free memory"), tr("Memory is almost full")),
        "temperature": (tr("Temperature is normal"), tr("The computer is very hot")),
        "package_lists": (
            tr("The list of programs is up to date"),
            tr("The list of programs has not been refreshed for a long time"),
        ),
        "driver_modules": (
            tr("Extra drivers are built for this kernel"),
            tr("Some drivers are not built for the running kernel"),
        ),
        "graphics": (
            tr("The graphics card driver works"),
            tr("No graphics driver: the screen is drawn by the processor"),
        ),
        "boot_time": (tr("The computer starts quickly"), tr("The computer starts slowly")),
        "battery": (tr("The battery is in good condition"), tr("The battery is worn")),
    }


def _clock_text(offset: float) -> str:
    """ "Saat 2 sa 52 dk ileri" gibi; offset saniye, ileri +."""
    minutes = round(abs(offset) / 60)
    hours, mins = divmod(minutes, 60)
    amount = (
        tr("{h} h {m} min").format(h=hours, m=mins)
        if hours and mins
        else tr("{h} h").format(h=hours)
        if hours
        else tr("{m} min").format(m=max(mins, 1))
    )
    return (
        tr("The clock is {amount} fast") if offset > 0 else tr("The clock is {amount} slow")
    ).format(amount=amount)


class TroubleshootPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[_Worker] = []
        self._plugin_cards_added = False

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
            tr(
                "Checks internet and DNS, the clock, disks, memory, temperature, installations, "
                "drivers, services, sound, printing, updates, start-up time and the battery."
            ),
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
        self._grid = grid
        self._content = content
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

    def _settings(self, item_id: str) -> Callable | None:
        desktop = detect_desktop(os.environ).value
        if command_for(item_id, desktop) is None:
            return None
        return lambda: open_settings(item_id, desktop)

    def _corner_click(self) -> None:
        from linwas.backend import touchpad

        ok = touchpad.set_corner_right_click(True)
        self._add_result(
            ok,
            tr("Right-click now works with the bottom-right corner of the touchpad")
            if ok
            else tr("The touchpad setting could not be changed"),
        )

    def _fixes(self) -> dict[str, list[tuple[str, Callable]]]:
        restart_net = self._task(
            tr("Restart network service"), "service.restart", {"name": "NetworkManager"}
        )
        repair = self._task(tr("Repair interrupted installations"), "package.fix_broken")
        restart_cups = self._task(
            tr("Restart printing service"), "service.restart", {"name": "cups"}
        )
        remove_old = self._task(tr("Remove old kernels"), "package.autoremove")
        refresh_lists = self._task(tr("Refresh the list of programs"), "package.update_index")
        rebuild = self._task(tr("Rebuild drivers"), "driver.rebuild_modules")
        fix_clock = self._task(tr("Correct the clock"), "clock.fix")
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
            "dns": [(tr("Restart network service"), restart_net)],
            "clock": [(tr("Correct the clock"), fix_clock)]
            + self._link(tr("Date & time settings"), "datetime"),
            "readonly": [],
            "home_space": [(tr("Free up space"), self._go("cleanup"))],
            "boot_space": [(tr("Remove old kernels"), remove_old)],
            "memory": [(tr("Task Manager"), self._go("taskmgr"))],
            "temperature": [
                (tr("Task Manager"), self._go("taskmgr")),
                (tr("Power plans"), self._go("power")),
            ],
            "package_lists": [(tr("Refresh the list"), refresh_lists)],
            "driver_modules": [(tr("Rebuild drivers"), rebuild)],
            "graphics": [(tr("Drivers"), self._go("drivers"))],
            "boot_time": [(tr("Startup programs"), self._go("taskmgr"))],
            "battery": [(tr("Battery details"), self._go("power"))],
        }

    def _right_click_actions(self) -> list[tuple[str, Callable]]:
        from linwas.backend import touchpad

        actions: list[tuple[str, Callable]] = []
        if touchpad.supported():
            actions.append((tr("Corner right-click, like Windows"), self._corner_click))
        return actions + self._link(tr("Mouse & touchpad settings"), "mouse")

    def _link(self, text: str, item_id: str) -> list[tuple[str, Callable]]:
        fn = self._settings(item_id)
        return [(text, fn)] if fn else []

    def _symptoms(self) -> list[tuple[str, str, list[tuple[str, Callable]]]]:
        fixes = self._fixes()
        remove_old = self._task(tr("Remove old kernels"), "package.autoremove")
        refresh_lists = self._task(tr("Refresh the list of programs"), "package.update_index")
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
            (
                tr("Bluetooth device won't connect"),
                tr("Headphones, mouse or phone isn't found or keeps disconnecting."),
                [
                    (
                        tr("Restart Bluetooth"),
                        self._task(
                            tr("Restart Bluetooth service"),
                            "service.restart",
                            {"name": "bluetooth"},
                        ),
                    ),
                    (tr("Bluetooth"), self._go("network")),
                ],
            ),
            (
                tr("Microphone or camera doesn't work"),
                tr("Others can't hear or see you in video calls."),
                [
                    (tr("Restart sound"), self._restart_sound),
                    *self._link(tr("Sound settings"), "sound"),
                    (tr("Devices"), self._go("hardware")),
                ],
            ),
            (
                tr("Battery drains fast"),
                tr("The battery empties quickly or the laptop gets warm."),
                [(tr("Power plans"), self._go("power")), (tr("Task Manager"), self._go("taskmgr"))],
            ),
            (
                tr("Wrong date or time"),
                tr("The clock is off, or secure websites show certificate errors."),
                [
                    (
                        tr("Correct the clock"),
                        self._task(tr("Correct the clock"), "clock.fix"),
                    ),
                    *self._link(tr("Date & time settings"), "datetime"),
                ],
            ),
            (
                tr("Updates fail"),
                tr("Updating stops with an error or the disk is full."),
                [
                    (tr("Refresh the list"), refresh_lists),
                    (tr("Repair"), fixes["packages"][0][1]),
                    (tr("Remove old kernels"), remove_old),
                ],
            ),
            (
                tr("Right-click doesn't work"),
                tr("Pressing the bottom-right corner of the touchpad clicks like the left button."),
                self._right_click_actions(),
            ),
            (
                tr("Computer starts slowly"),
                tr("It takes long until the desktop is ready."),
                [(tr("Startup programs"), self._go("taskmgr"))],
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

    # --- Eklentiler ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        # Eklentiler sayfalardan sonra yüklenir; belirti kartları ilk gösterimde eklenir
        if not self._plugin_cards_added:
            self._plugin_cards_added = True
            self._add_plugin_cards()

    def _add_plugin_cards(self) -> None:
        loader = active_plugins()
        if loader is None:
            return
        index = self._grid.count()
        for card in loader.gate("troubleshooting_cards"):
            actions = [
                (a.label, fn) for a in card.actions if (fn := action_callable(self, a)) is not None
            ]
            desc = card.description or "\n".join(f"• {s}" for s in card.solutions)
            widget = self._symptom_card(self._content, card.symptom, desc, actions)
            self._grid.addWidget(widget, index // 2, index % 2)
            index += 1

    @staticmethod
    def _run_plugin_checks(checks: list[ScanCheck]) -> list[tuple[ScanCheck, bool, str]]:
        results = []
        for check in checks:
            if check.run is None:
                continue
            try:
                ok, detail = check.run()
            except Exception as exc:  # bozuk eklenti taramayı durdurmasın
                ok, detail = True, f"check failed: {exc}"
            results.append((check, bool(ok), str(detail)))
        return results

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
        loader = active_plugins()
        checks = loader.gate("scan_checks") if loader else []
        self._run(
            lambda: (troubleshoot.run_all(), self._run_plugin_checks(checks)), self._on_scanned
        )

    def _add_result(self, ok: bool, text: str, detail: str = "") -> QHBoxLayout:
        row_widget = QWidget(self)
        row_widget.setObjectName("CardRow")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 2, 0, 2)
        mark = QLabel(row_widget)
        mark.setFixedSize(18, 18)
        icons.bind(mark, "check" if ok else "info", "success" if ok else "warning", 18)
        row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        lbl = QLabel(text, row_widget)
        if detail:
            lbl.setToolTip(detail)
        row.addWidget(lbl, 1)
        self._results.addWidget(row_widget)
        return row

    def _on_scanned(self, data: object) -> None:
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText(tr("Scan again"))
        texts = _check_texts()
        fixes = self._fixes()
        results, plugin_results = data if isinstance(data, tuple) else ([], [])
        problems = [r for r in results if not r.ok]
        # Önce sorunlar, sonra sorunsuz kontroller
        for r in problems + [r for r in results if r.ok]:
            ok_text, bad_text = texts.get(r.id, (r.id, r.id))
            if r.id == "clock" and not r.ok and r.detail.startswith("offset:"):
                bad_text = _clock_text(float(r.detail.split(":", 1)[1]))
            row = self._add_result(r.ok, ok_text if r.ok else bad_text, r.detail)
            if not r.ok:
                for text, fn in fixes.get(r.id, []):
                    btn = QPushButton(text, self)
                    btn.clicked.connect(fn)
                    row.addWidget(btn)
                # Her sorunda: ayrıntıyla birlikte yardımcıya sor
                ask = QPushButton(tr("Ask the assistant"), self)
                ask.clicked.connect(
                    lambda _c=False, t=bad_text, d=r.detail: self.ai_help_requested.emit(t, d)
                )
                row.addWidget(ask)
        # Eklentilerin denetimleri (sorunlular önce)
        plugin_problems = [r for r in plugin_results if not r[1]]
        for check, ok, detail in plugin_problems + [r for r in plugin_results if r[1]]:
            text = check.label if ok else (check.problem_label or check.label)
            row = self._add_result(ok, text, detail)
            if not ok:
                for action in check.fixes:
                    fn = action_callable(self, action)
                    if fn is not None:
                        btn = QPushButton(action.label, self)
                        btn.clicked.connect(fn)
                        row.addWidget(btn)
        total = len(problems) + len(plugin_problems)
        summary = QLabel(
            tr("No problems found.") if not total else tr("{n} problem(s) found.").format(n=total),
            self,
        )
        summary.setObjectName("H2")
        self._results.insertWidget(0, summary)
