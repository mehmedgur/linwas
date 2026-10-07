"""Güncelleme merkezi (Windows Update benzeri): sistem güncellemeleri, sürücüler, firmware,
güncelleme geçmişi ve gelişmiş seçenekler (otomatik kurulum, duraklatma) tek sayfada.

Kararlar: docs/kararlar.md › Güncelleme merkezi.
"""

from __future__ import annotations

import contextlib
import html
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import (
    QCoreApplication,
    QDateTime,
    QLocale,
    QProcess,
    Qt,
    QThread,
    QTime,
    Signal,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.drivers import DriverCandidate, DriverCategory, list_drivers
from linwas.backend.packages import apt_cache_age_hours, list_upgradable
from linwas.backend.update_history import HistoryRecord, load_history
from linwas.core import autoupdate
from linwas.core.tasks import Task, TaskStep
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.drivers import DriversPage
from linwas.ui.pages.updates import UpdatesPage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("UpdateCenterPage", text)


def _local(dt: datetime) -> str:
    stamp = QDateTime.fromSecsSinceEpoch(int(dt.timestamp()))
    return QLocale().toString(stamp, QLocale.FormatType.ShortFormat)


def _last_check_text() -> str:
    age = apt_cache_age_hours()
    if age is None:
        return tr("Last checked: unknown")
    if age < 1:
        return tr("Last checked: less than an hour ago")
    if age < 24:
        return tr("Last checked: {h} hour(s) ago").format(h=int(age))
    return tr("Last checked: {d} day(s) ago").format(d=int(age / 24))


# --- Özet (arka planda) ---


@dataclass
class _Summary:
    updates: int = 0
    security: int = 0
    drivers: list[DriverCandidate] = field(default_factory=list)
    reboot: bool = False
    scheduled: datetime | None = None
    config: autoupdate.AutoUpdateConfig = field(default_factory=autoupdate.AutoUpdateConfig)
    state: autoupdate.AutoUpdateState = field(default_factory=autoupdate.AutoUpdateState)

    def pending_drivers(self, firmware: bool) -> int:
        return sum(
            1
            for d in self.drivers
            if d.recommended
            and not d.installed
            and (d.category == DriverCategory.FIRMWARE) == firmware
        )


class _SummaryWorker(QThread):
    done = Signal(object)  # _Summary

    def run(self) -> None:
        s = _Summary()
        try:
            pkgs = list_upgradable()
            s.updates = len(pkgs)
            s.security = sum(1 for p in pkgs if p.is_security)
        except Exception:
            pass
        with contextlib.suppress(Exception):
            s.drivers = list_drivers()
        s.reboot = autoupdate.reboot_required()
        s.scheduled = autoupdate.scheduled_reboot()
        s.config = autoupdate.load_config()
        s.state = autoupdate.load_state()
        self.done.emit(s)


class _HistoryWorker(QThread):
    done = Signal(list)  # list[HistoryRecord]

    def run(self) -> None:
        try:
            self.done.emit(load_history())
        except Exception:
            self.done.emit([])


# --- Yardımcı bileşenler ---


class _NavRow(Card):
    """Ana görünümdeki tıklanabilir bölüm satırı (simge, başlık, alt metin, ›)."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("clickable", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.layout.setContentsMargins(16, 10, 16, 10)
        row = QHBoxLayout()
        row.setSpacing(12)
        ic = QLabel(self)
        icons.bind(ic, icon, "accent", 22)
        row.addWidget(ic)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self._title = QLabel(title, self)
        self._title.setObjectName("AppName")
        texts.addWidget(self._title)
        self._sub = QLabel("", self)
        self._sub.setObjectName("Secondary")
        self._sub.setWordWrap(True)
        texts.addWidget(self._sub)
        row.addLayout(texts, 1)
        chevron = QLabel(self)
        icons.bind(chevron, "chevron_right", "secondary", 16)
        row.addWidget(chevron)
        self.layout.addLayout(row)
        self.setAccessibleName(title)

    def set_subtitle(self, text: str) -> None:
        self._sub.setText(text)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _scroll(content: QWidget, parent: QWidget) -> QScrollArea:
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


# --- Güncelleme geçmişi ---


class _HistoryView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _HistoryWorker | None = None
        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(24, 8, 24, 20)
        self._layout.setSpacing(8)
        title = QLabel(tr("Update history"), content)
        title.setObjectName("H1")
        self._layout.addWidget(title)
        self._status = QLabel(tr("Loading…"), content)
        self._status.setObjectName("Secondary")
        self._layout.addWidget(self._status)
        self._list = QVBoxLayout()
        self._list.setSpacing(8)
        self._layout.addLayout(self._list)
        self._layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(content, self))

    def reload(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._worker = _HistoryWorker(self)
        self._worker.done.connect(self._on_loaded)
        self._worker.start()

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self.reload()

    def _on_loaded(self, records: list) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._status.setVisible(not records)
        self._status.setText(tr("No updates have been installed yet."))
        for record in records:
            self._list.addWidget(self._record_card(record))

    def _record_card(self, record: HistoryRecord) -> Card:
        card = Card(self)
        card.layout.setContentsMargins(14, 10, 14, 10)
        head = QHBoxLayout()
        if record.kind == "upgrade":
            text = tr("{n} package(s) updated").format(n=len(record.upgraded))
        elif record.kind == "install":
            text = tr("{n} package(s) installed").format(n=len(record.installed))
        else:
            text = tr("{n} package(s) removed").format(n=len(record.removed))
        title = QLabel(text, card)
        title.setObjectName("AppName")
        head.addWidget(title)
        if record.automatic:
            pill = QLabel(tr("Automatic"), card)
            pill.setObjectName("Pill")
            head.addWidget(pill)
        if record.error:
            err = QLabel("✗ " + tr("Failed"), card)
            err.setObjectName("Warning")
            head.addWidget(err)
        head.addStretch(1)
        when = QDateTime.fromString(record.start, "yyyy-MM-dd HH:mm:ss")
        date = QLabel(QLocale().toString(when, QLocale.FormatType.ShortFormat), card)
        date.setObjectName("Secondary")
        head.addWidget(date)
        more = QPushButton(tr("Details"), card)
        head.addWidget(more)
        card.layout.addLayout(head)

        lines = [f"↑ {p.name}  {p.old} → {p.new}" for p in record.upgraded]
        lines += [f"+ {p.name}  {p.new}" for p in record.installed]
        lines += [f"− {p.name}  {p.old}" for p in record.removed]
        if record.error:
            lines.append(tr("Error: {error}").format(error=record.error))
        detail = QLabel("<br>".join(html.escape(x) for x in lines), card)
        detail.setTextFormat(Qt.TextFormat.RichText)
        detail.setObjectName("Caption")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.hide()
        card.layout.addWidget(detail)
        more.clicked.connect(lambda: detail.setVisible(not detail.isVisible()))
        return card


# --- Gelişmiş seçenekler ---


class _AdvancedView(QWidget):
    configure = Signal(bool, bool, int)  # (açık, yedek, duraklatma haftası; -1 = değiştirme)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 8, 24, 20)
        layout.setSpacing(12)
        title = QLabel(tr("Advanced options"), content)
        title.setObjectName("H1")
        layout.addWidget(title)

        card = Card(content)
        h = QLabel(tr("Automatic updates"), card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        self._enabled = QCheckBox(tr("Install system and security updates automatically"), card)
        card.layout.addWidget(self._enabled)
        self._snapshot = QCheckBox(
            tr("Take a quick system backup (Timeshift) before installing"), card
        )
        card.layout.addWidget(self._snapshot)
        info = QLabel(
            tr(
                "Linwas checks once a day. It waits while the laptop runs on battery and on "
                "metered connections (e.g. a phone hotspot). Driver changes, a new kernel series "
                "and firmware are never installed without you. Linwas never restarts the "
                "computer by itself."
            ),
            card,
        )
        info.setObjectName("Secondary")
        info.setWordWrap(True)
        card.layout.addWidget(info)
        self._warning = QLabel("", card)
        self._warning.setObjectName("Warning")
        self._warning.setWordWrap(True)
        self._warning.hide()
        card.layout.addWidget(self._warning)
        self._save = QPushButton(tr("Save"), card)
        self._save.setProperty("primary", True)
        self._save.setEnabled(False)
        self._save.clicked.connect(self._on_save)
        card.layout.addWidget(self._save, 0, Qt.AlignmentFlag.AlignLeft)
        self._enabled.toggled.connect(self._changed)
        self._snapshot.toggled.connect(self._changed)
        layout.addWidget(card)

        last = Card(content)
        h2 = QLabel(tr("Last automatic check"), last)
        h2.setObjectName("H2")
        last.layout.addWidget(h2)
        self._last = QLabel("", last)
        self._last.setWordWrap(True)
        last.layout.addWidget(self._last)
        layout.addWidget(last)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(content, self))
        self._config = autoupdate.AutoUpdateConfig()

    def set_data(self, summary: _Summary) -> None:
        self._config = summary.config
        for box, value in (
            (self._enabled, summary.config.enabled),
            (self._snapshot, summary.config.snapshot),
        ):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)
        self._save.setEnabled(False)
        from shutil import which

        has_timeshift = which("timeshift") is not None
        self._snapshot.setEnabled(has_timeshift)
        warnings = []
        if not has_timeshift:
            warnings.append(tr("Timeshift is not installed, so no backup is taken."))
        if not autoupdate.timer_installed():
            warnings.append(
                tr(
                    "The automatic update service is not installed. It comes with the Linwas "
                    "package (not when running from source)."
                )
            )
        self._warning.setText("\n".join(warnings))
        self._warning.setVisible(bool(warnings))
        self._last.setText(self._state_text(summary.state))

    @staticmethod
    def _state_text(state: autoupdate.AutoUpdateState) -> str:
        if not state.last_run:
            return tr("Not run yet.")
        try:
            when = _local(datetime.fromisoformat(state.last_run))
        except ValueError:
            when = state.last_run
        reasons = {
            "disabled": tr("automatic updates are off"),
            "paused": tr("updates are paused"),
            "battery": tr("the computer was on battery"),
            "metered": tr("the connection was metered"),
        }
        if state.result == "updated":
            text = tr("{when}: {n} package(s) updated.").format(when=when, n=len(state.packages))
        elif state.result == "up_to_date":
            text = tr("{when}: the system was up to date.").format(when=when)
        elif state.result == "skipped":
            text = tr("{when}: skipped because {why}.").format(
                when=when, why=reasons.get(state.reason, state.reason)
            )
        else:
            text = tr("{when}: the update failed.").format(when=when)
            if state.error:
                text += "\n" + state.error.strip().splitlines()[-1]
        if state.snapshot:
            text += "\n" + tr("Backup taken: {name}").format(name=state.snapshot)
        return text

    def _changed(self) -> None:
        self._save.setEnabled(
            (self._enabled.isChecked(), self._snapshot.isChecked())
            != (self._config.enabled, self._config.snapshot)
        )

    def _on_save(self) -> None:
        self.configure.emit(self._enabled.isChecked(), self._snapshot.isChecked(), -1)


# --- Sayfa ---


class UpdateCenterPage(BasePage):
    SECTIONS = ("system", "drivers", "firmware", "history", "advanced")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary = _Summary()
        self._worker: _SummaryWorker | None = None
        self._loaded = False

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_home())

        self._system = UpdatesPage()
        self._drivers = DriversPage(
            categories={DriverCategory.GPU, DriverCategory.NETWORK}, title=tr("Drivers")
        )
        self._firmware = DriversPage(categories={DriverCategory.FIRMWARE}, title=tr("Firmware"))
        for sub in (self._system, self._drivers, self._firmware):
            sub.task_requested.connect(self.task_requested)
            sub.task_run_now.connect(self.task_run_now)
            sub.page_requested.connect(self.page_requested)
        self._history = _HistoryView()
        self._advanced = _AdvancedView()
        self._advanced.configure.connect(self._configure)
        self._views = {
            "system": self._system,
            "drivers": self._drivers,
            "firmware": self._firmware,
            "history": self._history,
            "advanced": self._advanced,
        }
        for view in self._views.values():
            self._stack.addWidget(self._with_back(view))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

    # --- Ana görünüm ---

    def _build_home(self) -> QWidget:
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)
        title = QLabel(tr("Update center"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Durum kartı
        status = Card(content)
        top = QHBoxLayout()
        top.setSpacing(16)
        self._status_icon = QLabel(status)
        icons.bind(self._status_icon, "updates", "accent", 44)
        top.addWidget(self._status_icon, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._status_title = QLabel(tr("Checking for updates…"), status)
        self._status_title.setObjectName("H2")
        texts.addWidget(self._status_title)
        self._status_sub = QLabel("", status)
        self._status_sub.setObjectName("Secondary")
        self._status_sub.setWordWrap(True)
        texts.addWidget(self._status_sub)
        top.addLayout(texts, 1)
        status.layout.addLayout(top)

        buttons = QHBoxLayout()
        self._check_btn = QPushButton(tr("Check for updates"), status)
        self._check_btn.setProperty("primary", True)
        self._check_btn.setToolTip(
            tr("Downloads the latest package information (asks for your password).")
        )
        self._check_btn.clicked.connect(self._check_now)
        buttons.addWidget(self._check_btn)
        self._install_btn = QPushButton(tr("Install all"), status)
        self._install_btn.clicked.connect(self._install_all)
        self._install_btn.hide()
        buttons.addWidget(self._install_btn)
        buttons.addStretch(1)
        self._pause_btn = QPushButton(tr("Pause for 1 week"), status)
        pause_menu = QMenu(self._pause_btn)
        for weeks in range(1, autoupdate.MAX_PAUSE_WEEKS + 1):
            action = pause_menu.addAction(tr("Pause for {n} week(s)").format(n=weeks))
            action.triggered.connect(lambda _=False, w=weeks: self._pause(w))
        self._pause_menu = pause_menu
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        buttons.addWidget(self._pause_btn)
        self._more_pause = QPushButton("▾", status)
        self._more_pause.setFixedWidth(36)
        self._more_pause.setToolTip(tr("Pause for longer"))
        self._more_pause.setMenu(pause_menu)
        buttons.addWidget(self._more_pause)
        status.layout.addLayout(buttons)
        outer.addWidget(status)

        # Yeniden başlatma kartı
        self._reboot_card = Card(content)
        rh = QLabel(tr("Restart required"), self._reboot_card)
        rh.setObjectName("H2")
        self._reboot_card.layout.addWidget(rh)
        self._reboot_lbl = QLabel(
            tr("Some updates (e.g. a new kernel) take effect after a restart."), self._reboot_card
        )
        self._reboot_lbl.setWordWrap(True)
        self._reboot_card.layout.addWidget(self._reboot_lbl)
        rrow = QHBoxLayout()
        now_btn = QPushButton(tr("Restart now"), self._reboot_card)
        now_btn.setProperty("primary", True)
        now_btn.clicked.connect(self._restart_now)
        rrow.addWidget(now_btn)
        rrow.addSpacing(12)
        self._reboot_time = QTimeEdit(QTime(3, 0), self._reboot_card)
        self._reboot_time.setDisplayFormat("HH:mm")
        rrow.addWidget(self._reboot_time)
        self._schedule_btn = QPushButton(tr("Restart at this time"), self._reboot_card)
        self._schedule_btn.clicked.connect(self._schedule_restart)
        rrow.addWidget(self._schedule_btn)
        self._cancel_btn = QPushButton(tr("Cancel the planned restart"), self._reboot_card)
        self._cancel_btn.clicked.connect(self._cancel_restart)
        rrow.addWidget(self._cancel_btn)
        rrow.addStretch(1)
        self._reboot_card.layout.addLayout(rrow)
        self._reboot_card.hide()
        outer.addWidget(self._reboot_card)

        # Bölümler
        self._rows: dict[str, _NavRow] = {}
        for section, icon, text in (
            ("system", "updates", tr("System updates")),
            ("drivers", "drivers", tr("Drivers")),
            ("firmware", "hardware", tr("Firmware (BIOS, SSD, docks…)")),
            ("history", "backups", tr("Update history")),
            ("advanced", "settings", tr("Advanced options")),
        ):
            row = _NavRow(icon, text, content)
            row.clicked.connect(lambda s=section: self.open_section(s))
            self._rows[section] = row
            outer.addWidget(row)
        self._rows["history"].set_subtitle(tr("Installed, updated and removed packages"))
        outer.addStretch(1)
        return _scroll(content, self)

    def _with_back(self, view: QWidget) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(0)
        back = QPushButton("‹ " + tr("Update center"), box)
        back.setFlat(True)
        back.setStyleSheet("QPushButton { border: none; text-align: left; padding: 4px 24px; }")
        back.clicked.connect(self.open_home)
        layout.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(view, 1)
        return box

    def open_home(self) -> None:
        self._stack.setCurrentIndex(0)

    def open_section(self, section: str) -> None:
        if section in self._views:
            self._stack.setCurrentIndex(self.SECTIONS.index(section) + 1)

    # --- Veri ---

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        if not self._loaded:
            self.refresh()

    def refresh(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._loaded = True
        self._worker = _SummaryWorker(self)
        self._worker.done.connect(self._on_summary)
        self._worker.start()

    def on_tasks_finished(self) -> None:
        for sub in (self._system, self._drivers, self._firmware):
            sub.on_tasks_finished()
        self.refresh()

    def _on_summary(self, s: _Summary) -> None:
        self._summary = s
        paused = autoupdate.paused_until(s.config)
        if paused:
            title = tr("Updates are paused until {date}").format(date=_local(paused))
            icon = "updates"
        elif s.reboot:
            title = tr("Restart required")
            icon = "power"
        elif s.updates:
            title = tr("{n} update(s) available").format(n=s.updates)
            icon = "updates"
        else:
            title = tr("You're up to date")
            icon = "check"
        self._status_title.setText(title)
        icons.bind(self._status_icon, icon, "accent", 44)
        auto = (
            tr("Automatic updates are on.")
            if s.config.enabled and autoupdate.timer_installed()
            else tr("Automatic updates are off.")
        )
        self._status_sub.setText(_last_check_text() + " · " + auto)
        self._install_btn.setVisible(bool(s.updates))
        self._install_btn.setProperty("primary", bool(s.updates))
        self._check_btn.setProperty("primary", not s.updates)
        for btn in (self._install_btn, self._check_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._pause_btn.setText(tr("Resume updates") if paused else tr("Pause for 1 week"))
        self._more_pause.setVisible(not paused)

        self._reboot_card.setVisible(s.reboot or s.scheduled is not None)
        if s.scheduled:
            self._reboot_lbl.setText(
                tr("The computer will restart at {time}.").format(time=_local(s.scheduled))
            )
        self._schedule_btn.setVisible(s.scheduled is None)
        self._reboot_time.setVisible(s.scheduled is None)
        self._cancel_btn.setVisible(s.scheduled is not None)

        if s.updates:
            text = tr("{n} update(s) ready").format(n=s.updates)
            if s.security:
                text += " · " + tr("{n} security").format(n=s.security)
        else:
            text = tr("Up to date")
        self._rows["system"].set_subtitle(text)
        n = s.pending_drivers(firmware=False)
        self._rows["drivers"].set_subtitle(
            tr("{n} recommended driver(s)").format(n=n) if n else tr("Graphics, network and Wi-Fi")
        )
        n = s.pending_drivers(firmware=True)
        self._rows["firmware"].set_subtitle(
            tr("{n} firmware update(s)").format(n=n) if n else tr("No firmware updates")
        )
        self._rows["advanced"].set_subtitle(auto)
        self._advanced.set_data(s)

    # --- İşlemler ---

    def _check_now(self) -> None:
        self._status_title.setText(tr("Checking for updates…"))
        self.task_run_now.emit(
            Task(
                label=tr("Check for updates"),
                steps=[TaskStep(op_id="package.update_index", params={})],
            )
        )

    def _install_all(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install updates"),
                steps=[
                    TaskStep(op_id="package.update_index", params={}),
                    TaskStep(op_id="package.update_all", params={}),
                ],
            )
        )

    def _configure(self, enabled: bool, snapshot: bool, pause_weeks: int) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Change automatic update settings"),
                steps=[
                    TaskStep(
                        op_id="autoupdate.configure",
                        params={
                            "enabled": "true" if enabled else "false",
                            "snapshot": "true" if snapshot else "false",
                            "pause_weeks": str(pause_weeks),
                        },
                    )
                ],
            )
        )

    def _on_pause_clicked(self) -> None:
        if autoupdate.paused_until(self._summary.config):
            self._pause(0)
        else:
            self._pause(1)

    def _pause(self, weeks: int) -> None:
        cfg = self._summary.config
        self._configure(cfg.enabled, cfg.snapshot, weeks)

    def _restart_now(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Restart now"),
            tr("Save your work and close your programs. Restart the computer now?"),
        )
        if answer == QMessageBox.StandardButton.Yes:
            # Etkin oturumdaki kullanıcı logind üzerinden yeniden başlatabilir (şifre gerekmez)
            QProcess.startDetached("systemctl", ["reboot"])

    def _schedule_restart(self) -> None:
        time = self._reboot_time.time().toString("HH:mm")
        self.task_run_now.emit(
            Task(
                label=tr("Restart at {time}").format(time=time),
                steps=[TaskStep(op_id="power.schedule_reboot", params={"time": time})],
            )
        )

    def _cancel_restart(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Cancel the planned restart"),
                steps=[TaskStep(op_id="power.cancel_reboot", params={})],
            )
        )
