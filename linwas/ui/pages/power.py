"""Güç ve pil sayfası (yalnızca dizüstü bilgisayarlarda menüde görünür)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import power
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("PowerPage", text)


def _status_text(status: str) -> str:
    return {
        "Charging": tr("Charging"),
        "Discharging": tr("On battery"),
        "Full": tr("Fully charged"),
        "Not charging": tr("Plugged in, not charging"),
    }.get(status, tr("Unknown"))


def _profile_text(profile: str) -> tuple[str, str]:
    return {
        "power-saver": (tr("Power saver"), tr("Longer battery life, slower computer")),
        "balanced": (tr("Balanced"), tr("Recommended for everyday use")),
        "performance": (tr("Performance"), tr("Fastest, uses more battery")),
    }.get(profile, (profile, ""))


def _lid_text(action: str) -> str:
    return {
        "suspend": tr("Sleep (default)"),
        "lock": tr("Lock the screen only"),
        "ignore": tr("Do nothing"),
        "poweroff": tr("Shut down"),
    }.get(action, action)


class _LoadWorker(QThread):
    done = Signal(object, object, str)  # (piller, (profiller, etkin), kapak)

    def run(self) -> None:
        self.done.emit(power.list_batteries(), power.power_profiles(), power.current_lid_action())


class _ProfileWorker(QThread):
    done = Signal(bool)

    def __init__(self, profile: str) -> None:
        super().__init__()
        self._profile = profile

    def run(self) -> None:
        self.done.emit(power.set_power_profile(self._profile))


class PowerPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loaded = False
        self._workers: list[QThread] = []
        self._battery_name = ""

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        title = QLabel(tr("Power & Battery"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Pil
        bat_card = Card(content)
        h = QLabel(tr("Battery"), bat_card)
        h.setObjectName("H2")
        bat_card.layout.addWidget(h)
        self._level = QProgressBar(bat_card)
        self._level.setRange(0, 100)
        bat_card.layout.addWidget(self._level)
        self._bat_lbl = QLabel(tr("Reading battery information…"), bat_card)
        self._bat_lbl.setWordWrap(True)
        bat_card.layout.addWidget(self._bat_lbl)
        outer.addWidget(bat_card)

        # Enerji modu
        self._mode_card = Card(content)
        h = QLabel(tr("Power mode"), self._mode_card)
        h.setObjectName("H2")
        self._mode_card.layout.addWidget(h)
        self._mode_box = QVBoxLayout()
        self._mode_card.layout.addLayout(self._mode_box)
        self._mode_group = QButtonGroup(self)
        self._mode_group.idClicked.connect(self._on_mode)
        self._profiles: list[str] = []
        outer.addWidget(self._mode_card)

        # Kapak
        lid_card = Card(content)
        h = QLabel(tr("When I close the lid"), lid_card)
        h.setObjectName("H2")
        lid_card.layout.addWidget(h)
        row = QHBoxLayout()
        self._lid = QComboBox(lid_card)
        for action in power.LID_ACTIONS:
            self._lid.addItem(_lid_text(action), action)
        row.addWidget(self._lid, 1)
        self._lid_btn = QPushButton(tr("Apply"), lid_card)
        self._lid_btn.clicked.connect(self._apply_lid)
        row.addWidget(self._lid_btn)
        lid_card.layout.addLayout(row)
        note = QLabel(tr("The change takes effect after the next restart."), lid_card)
        note.setObjectName("Secondary")
        lid_card.layout.addWidget(note)
        outer.addWidget(lid_card)

        # Pil koruma
        self._limit_card = Card(content)
        h = QLabel(tr("Battery protection"), self._limit_card)
        h.setObjectName("H2")
        self._limit_card.layout.addWidget(h)
        desc = QLabel(
            tr(
                "Stopping charging at 80% helps the battery last longer if the laptop is "
                "usually plugged in."
            ),
            self._limit_card,
        )
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        self._limit_card.layout.addWidget(desc)
        row = QHBoxLayout()
        self._limit = QComboBox(self._limit_card)
        for pct in power.CHARGE_LIMITS:
            text = tr("No limit (100%)") if pct == 100 else tr("Stop at {n}%").format(n=pct)
            self._limit.addItem(text, pct)
        row.addWidget(self._limit, 1)
        limit_btn = QPushButton(tr("Apply"), self._limit_card)
        limit_btn.clicked.connect(self._apply_limit)
        row.addWidget(limit_btn)
        self._limit_card.layout.addLayout(row)
        note = QLabel(tr("The limit is kept after restarting."), self._limit_card)
        note.setObjectName("Secondary")
        self._limit_card.layout.addWidget(note)
        self._limit_card.hide()  # yalnızca destekleyen cihazlarda
        outer.addWidget(self._limit_card)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        # Pil durumu değiştiği için her gösterilişte yenilenir
        self._reload()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            self._reload()

    def _keep(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.start()

    def _reload(self) -> None:
        self._loaded = True
        worker = _LoadWorker()
        worker.done.connect(self._on_loaded)
        self._keep(worker)

    def _on_loaded(self, batteries: list, profiles: tuple, lid: str) -> None:
        if batteries:
            bat: power.Battery = batteries[0]
            self._battery_name = bat.name
            self._level.setValue(bat.capacity or 0)
            lines = [_status_text(bat.status)]
            if bat.health is not None:
                if bat.health >= 80:
                    verdict = tr("good")
                elif bat.health >= 60:
                    verdict = tr("worn")
                else:
                    verdict = tr("needs replacing soon")
                lines.append(
                    tr("Battery health: {n}% of its original capacity ({verdict})").format(
                        n=bat.health, verdict=verdict
                    )
                )
            if bat.cycle_count:
                lines.append(tr("Charge cycles: {n}").format(n=bat.cycle_count))
            self._bat_lbl.setText("\n".join(lines))
            if bat.charge_limit is not None:
                self._limit_card.show()
                idx = self._limit.findData(bat.charge_limit)
                if idx >= 0:
                    self._limit.setCurrentIndex(idx)
        else:
            self._level.hide()
            self._bat_lbl.setText(tr("No battery found."))

        self._fill_profiles(*profiles)
        idx = self._lid.findData(lid)
        if idx >= 0:
            self._lid.setCurrentIndex(idx)

    def _fill_profiles(self, profiles: list[str], active: str) -> None:
        if profiles == self._profiles:
            for i, p in enumerate(profiles):
                self._mode_group.button(i).setChecked(p == active)
            return
        while self._mode_box.count():
            item = self._mode_box.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._profiles = profiles
        if not profiles:
            lbl = QLabel(tr("Power modes are not available on this computer."), self)
            lbl.setObjectName("Secondary")
            self._mode_box.addWidget(lbl)
            return
        # Sıra: tasarruf → dengeli → performans
        order = {"power-saver": 0, "balanced": 1, "performance": 2}
        for i, p in sorted(enumerate(profiles), key=lambda x: order.get(x[1], 9)):
            name, desc = _profile_text(p)
            rb = QRadioButton(f"{name} — {desc}" if desc else name, self)
            rb.setChecked(p == active)
            self._mode_group.addButton(rb, i)
            self._mode_box.addWidget(rb)

    def _on_mode(self, index: int) -> None:
        if 0 <= index < len(self._profiles):
            worker = _ProfileWorker(self._profiles[index])
            worker.done.connect(lambda ok: None if ok else self._reload())
            self._keep(worker)

    def _apply_lid(self) -> None:
        action = self._lid.currentData()
        self.task_run_now.emit(
            Task(
                label=tr("Lid close: {action}").format(action=_lid_text(action)),
                steps=[TaskStep(op_id="power.set_lid_action", params={"action": action})],
            )
        )

    def _apply_limit(self) -> None:
        if not self._battery_name:
            return
        pct = self._limit.currentData()
        self.task_run_now.emit(
            Task(
                label=tr("Battery charge limit: {n}%").format(n=pct),
                steps=[
                    TaskStep(
                        op_id="battery.set_charge_limit",
                        params={"battery": self._battery_name, "percent": str(pct)},
                    )
                ],
            )
        )
