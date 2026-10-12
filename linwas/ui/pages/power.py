"""Güç ve pil sayfası (masaüstü bilgisayarda "Güç"; pil bölümleri gizli).

Üstte güç planı seçimi ve sık ayarlar, altta Windows'taki gibi "Gelişmiş güç seçenekleri"
ağaç listesi (her satırda Prizde / Pilde). Plan şifresiz değiştirilir (kurulu pakette); plan
ayarları root helper'ın `power.save_config` işlemiyle kaydedilir (kararlar.md › Güç ve pil).
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, QTime, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import power, power_support
from linwas.core import power_agent, power_apply, powerplan
from linwas.core.powerplan import AUTO, SECTIONS, SETTINGS, SPECS, PowerConfig
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages import power_texts as texts
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.power_report_view import PowerReportCard
from linwas.ui.widgets.card import Card

# Hazırda bekletme yoksa listeden çıkarılan değerler (seçiliyse yine gösterilir)
_HIBERNATE_VALUES = {"hibernate", "hybrid-sleep", "Hibernate", "HybridSleep"}
# "Sık kullanılan ayarlar" kartındaki ayarlar
_QUICK = ("screen_off", "sleep_after")


def tr(text: str) -> str:
    return QCoreApplication.translate("PowerPage", text)


def _status_text(status: str) -> str:
    return {
        "Charging": tr("Charging"),
        "Discharging": tr("On battery"),
        "Full": tr("Fully charged"),
        "Not charging": tr("Plugged in, not charging"),
    }.get(status, tr("Unknown"))


class _LoadWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        batteries = power.list_batteries()
        self.done.emit(
            {
                "batteries": batteries,
                "config": powerplan.load_config(),
                "support": power_support.detect(laptop=bool(batteries)),
                "status": power_apply.read_status(),
                "ppd": power.power_profiles()[1],
                "state": powerplan.read_power_state(),
            }
        )


class _SwitchWorker(QThread):
    done = Signal(bool)

    def __init__(self, plan_id: str) -> None:
        super().__init__()
        self._plan_id = plan_id

    def run(self) -> None:
        ok = power.switch_plan(self._plan_id)
        if ok:
            power_agent.apply_now()
        self.done.emit(ok)


class _AgentWorker(QThread):
    """Kaydettikten sonra masaüstü ayarlarını hemen uygular (ajanın 20 sn'sini beklemeden)."""

    def run(self) -> None:
        power_agent.apply_now()


class PowerPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loaded = False
        self._workers: list[QThread] = []
        self._battery_name = ""
        self._laptop = power.is_laptop()
        self._saved: PowerConfig = powerplan.default_config()
        self._draft: PowerConfig = powerplan.default_config()
        self._support: power_support.PowerSupport | None = None
        self._edit_plan = powerplan.DEFAULT_PLAN
        self._filling = False
        self._pending_save = False

        scroll = QScrollArea(self)
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        title = QLabel(tr("Power & Battery") if self._laptop else tr("Power"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        self._conflict_card = self._build_conflict_card(content)
        outer.addWidget(self._conflict_card)
        self._battery_card = self._build_battery_card(content)
        outer.addWidget(self._battery_card)
        self._battery_card.setVisible(self._laptop)
        outer.addWidget(self._build_plan_card(content))
        outer.addWidget(self._build_quick_card(content))
        self._advanced_card = self._build_advanced_card(content)
        outer.addWidget(self._advanced_card)
        self._automation_card = self._build_automation_card(content)
        outer.addWidget(self._automation_card)
        self._hibernate_card = self._build_hibernate_card(content)
        outer.addWidget(self._hibernate_card)
        self._report_card = PowerReportCard(content)
        self._report_card.task_run_now.connect(self.task_run_now)
        self._report_card.ui_action.connect(self._on_report_action)
        outer.addWidget(self._report_card)

        # Kaydet çubuğu
        self._save_bar = Card(content)
        row = QHBoxLayout()
        self._dirty_lbl = QLabel(tr("You have unsaved changes."), self._save_bar)
        row.addWidget(self._dirty_lbl, 1)
        discard = QPushButton(tr("Discard"), self._save_bar)
        discard.clicked.connect(self._discard)
        row.addWidget(discard)
        save = QPushButton(tr("Save changes"), self._save_bar)
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(save)
        self._save_bar.layout.addLayout(row)
        self._save_bar.hide()
        outer.addWidget(self._save_bar)

        outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    # --- Kartlar ---

    def _h2(self, text: str, parent: QWidget) -> QLabel:
        h = QLabel(text, parent)
        h.setObjectName("H2")
        return h

    def _secondary(self, text: str, parent: QWidget) -> QLabel:
        lbl = QLabel(text, parent)
        lbl.setObjectName("Secondary")
        lbl.setWordWrap(True)
        return lbl

    def _build_conflict_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Another power tool is installed"), card))
        self._conflict_lbl = QLabel("", card)
        self._conflict_lbl.setObjectName("Warning")
        self._conflict_lbl.setWordWrap(True)
        card.layout.addWidget(self._conflict_lbl)
        self._conflict_btns = QHBoxLayout()
        card.layout.addLayout(self._conflict_btns)
        card.hide()
        return card

    def _build_battery_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Battery"), card))
        self._level = QProgressBar(card)
        self._level.setRange(0, 100)
        card.layout.addWidget(self._level)
        self._bat_lbl = QLabel(tr("Reading battery information…"), card)
        self._bat_lbl.setWordWrap(True)
        card.layout.addWidget(self._bat_lbl)

        # Pil koruma (yalnızca destekleyen cihazlarda)
        self._limit_box = QWidget(card)
        box = QVBoxLayout(self._limit_box)
        box.setContentsMargins(0, 8, 0, 0)
        box.addWidget(self._h2(tr("Battery protection"), self._limit_box))
        box.addWidget(
            self._secondary(
                tr(
                    "Stopping charging at 80% helps the battery last longer if the laptop is "
                    "usually plugged in."
                ),
                self._limit_box,
            )
        )
        row = QHBoxLayout()
        self._limit = QComboBox(self._limit_box)
        for pct in power.CHARGE_LIMITS:
            text = tr("No limit (100%)") if pct == 100 else tr("Stop at {n}%").format(n=pct)
            self._limit.addItem(text, pct)
        row.addWidget(self._limit, 1)
        limit_btn = QPushButton(tr("Apply"), self._limit_box)
        limit_btn.clicked.connect(self._apply_limit)
        row.addWidget(limit_btn)
        box.addLayout(row)
        box.addWidget(self._secondary(tr("The limit is kept after restarting."), self._limit_box))
        self._limit_box.hide()
        card.layout.addWidget(self._limit_box)
        return card

    def _build_plan_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Power plan"), card))
        self._now_lbl = self._secondary("", card)
        card.layout.addWidget(self._now_lbl)
        self._ppd_warn = QLabel("", card)
        self._ppd_warn.setObjectName("Warning")
        self._ppd_warn.setWordWrap(True)
        self._ppd_warn.hide()
        card.layout.addWidget(self._ppd_warn)
        self._plan_box = QVBoxLayout()
        card.layout.addLayout(self._plan_box)
        self._plan_group = QButtonGroup(self)
        self._plan_group.idClicked.connect(self._on_plan_clicked)
        self._plan_ids: list[str] = []

        row = QHBoxLayout()
        for text, slot in (
            (tr("New plan…"), self._new_plan),
            (tr("Import…"), self._import_plan),
            (tr("Reapply plan"), self._reapply),
        ):
            btn = QPushButton(text, card)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        return card

    def _build_quick_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        self._quick_title = self._h2("", card)
        card.layout.addWidget(self._quick_title)
        grid = QVBoxLayout()
        self._quick_combos: dict[tuple[str, str], QComboBox] = {}
        head = QHBoxLayout()
        head.addWidget(QLabel("", card), 2)
        self._quick_heads: list[QLabel] = []
        for text in (tr("Plugged in"), tr("On battery")):
            lbl = QLabel(text, card)
            lbl.setObjectName("Secondary")
            head.addWidget(lbl, 1)
            self._quick_heads.append(lbl)
        grid.addLayout(head)
        for sid in _QUICK:
            row = QHBoxLayout()
            row.addWidget(QLabel(texts.setting_name(sid), card), 2)
            for src in powerplan.SOURCES:
                combo = QComboBox(card)
                combo.currentIndexChanged.connect(
                    lambda _i, s=sid, so=src, c=combo: self._on_combo(s, so, c)
                )
                row.addWidget(combo, 1)
                self._quick_combos[(sid, src)] = combo
            grid.addLayout(row)
        card.layout.addLayout(grid)
        return card

    def _build_advanced_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Advanced power settings"), card))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Plan:"), card))
        self._edit_combo = QComboBox(card)
        self._edit_combo.currentIndexChanged.connect(self._on_edit_plan_changed)
        row.addWidget(self._edit_combo, 1)
        self._rename_btn = QPushButton(tr("Rename…"), card)
        self._rename_btn.clicked.connect(self._rename_plan)
        row.addWidget(self._rename_btn)
        self._delete_btn = QPushButton(tr("Delete"), card)
        self._delete_btn.clicked.connect(self._delete_plan)
        row.addWidget(self._delete_btn)
        export_btn = QPushButton(tr("Export…"), card)
        export_btn.clicked.connect(self._export_plan)
        row.addWidget(export_btn)
        card.layout.addLayout(row)

        self._tree = QTreeWidget(card)
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels([tr("Setting"), tr("Plugged in"), tr("On battery")])
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self._tree.setMinimumHeight(420)
        self._tree.setRootIsDecorated(True)
        card.layout.addWidget(self._tree)
        self._tree_combos: dict[tuple[str, str], QComboBox] = {}
        self._tree_items: dict[str, QTreeWidgetItem] = {}

        row = QHBoxLayout()
        reset = QPushButton(tr("Restore plan defaults"), card)
        reset.clicked.connect(self._reset_plan)
        row.addWidget(reset)
        reset_all = QPushButton(tr("Restore all defaults"), card)
        reset_all.clicked.connect(self._reset_all)
        row.addWidget(reset_all)
        row.addStretch(1)
        card.layout.addLayout(row)
        card.layout.addWidget(
            self._secondary(
                tr(
                    '"System default" means Linwas does not change that setting. Settings '
                    'under "all plans" are the same for every plan.'
                ),
                card,
            )
        )
        return card

    def _build_automation_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Automatic plan switching"), card))

        self._saver_box = QWidget(card)
        row = QHBoxLayout(self._saver_box)
        row.setContentsMargins(0, 0, 0, 0)
        self._saver_chk = QCheckBox(tr("When the battery falls to"), self._saver_box)
        self._saver_chk.toggled.connect(self._on_automation)
        row.addWidget(self._saver_chk)
        self._saver_pct = QSpinBox(self._saver_box)
        self._saver_pct.setRange(5, 50)
        self._saver_pct.setSuffix("%")
        self._saver_pct.valueChanged.connect(self._on_automation)
        row.addWidget(self._saver_pct)
        row.addWidget(QLabel(tr("switch to"), self._saver_box))
        self._saver_plan = QComboBox(self._saver_box)
        self._saver_plan.currentIndexChanged.connect(self._on_automation)
        row.addWidget(self._saver_plan, 1)
        self._saver_box.setVisible(self._laptop)
        card.layout.addWidget(self._saver_box)

        row = QHBoxLayout()
        self._sched_chk = QCheckBox(tr("Every day from"), card)
        self._sched_chk.toggled.connect(self._on_automation)
        row.addWidget(self._sched_chk)
        self._sched_start = QTimeEdit(card)
        self._sched_start.setDisplayFormat("HH:mm")
        self._sched_start.timeChanged.connect(self._on_automation)
        row.addWidget(self._sched_start)
        row.addWidget(QLabel(tr("to"), card))
        self._sched_end = QTimeEdit(card)
        self._sched_end.setDisplayFormat("HH:mm")
        self._sched_end.timeChanged.connect(self._on_automation)
        row.addWidget(self._sched_end)
        row.addWidget(QLabel(tr("use"), card))
        self._sched_plan = QComboBox(card)
        self._sched_plan.currentIndexChanged.connect(self._on_automation)
        row.addWidget(self._sched_plan, 1)
        card.layout.addLayout(row)
        card.layout.addWidget(
            self._secondary(
                tr("Low battery switching comes first, then the schedule, then the selected plan."),
                card,
            )
        )
        return card

    def _build_hibernate_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Hibernate"), card))
        self._hibernate_lbl = self._secondary("", card)
        card.layout.addWidget(self._hibernate_lbl)
        return card

    # --- Yükleme ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if not self._dirty():
            self._reload()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            if self._pending_save:
                self._pending_save = False
                self._keep(_AgentWorker())
            self._reload(force=True)

    def _keep(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.start()

    def _reload(self, force: bool = False) -> None:
        if self._dirty() and not force:
            return
        self._loaded = True
        worker = _LoadWorker()
        worker.done.connect(self._on_loaded)
        self._keep(worker)

    def _on_loaded(self, data: dict) -> None:
        self._fill_battery(data["batteries"])
        self._support = data["support"]
        self._laptop = self._support.laptop
        self._saved = data["config"]
        self._draft = copy.deepcopy(self._saved)
        if self._draft.plan(self._edit_plan) is None:
            self._edit_plan = self._draft.active
        self._fill_all()
        self._fill_status(data["status"], data["ppd"], data["state"])
        self._fill_conflicts(self._support.conflicts)
        self._fill_hibernate(self._support.hibernate)

    def _fill_battery(self, batteries: list) -> None:
        if not batteries:
            self._battery_card.hide()
            return
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
            self._limit_box.show()
            idx = self._limit.findData(bat.charge_limit)
            if idx >= 0:
                self._limit.setCurrentIndex(idx)

    def _fill_status(self, status: dict, ppd_now: str, state: powerplan.PowerState) -> None:
        source = tr("plugged in") if state.on_ac else tr("on battery")
        if not status:
            plan, reason = powerplan.effective_plan(self._saved, state)
            note = tr("The power plan service is not running; some settings are not applied.")
        else:
            plan = self._saved.plan(str(status.get("plan"))) or self._saved.plan(self._saved.active)
            reason = str(status.get("reason", "active"))
            note = ""
        if plan is None:
            return
        line = tr("Now using: {plan} ({source})").format(plan=texts.plan_name(plan), source=source)
        if reason == "battery_saver":
            line += " — " + tr("because the battery is low")
        elif reason == "schedule":
            line += " — " + tr("because of the schedule")
        self._now_lbl.setText(line + (f"\n{note}" if note else ""))

        # Sistem menüsünden güç kipi değiştirildiyse uyar
        want = self._saved.value(plan, "ppd_profile", "ac" if state.on_ac else "bat")
        if want != AUTO and ppd_now and ppd_now != want:
            self._ppd_warn.setText(
                tr(
                    "The power mode was changed from the system menu ({now}). This plan uses "
                    "{want}; it is set again when the plan or power source changes, or when "
                    'you press "Reapply plan".'
                ).format(
                    now=texts.value_text("ppd_profile", ppd_now),
                    want=texts.value_text("ppd_profile", want),
                )
            )
            self._ppd_warn.show()
        else:
            self._ppd_warn.hide()

    def _fill_conflicts(self, tools: list[power_support.ConflictTool]) -> None:
        while self._conflict_btns.count():
            item = self._conflict_btns.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not tools:
            self._conflict_card.hide()
            return
        names = ", ".join(t.name for t in tools)
        self._conflict_lbl.setText(
            tr(
                "{names} also manages power settings. To avoid the two overriding each other, "
                "Linwas does not change processor, USB/PCIe/disk, wireless and graphics card "
                "settings. Removing it is recommended."
            ).format(names=names)
        )
        for tool in tools:
            if not tool.removable:
                continue
            btn = QPushButton(tr("Remove {name}").format(name=tool.name), self._conflict_card)
            btn.clicked.connect(lambda _c=False, t=tool: self._remove_tool(t))
            self._conflict_btns.addWidget(btn)
        self._conflict_btns.addStretch(1)
        self._conflict_card.show()

    def _fill_hibernate(self, info: power_support.HibernateInfo) -> None:
        if info.available:
            self._hibernate_lbl.setText(
                tr("Hibernate is available. You can choose it for sleep, the lid and buttons.")
            )
            return
        lines = [tr("Hibernate is not available on this computer:")]
        lines += [f"• {texts.hibernate_reason_text(r)}" for r in info.reasons]
        lines.append(tr("Linwas will be able to set up hibernation in a later version."))
        self._hibernate_lbl.setText("\n".join(lines))

    # --- Doldurma ---

    def _fill_all(self) -> None:
        self._filling = True
        try:
            self._fill_plans()
            self._fill_plan_combos()
            self._fill_tree()
            self._fill_quick()
            self._fill_automation()
        finally:
            self._filling = False
        self._update_dirty()

    def _fill_plans(self) -> None:
        for btn in self._plan_group.buttons():
            self._plan_group.removeButton(btn)
            btn.deleteLater()
        self._plan_ids = [p.id for p in self._draft.plans]
        for i, plan in enumerate(self._draft.plans):
            rb = QRadioButton(f"{texts.plan_name(plan)} — {texts.plan_description(plan)}", self)
            rb.setChecked(plan.id == self._draft.active)
            self._plan_group.addButton(rb, i)
            self._plan_box.addWidget(rb)

    def _fill_plan_combos(self) -> None:
        for combo in (self._edit_combo, self._saver_plan, self._sched_plan):
            combo.blockSignals(True)
            combo.clear()
            for plan in self._draft.plans:
                combo.addItem(texts.plan_name(plan), plan.id)
            combo.blockSignals(False)
        self._edit_combo.setCurrentIndex(max(0, self._edit_combo.findData(self._edit_plan)))
        plan = self._draft.plan(self._edit_plan)
        custom = bool(plan and not plan.builtin)
        self._rename_btn.setEnabled(custom)
        self._delete_btn.setEnabled(custom)

    def _choices(self, sid: str, current: str) -> list[str]:
        spec = SPECS[sid]
        values = list(spec.values)
        support = self._support
        if support and sid in support.values:
            values = [v for v in values if v in support.values[sid]]
        if support and not support.hibernate.available:
            values = [v for v in values if v not in _HIBERNATE_VALUES]
        if current != AUTO and current not in values:
            values.append(current)
        return [AUTO, *values]

    def _fill_combo(self, combo: QComboBox, sid: str, value: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for v in self._choices(sid, value):
            combo.addItem(texts.value_text(sid, v), v)
        combo.setCurrentIndex(max(0, combo.findData(value)))
        combo.blockSignals(False)

    def _visible(self, sid: str) -> bool:
        spec = SPECS[sid]
        return not (spec.laptop_only and not self._laptop)

    def _fill_tree(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        self._tree.clear()
        self._tree_combos.clear()
        self._tree_items.clear()
        split_cols = self._laptop
        self._tree.setColumnHidden(2, not split_cols)
        self._tree.setHeaderLabels(
            [tr("Setting"), tr("Plugged in") if split_cols else tr("Value"), tr("On battery")]
        )
        unsupported = self._support.unsupported if self._support else {}
        for section in SECTIONS:
            specs = [s for s in SETTINGS if s.section == section and self._visible(s.id)]
            if not specs:
                continue
            top = QTreeWidgetItem(self._tree, [texts.section_name(section)])
            top.setFirstColumnSpanned(True)
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            for spec in specs:
                item = QTreeWidgetItem(top, [texts.setting_name(spec.id)])
                reason = unsupported.get(spec.id, "")
                tip = texts.setting_help(spec.id)
                if reason:
                    tip = texts.reason_text(reason) + (f"\n{tip}" if tip else "")
                    item.setText(0, f"{texts.setting_name(spec.id)} ({texts.reason_text(reason)})")
                item.setToolTip(0, tip)
                self._tree_items[spec.id] = item
                sources = powerplan.SOURCES if (spec.split and split_cols) else ("ac",)
                for col, src in enumerate(sources, start=1):
                    combo = QComboBox(self._tree)
                    self._fill_combo(combo, spec.id, self._draft.value(plan, spec.id, src))
                    combo.setEnabled(not reason)
                    combo.currentIndexChanged.connect(
                        lambda _i, s=spec.id, so=src, c=combo: self._on_combo(s, so, c)
                    )
                    self._tree.setItemWidget(item, col, combo)
                    self._tree_combos[(spec.id, src)] = combo
            top.setExpanded(section in ("display", "buttons", "cpu"))

    def _fill_quick(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        self._quick_title.setText(
            tr("Common settings for {plan}").format(plan=texts.plan_name(plan))
        )
        unsupported = self._support.unsupported if self._support else {}
        for lbl in self._quick_heads:
            lbl.setVisible(self._laptop)
        for (sid, src), combo in self._quick_combos.items():
            self._fill_combo(combo, sid, self._draft.value(plan, sid, src))
            combo.setEnabled(sid not in unsupported)
            combo.setVisible(src == "ac" or self._laptop)

    def _fill_automation(self) -> None:
        saver = self._draft.battery_saver
        sched = self._draft.schedule
        self._saver_chk.setChecked(saver.enabled)
        self._saver_pct.setValue(saver.threshold)
        self._saver_plan.setCurrentIndex(max(0, self._saver_plan.findData(saver.plan)))
        self._sched_chk.setChecked(sched.enabled)
        self._sched_start.setTime(QTime.fromString(sched.start, "HH:mm"))
        self._sched_end.setTime(QTime.fromString(sched.end, "HH:mm"))
        self._sched_plan.setCurrentIndex(max(0, self._sched_plan.findData(sched.plan)))

    # --- Düzenleme ---

    def _dirty(self) -> bool:
        return powerplan.dumps(self._draft) != powerplan.dumps(self._saved)

    def _update_dirty(self) -> None:
        self._save_bar.setVisible(self._dirty())

    def _on_combo(self, sid: str, src: str, combo: QComboBox) -> None:
        if self._filling:
            return
        value = combo.currentData()
        spec = SPECS[sid]
        # Tek değerli ayar ya da masaüstü bilgisayar: prizde ve pilde aynı değer
        sources = powerplan.SOURCES if not (spec.split and self._laptop) else (src,)
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        target = plan.values if spec.per_plan else self._draft.globals
        pair = target.setdefault(sid, {"ac": AUTO, "bat": AUTO})
        for s in sources:
            pair[s] = value
        if pair == {"ac": AUTO, "bat": AUTO}:
            target.pop(sid, None)
        # Aynı ayar hem hızlı kartta hem ağaçta: diğerini eşitle
        self._filling = True
        try:
            for combos in (self._quick_combos, self._tree_combos):
                for s in sources:
                    other = combos.get((sid, s))
                    if other is not None and other is not combo:
                        other.setCurrentIndex(max(0, other.findData(value)))
        finally:
            self._filling = False
        self._update_dirty()

    def _on_edit_plan_changed(self, index: int) -> None:
        if self._filling or index < 0:
            return
        self._edit_plan = self._edit_combo.itemData(index)
        self._filling = True
        try:
            self._fill_plan_combos()
            self._fill_tree()
            self._fill_quick()
        finally:
            self._filling = False

    def _on_automation(self, *_args: object) -> None:
        if self._filling:
            return
        saver = self._draft.battery_saver
        saver.enabled = self._saver_chk.isChecked()
        saver.threshold = self._saver_pct.value()
        saver.plan = self._saver_plan.currentData() or saver.plan
        sched = self._draft.schedule
        sched.enabled = self._sched_chk.isChecked()
        sched.start = self._sched_start.time().toString("HH:mm")
        sched.end = self._sched_end.time().toString("HH:mm")
        sched.plan = self._sched_plan.currentData() or sched.plan
        self._update_dirty()

    def _validate(self) -> str:
        for plan in self._draft.plans:
            for src in powerplan.SOURCES:
                lo, hi = plan.get("cpu_min", src), plan.get("cpu_max", src)
                if AUTO not in (lo, hi) and int(lo) > int(hi):
                    return tr(
                        "In {plan}, the minimum processor state is higher than the maximum."
                    ).format(plan=texts.plan_name(plan))
        g = self._draft.globals
        levels = [
            g.get(k, {}).get("ac", AUTO)
            for k in ("battery_low", "battery_critical", "battery_action_level")
        ]
        known = [int(v) for v in levels if v != AUTO]
        if known != sorted(known, reverse=True) or len(set(known)) != len(known):
            return tr("Battery levels must be: low > critical > action level.")
        sched = self._draft.schedule
        if sched.enabled and sched.start == sched.end:
            return tr("The schedule start and end times are the same.")
        return ""

    def _save(self) -> None:
        error = self._validate()
        if error:
            QMessageBox.warning(self, tr("Power plan"), error)
            return
        self._pending_save = True
        self.task_run_now.emit(
            Task(
                label=tr("Save power plan settings"),
                steps=[
                    TaskStep(
                        op_id="power.save_config",
                        params={"config": powerplan.dumps(self._draft)},
                    )
                ],
            )
        )

    def _discard(self) -> None:
        self._draft = copy.deepcopy(self._saved)
        if self._draft.plan(self._edit_plan) is None:
            self._edit_plan = self._draft.active
        self._fill_all()

    # --- Plan işlemleri ---

    def _on_plan_clicked(self, index: int) -> None:
        if not 0 <= index < len(self._plan_ids):
            return
        plan_id = self._plan_ids[index]
        if plan_id == self._draft.active:
            return
        other_changes = self._dirty_except_active()
        self._draft.active = plan_id
        if other_changes or self._saved.plan(plan_id) is None:
            self._update_dirty()  # diğer değişikliklerle birlikte kaydedilir
            return
        if power.can_switch_plan_directly():
            worker = _SwitchWorker(plan_id)
            worker.done.connect(self._on_switched)
            self._keep(worker)
        else:
            self._save()  # kaynak koddan çalışırken: root helper (şifre)

    def _dirty_except_active(self) -> bool:
        a = copy.deepcopy(self._draft)
        a.active = self._saved.active
        return powerplan.dumps(a) != powerplan.dumps(self._saved)

    def _on_switched(self, ok: bool) -> None:
        if not ok:
            QMessageBox.warning(self, tr("Power plan"), tr("The power plan could not be changed."))
        self._reload(force=True)

    def _reapply(self) -> None:
        plan_id = self._saved.active
        if power.can_switch_plan_directly():
            worker = _SwitchWorker(plan_id)
            worker.done.connect(self._on_switched)
            self._keep(worker)
        else:
            self._save()

    def _ask_name(self, title: str, text: str = "") -> str:
        name, ok = QInputDialog.getText(self, title, tr("Plan name:"), text=text)
        name = " ".join(name.split())
        if not ok or not name:
            return ""
        return name[: powerplan.MAX_NAME_LEN]

    def _new_plan(self) -> None:
        name = self._ask_name(tr("New power plan"))
        if not name:
            return
        try:
            plan = powerplan.new_custom_plan(self._draft, name, based_on=self._edit_plan)
        except powerplan.PowerConfigError:
            QMessageBox.warning(
                self,
                tr("Power plan"),
                tr("You can have at most {n} custom plans.").format(n=powerplan.MAX_CUSTOM_PLANS),
            )
            return
        self._edit_plan = plan.id
        self._fill_all()

    def _rename_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None or plan.builtin:
            return
        name = self._ask_name(tr("Rename power plan"), plan.name)
        if name:
            plan.name = name
            self._fill_all()

    def _delete_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None or plan.builtin:
            return
        answer = QMessageBox.question(
            self, tr("Power plan"), tr('Delete the plan "{name}"?').format(name=plan.name)
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        powerplan.delete_plan(self._draft, plan.id)
        self._edit_plan = self._draft.active
        self._fill_all()

    def _reset_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        answer = QMessageBox.question(
            self,
            tr("Power plan"),
            tr('Restore the default settings of "{name}"?').format(name=texts.plan_name(plan)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            powerplan.reset_plan(self._draft, plan.id)
            self._fill_all()

    def _reset_all(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Power plan"),
            tr(
                "Restore all power settings to their defaults? Custom plans and automatic "
                "switching are removed."
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._draft = powerplan.default_config()
            self._edit_plan = self._draft.active
            self._fill_all()

    def _export_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        name = texts.plan_name(plan)
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export power plan"),
            str(Path.home() / f"{name}.json"),
            tr("Power plan (*.json)"),
        )
        if not path:
            return
        try:
            Path(path).write_text(powerplan.export_plan(self._draft, plan.id, name), "utf-8")
        except OSError as exc:
            QMessageBox.warning(self, tr("Power plan"), str(exc))

    def _import_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Import power plan"), str(Path.home()), tr("Power plan (*.json)")
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            plan = powerplan.import_plan(self._draft, text, default_name=tr("Imported plan"))
        except (OSError, UnicodeDecodeError, powerplan.PowerConfigError):
            QMessageBox.warning(
                self, tr("Power plan"), tr("This file is not a valid Linwas power plan.")
            )
            return
        self._edit_plan = plan.id
        self._fill_all()

    # --- Diğer işlemler ---

    def _on_report_action(self, action: str) -> None:
        target = {
            "charge_limit": self._battery_card,
            "automation": self._automation_card,
            "advanced": self._advanced_card,
        }.get(action)
        if target is not None:
            self._scroll.ensureWidgetVisible(target, 0, 40)

    def _remove_tool(self, tool: power_support.ConflictTool) -> None:
        op, param = (
            ("package.remove", "name") if tool.removable == "apt" else ("app.remove_snap", "name")
        )
        self.task_run_now.emit(
            Task(
                label=tr("Remove {name}").format(name=tool.name),
                steps=[TaskStep(op_id=op, params={param: tool.package})],
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
