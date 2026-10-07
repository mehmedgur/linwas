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
    QObject,
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
from linwas.ui.pages.firmware_view import FirmwareView
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

    def __init__(self, parent: QObject | None = None, limit: int = 200) -> None:
        super().__init__(parent)
        self._limit = limit

    def run(self) -> None:
        try:
            self.done.emit(load_history(limit=self._limit))
        except Exception:
            self.done.emit([])


# --- Yardımcı bileşenler ---


class _Tile(Card):
    """Ana görünümdeki tıklanabilir kutucuk: simge + başlık, büyük sayı, kısa açıklama."""

    clicked = Signal()

    def __init__(self, icon: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("clickable", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        top = QHBoxLayout()
        ic = QLabel(self)
        icons.bind(ic, icon, "accent", 18)
        top.addWidget(ic)
        name = QLabel(title, self)
        name.setObjectName("AppName")
        top.addWidget(name)
        top.addStretch(1)
        chevron = QLabel(self)
        icons.bind(chevron, "chevron_right", "secondary", 14)
        top.addWidget(chevron)
        self.layout.addLayout(top)
        self._number = QLabel("–", self)
        self._number.setObjectName("TileNumber")
        self.layout.addWidget(self._number)
        self._caption = QLabel("", self)
        self._caption.setObjectName("Secondary")
        self._caption.setWordWrap(True)
        self.layout.addWidget(self._caption)

    def set_value(self, number: int, caption: str) -> None:
        self._number.setText(str(number) if number else "✓")
        self._number.setProperty("attention", bool(number))
        self._number.style().unpolish(self._number)
        self._number.style().polish(self._number)
        self._caption.setText(caption)

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
            categories={DriverCategory.GPU, DriverCategory.NETWORK, DriverCategory.PRINTER},
            title=tr("Drivers"),
        )
        self._firmware = FirmwareView()
        for sub in (self._system, self._drivers, self._firmware):
            sub.task_requested.connect(self.task_requested)
            sub.task_run_now.connect(self.task_run_now)
            sub.page_requested.connect(self.page_requested)
            sub.ai_help_requested.connect(self.ai_help_requested)
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
        outer.setSpacing(14)

        # Başlık satırı: başlık + durum cümlesi solda, işlemler sağda
        head = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(tr("Update center"), content)
        title.setObjectName("H1")
        texts.addWidget(title)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._status_icon = QLabel(content)
        icons.bind(self._status_icon, "updates", "accent", 16)
        status_row.addWidget(self._status_icon)
        self._status_title = QLabel(tr("Checking for updates…"), content)
        self._status_title.setObjectName("AppName")
        status_row.addWidget(self._status_title)
        self._status_sub = QLabel("", content)
        self._status_sub.setObjectName("Secondary")
        status_row.addWidget(self._status_sub)
        status_row.addStretch(1)
        texts.addLayout(status_row)
        head.addLayout(texts, 1)
        self._check_btn = QPushButton(tr("Check for updates"), content)
        self._check_btn.setToolTip(
            tr("Downloads the latest package information (asks for your password).")
        )
        self._check_btn.clicked.connect(self._check_now)
        head.addWidget(self._check_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self._install_btn = QPushButton(tr("Install all"), content)
        self._install_btn.setProperty("primary", True)
        self._install_btn.clicked.connect(self._install_all)
        self._install_btn.hide()
        head.addWidget(self._install_btn, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(head)

        # Yeniden başlatma şeridi
        self._reboot_card = Card(content)
        rrow = QHBoxLayout()
        ric = QLabel(self._reboot_card)
        icons.bind(ric, "power", "accent", 22)
        rrow.addWidget(ric)
        self._reboot_lbl = QLabel(
            tr("Restart required: some updates (e.g. a new kernel) take effect after a restart."),
            self._reboot_card,
        )
        self._reboot_lbl.setWordWrap(True)
        rrow.addWidget(self._reboot_lbl, 1)
        now_btn = QPushButton(tr("Restart now"), self._reboot_card)
        now_btn.setProperty("primary", True)
        now_btn.clicked.connect(self._restart_now)
        rrow.addWidget(now_btn)
        self._reboot_time = QTimeEdit(QTime(3, 0), self._reboot_card)
        self._reboot_time.setDisplayFormat("HH:mm")
        rrow.addWidget(self._reboot_time)
        self._schedule_btn = QPushButton(tr("Restart at this time"), self._reboot_card)
        self._schedule_btn.clicked.connect(self._schedule_restart)
        rrow.addWidget(self._schedule_btn)
        self._cancel_btn = QPushButton(tr("Cancel the planned restart"), self._reboot_card)
        self._cancel_btn.clicked.connect(self._cancel_restart)
        rrow.addWidget(self._cancel_btn)
        self._reboot_card.layout.addLayout(rrow)
        self._reboot_card.hide()
        outer.addWidget(self._reboot_card)

        # Kutucuklar: bekleyen sayıları büyük gösterir
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self._tiles: dict[str, _Tile] = {}
        for section, icon, text in (
            ("system", "updates", tr("System")),
            ("drivers", "drivers", tr("Drivers")),
            ("firmware", "hardware", tr("Firmware")),
        ):
            tile = _Tile(icon, text, content)
            tile.clicked.connect(lambda s=section: self.open_section(s))
            self._tiles[section] = tile
            tiles.addWidget(tile, 1)
        outer.addLayout(tiles)

        # Alt satır: son değişiklikler + otomatik güncelleme
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        recent = Card(content)
        rhead = QHBoxLayout()
        rt = QLabel(tr("Recent changes"), recent)
        rt.setObjectName("H2")
        rhead.addWidget(rt)
        rhead.addStretch(1)
        all_btn = QPushButton(tr("All history") + " ›", recent)
        all_btn.setFlat(True)
        all_btn.clicked.connect(lambda: self.open_section("history"))
        rhead.addWidget(all_btn)
        recent.layout.addLayout(rhead)
        self._recent = QVBoxLayout()
        self._recent.setSpacing(6)
        recent.layout.addLayout(self._recent)
        recent.layout.addStretch(1)
        bottom.addWidget(recent, 3)

        auto = Card(content)
        at = QLabel(tr("Automatic updates"), auto)
        at.setObjectName("H2")
        auto.layout.addWidget(at)
        self._auto_state = QLabel("", auto)
        self._auto_state.setObjectName("AppName")
        auto.layout.addWidget(self._auto_state)
        self._auto_detail = QLabel("", auto)
        self._auto_detail.setObjectName("Secondary")
        self._auto_detail.setWordWrap(True)
        auto.layout.addWidget(self._auto_detail)
        auto.layout.addStretch(1)
        arow = QHBoxLayout()
        self._pause_btn = QPushButton(tr("Pause"), auto)
        pause_menu = QMenu(self._pause_btn)
        for weeks in range(1, autoupdate.MAX_PAUSE_WEEKS + 1):
            action = pause_menu.addAction(tr("Pause for {n} week(s)").format(n=weeks))
            action.triggered.connect(lambda _=False, w=weeks: self._pause(w))
        self._pause_menu = pause_menu
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        arow.addWidget(self._pause_btn)
        settings_btn = QPushButton(tr("Settings"), auto)
        settings_btn.clicked.connect(lambda: self.open_section("advanced"))
        arow.addWidget(settings_btn)
        arow.addStretch(1)
        auto.layout.addLayout(arow)
        bottom.addWidget(auto, 2)
        outer.addLayout(bottom)

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
        if s.reboot:
            title, icon = tr("Restart required"), "power"
        elif s.updates:
            title, icon = tr("{n} update(s) available").format(n=s.updates), "updates"
        else:
            title, icon = tr("You're up to date"), "check"
        self._status_title.setText(title)
        icons.bind(self._status_icon, icon, "accent", 16)
        self._status_sub.setText("· " + _last_check_text())
        self._install_btn.setVisible(bool(s.updates))

        self._reboot_card.setVisible(s.reboot or s.scheduled is not None)
        if s.scheduled:
            self._reboot_lbl.setText(
                tr("The computer will restart at {time}.").format(time=_local(s.scheduled))
            )
        self._schedule_btn.setVisible(s.scheduled is None)
        self._reboot_time.setVisible(s.scheduled is None)
        self._cancel_btn.setVisible(s.scheduled is not None)

        sec = " · " + tr("{n} security").format(n=s.security) if s.security else ""
        self._tiles["system"].set_value(
            s.updates, (tr("updates waiting") + sec) if s.updates else tr("up to date")
        )
        n = s.pending_drivers(firmware=False)
        self._tiles["drivers"].set_value(
            n, tr("recommended") if n else tr("graphics, network, printers")
        )
        n = s.pending_drivers(firmware=True)
        self._tiles["firmware"].set_value(
            n, tr("updates waiting") if n else tr("BIOS, SSD, processor")
        )

        on = s.config.enabled and autoupdate.timer_installed()
        if paused:
            state = tr("Paused until {date}").format(date=_local(paused))
        else:
            state = tr("On") if on else tr("Off")
        self._auto_state.setText(state)
        self._auto_detail.setText(_AdvancedView._state_text(s.state))
        self._pause_btn.setText(tr("Resume") if paused else tr("Pause"))
        self._pause_btn.setMenu(None if paused else self._pause_menu)
        self._pause_btn.setEnabled(on or bool(paused))
        self._advanced.set_data(s)
        self._load_recent()

    def _load_recent(self) -> None:
        worker = _HistoryWorker(self, limit=3)
        worker.done.connect(self._on_recent)
        self._recent_worker = worker
        worker.start()

    def _on_recent(self, records: list) -> None:
        while self._recent.count():
            item = self._recent.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not records:
            empty = QLabel(tr("No updates have been installed yet."), self)
            empty.setObjectName("Secondary")
            self._recent.addWidget(empty)
        for record in records[:3]:
            when = QDateTime.fromString(record.start, "yyyy-MM-dd HH:mm:ss")
            names = [p.name for p in record.upgraded + record.installed + record.removed]
            text = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
            mark = "↑" if record.kind == "upgrade" else "+" if record.kind == "install" else "−"
            lbl = QLabel(
                f"<b>{mark}</b> {html.escape(text)}<br><span style='font-size:11px'>"
                f"{html.escape(QLocale().toString(when, QLocale.FormatType.ShortFormat))}"
                + (" · " + html.escape(tr("Automatic")) if record.automatic else "")
                + "</span>",
                self,
            )
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            self._recent.addWidget(lbl)

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
