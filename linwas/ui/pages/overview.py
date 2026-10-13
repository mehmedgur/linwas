"""Genel Bakış sayfası: bilgisayar kartı, durum kartları, öneriler, hızlı işlemler, sistem sağlığı.

Bütün değerler gerçek sistem verisinden okunur; okunamayan bilgi gösterilmez ya da "okunamadı"
olarak işaretlenir. Durumlar: denetleniyor / iyi / işlem gerekiyor / desteklenmiyor / hata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import health
from linwas.ui import icons
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("OverviewPage", text)


def _size(n: int) -> str:
    return QLocale().formattedDataSize(n, 1, QLocale.DataSizeFormat.DataSizeSIFormat)


# Durum → (yazı rengi, zemin); renkler açık ve koyu temada okunur
CHECKING, GOOD, ACTION, UNSUPPORTED, ERROR = "checking", "good", "action", "unsupported", "error"
_STATE_STYLE = {
    health.OK: ("#1e6b1e", "#e3f5e1"),
    health.WARN: ("#8a5300", "#fff1cc"),
    health.BAD: ("#a4161a", "#fde2e4"),
    GOOD: ("#1e6b1e", "#e3f5e1"),
    ACTION: ("#8a5300", "#fff1cc"),
    ERROR: ("#a4161a", "#fde2e4"),
    UNSUPPORTED: ("#4a4a4f", "#ebebef"),
    CHECKING: ("#4a4a4f", "#ebebef"),
}


def _state_text(state: str) -> str:
    return {
        health.OK: tr("Good"),
        health.WARN: tr("Check"),
        health.BAD: tr("Needs attention"),
        GOOD: tr("Up to date"),
        ACTION: tr("Action needed"),
        ERROR: tr("Error"),
        UNSUPPORTED: tr("Not supported"),
        CHECKING: tr("Checking…"),
    }[state]


def _pill(state: str, parent: QWidget, text: str | None = None) -> QLabel:
    fg, bg = _STATE_STYLE[state]
    pill = QLabel(text or _state_text(state), parent)
    pill.setStyleSheet(
        f"background:{bg}; color:{fg}; border-radius:10px; padding:2px 10px;"
        " font-size: 13px; font-weight: bold;"
    )
    return pill


def _icon_label(name: str, parent: QWidget, size: int = 40) -> QLabel:
    """Kart simgesi: nötr kutu (kenar çubuğu ile aynı sakin stil)."""
    lbl = QLabel(parent)
    lbl.setFixedSize(size, size)
    icons.bind(lbl, name, "tile", size)
    return lbl


def _clear(layout) -> None:  # noqa: ANN001 - QLayout
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


# --- Veri toplama (arka planda) ---


@dataclass
class _Status:
    state: str
    text: str


@dataclass
class _Snapshot:
    computer: str = ""
    model: str = ""
    system: str = ""
    specs: list[str] = field(default_factory=list)
    updates: _Status | None = None
    drivers: _Status | None = None
    network: _Status | None = None
    # (sayfa kimliği, başlık, açıklama, düğme)
    suggestions: list[tuple[str, str, str, str]] = field(default_factory=list)


def _collect() -> _Snapshot:
    import os

    from linwas.backend.desktop import detect_desktop
    from linwas.backend.distro import detect_distro
    from linwas.plugins.hardware_info import probe
    from linwas.plugins.hardware_info.widgets import short_device_name

    snap = _Snapshot()
    m = probe.machine_info()
    snap.computer = m.title or tr("This computer")
    snap.model = m.product if m.product and m.product != snap.computer else ""
    desktop = detect_desktop(os.environ).value
    desktop_name = desktop.upper() if len(desktop) <= 5 else desktop.title()
    snap.system = f"{detect_distro().display_name} · {desktop_name}"
    cpu = probe.cpu_info()
    mem = probe.memory_usage()
    if cpu.model:
        snap.specs.append(cpu.model)
    if mem.total:
        snap.specs.append(tr("%1 RAM").replace("%1", _size(mem.total)))

    # Sürücüler ve ekran kartları
    try:
        from linwas.backend import devices

        devs = devices.list_devices()
        gpus = [short_device_name(d.name) for d in devs if d.group == "display"]
        snap.specs.extend(gpus)
        problems = [d for d in devs if d.problem]
        snap.drivers = (
            _Status(ACTION, tr("%1 device(s) have no driver").replace("%1", str(len(problems))))
            if problems
            else _Status(GOOD, tr("All devices have a driver"))
        )
    except Exception:
        snap.drivers = _Status(ERROR, tr("Devices could not be read"))

    # Güncellemeler (APT önbelleğinden; ağ gerekmez)
    try:
        from linwas.backend.packages import count_upgradable

        total, security = count_upgradable()
        if total:
            text = tr("%1 update(s) ready").replace("%1", str(total))
            if security:
                text += " · " + tr("%1 security").replace("%1", str(security))
            snap.updates = _Status(ACTION, text)
            snap.suggestions.append(("updates", tr("Install updates"), text, tr("Open")))
        else:
            snap.updates = _Status(GOOD, tr("The system is up to date"))
    except Exception:
        snap.updates = _Status(ERROR, tr("Updates could not be checked"))

    # Wi-Fi ve Bluetooth
    try:
        from linwas.backend import network

        wifi = network.wifi_status()
        if not wifi.device:
            snap.network = _Status(UNSUPPORTED, tr("No Wi-Fi adapter"))
        elif wifi.connected:
            snap.network = _Status(GOOD, tr("Connected to %1").replace("%1", wifi.ssid))
        elif not wifi.enabled:
            snap.network = _Status(ACTION, tr("Wi-Fi is off"))
        else:
            snap.network = _Status(ACTION, tr("Not connected"))
        bt = tr("Bluetooth on") if network.bluetooth_enabled() else tr("Bluetooth off")
        snap.network.text += " · " + bt
    except Exception:
        snap.network = _Status(ERROR, tr("Network status could not be read"))

    # Öneriler: yalnızca doğrulanmış olanlar
    try:
        from linwas.backend.backups import timeshift_available

        if not timeshift_available():
            snap.suggestions.append(
                (
                    "backups",
                    tr("Set up system restore"),
                    tr(
                        "Timeshift is not installed; there is no way back if an update "
                        "breaks the system."
                    ),
                    tr("Set up"),
                )
            )
    except Exception:
        pass
    try:
        from linwas.backend import firmware

        if firmware.available():
            updates = firmware.list_updates()
            if updates:
                snap.suggestions.append(
                    (
                        "updates",
                        tr("Firmware update"),
                        tr("An update is available for %1.").replace(
                            "%1", ", ".join(d.name for d in updates[:3])
                        ),
                        tr("Open"),
                    )
                )
    except Exception:
        pass
    for bat in probe.batteries():
        if bat.health is not None and bat.health < 80:
            snap.suggestions.append(
                (
                    "power",
                    tr("Protect the battery"),
                    tr("Battery health is %1%. Charge limiting can slow further wear.").replace(
                        "%1", str(bat.health)
                    ),
                    tr("Open"),
                )
            )
    return snap


class _Worker(QThread):
    done = Signal(object)

    def run(self) -> None:
        try:
            self.done.emit(_collect())
        except Exception:
            self.done.emit(None)


# --- Kartlar ---


class _QuickActionCard(Card):
    """Hızlı işlem kartı: simge + başlık + kısa açıklama."""

    clicked = Signal()

    def __init__(
        self, title: str, description: str, icon: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("clickable", True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(_icon_label(icon, self), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        lbl_title = QLabel(title, self)
        lbl_title.setStyleSheet("font-weight: 600;")
        texts.addWidget(lbl_title)
        lbl_desc = QLabel(description, self)
        lbl_desc.setObjectName("Secondary")
        lbl_desc.setWordWrap(True)
        texts.addWidget(lbl_desc)
        row.addLayout(texts, 1)
        self.layout.addLayout(row)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)  # type: ignore[misc]

    def keyPressEvent(self, event) -> None:  # type: ignore[override]  # noqa: ANN001
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class _StatusCard(Card):
    """Durum kartı: simge, başlık, durum rozeti ve tek satır açıklama; tıklanınca sayfa açılır."""

    clicked = Signal()
    retry = Signal()

    def __init__(self, title: str, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("clickable", True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(_icon_label(icon, self, 34))
        t = QLabel(title, self)
        t.setStyleSheet("font-weight: 600;")
        head.addWidget(t, 1)
        self._pill_box = QHBoxLayout()
        head.addLayout(self._pill_box)
        self.layout.addLayout(head)
        self._text = QLabel("", self)
        self._text.setObjectName("Secondary")
        self._text.setWordWrap(True)
        self.layout.addWidget(self._text)
        self._retry = QPushButton(tr("Try again"), self)
        self._retry.clicked.connect(self.retry)
        self._retry.hide()
        self.layout.addWidget(self._retry, 0, Qt.AlignmentFlag.AlignLeft)
        self.set_status(_Status(CHECKING, ""))

    def set_status(self, status: _Status | None) -> None:
        status = status or _Status(ERROR, tr("Could not be read"))
        _clear(self._pill_box)
        self._pill_box.addWidget(_pill(status.state, self))
        self._text.setText(status.text)
        self._text.setVisible(bool(status.text))
        self._retry.setVisible(status.state == ERROR)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        self.clicked.emit()
        super().mousePressEvent(event)  # type: ignore[misc]

    def keyPressEvent(self, event) -> None:  # type: ignore[override]  # noqa: ANN001
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class _HealthCard(Card):
    """Sistem sağlığı: her satırda ad, doluluk çubuğu, değer ve durum rozeti (gerçek değerler)."""

    page_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(12)
        self._grid.setColumnStretch(1, 1)
        self.layout.addLayout(self._grid)
        self._rows = 0

    def refresh(self) -> None:
        _clear(self._grid)
        self._rows = 0
        root = health.disk_usage(Path("/"))
        if root:
            self._add(
                tr("System disk"),
                root.percent,
                tr("%1 free of %2")
                .replace("%1", _size(root.total - root.used))
                .replace("%2", _size(root.total)),
                health.state_for(root.percent, 80, 90),
                "cleanup",
            )
        if health.home_is_separate():
            home = health.disk_usage(Path.home())
            if home:
                self._add(
                    tr("Personal files disk"),
                    home.percent,
                    tr("%1 free of %2")
                    .replace("%1", _size(home.total - home.used))
                    .replace("%2", _size(home.total)),
                    health.state_for(home.percent, 80, 90),
                    "cleanup",
                )
        mem = health.memory_usage()
        if mem:
            self._add(
                tr("Memory (RAM)"),
                mem.percent,
                tr("%1 of %2 in use")
                .replace("%1", _size(mem.used))
                .replace("%2", _size(mem.total)),
                health.state_for(mem.percent, 80, 92),
                "taskmgr",
            )
        from linwas.backend.power import list_batteries

        for bat in list_batteries():
            if bat.health is None:
                continue
            self._add(
                tr("Battery health"),
                bat.health,
                tr("%1% of its original capacity").replace("%1", str(bat.health)),
                health.battery_state(bat.health),
                "power",
            )
        self.setVisible(self._rows > 0)

    def _add(self, name: str, percent: int, detail: str, state: str, page_id: str) -> None:
        r = self._rows
        label = QLabel(name, self)
        label.setMinimumWidth(170)
        self._grid.addWidget(label, r, 0)
        bar = QProgressBar(self)
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, percent)))
        bar.setTextVisible(False)
        bar.setAccessibleName(name)
        self._grid.addWidget(bar, r, 1, Qt.AlignmentFlag.AlignVCenter)
        value = QLabel(detail, self)
        value.setObjectName("Secondary")
        self._grid.addWidget(value, r, 2)
        self._grid.addWidget(_pill(state, self), r, 3)
        more = QPushButton(tr("Open"), self)
        more.setAccessibleName(tr("Open") + " " + name)
        more.clicked.connect(lambda _=False, pid=page_id: self.page_requested.emit(pid))
        self._grid.addWidget(more, r, 4)
        self._rows += 1


# --- Sayfa ---


class OverviewPage(QWidget):
    """Genel Bakış sayfası."""

    page_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _Worker | None = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(14)

        title = QLabel(tr("Overview"), content)
        title.setObjectName("H1")
        outer.addWidget(title)

        # Bilgisayar kartı: ad › sistem › donanım hiyerarşisi
        hero = Card(content)
        hrow = QHBoxLayout()
        hrow.setSpacing(20)
        hrow.addWidget(_icon_label("laptop", hero, 72), 0, Qt.AlignmentFlag.AlignTop)
        htexts = QVBoxLayout()
        htexts.setSpacing(3)
        self._computer = QLabel(tr("This computer"), hero)
        self._computer.setStyleSheet("font-size: 24px; font-weight: 700;")
        htexts.addWidget(self._computer)
        self._model = QLabel("", hero)
        self._model.setObjectName("Secondary")
        htexts.addWidget(self._model)
        self._system = QLabel("", hero)
        htexts.addWidget(self._system)
        self._specs = QLabel("", hero)
        self._specs.setObjectName("Secondary")
        self._specs.setWordWrap(True)
        htexts.addWidget(self._specs)
        hrow.addLayout(htexts, 1)
        details = QPushButton(tr("Hardware details"), hero)
        details.clicked.connect(lambda: self.page_requested.emit("hardware"))
        hrow.addWidget(details, 0, Qt.AlignmentFlag.AlignTop)
        hero.layout.addLayout(hrow)
        outer.addWidget(hero)

        # Durum kartları (aynı hizada, eşit genişlikte)
        status_row = QHBoxLayout()
        status_row.setSpacing(14)
        self._updates_card = _StatusCard(tr("Updates"), "updates", content)
        self._drivers_card = _StatusCard(tr("Drivers"), "drivers", content)
        self._wifi_card = _StatusCard(tr("Wi-Fi & Bluetooth"), "network", content)
        for page_id, card in (
            ("updates", self._updates_card),
            ("drivers", self._drivers_card),
            ("network", self._wifi_card),
        ):
            card.clicked.connect(lambda pid=page_id: self.page_requested.emit(pid))
            card.retry.connect(self.refresh)
            status_row.addWidget(card, 1)
        outer.addLayout(status_row)

        # Öneriler (yalnızca doğrulanmış olanlar)
        sug_label = QLabel(tr("Suggestions"), content)
        sug_label.setObjectName("Secondary")
        outer.addWidget(sug_label)
        self._suggestions = Card(content)
        self._sug_box = QVBoxLayout()
        self._sug_box.setSpacing(10)
        self._suggestions.layout.addLayout(self._sug_box)
        outer.addWidget(self._suggestions)

        # Hızlı işlemler (2×2)
        quick_label = QLabel(tr("Quick actions"), content)
        quick_label.setObjectName("Secondary")
        outer.addWidget(quick_label)
        quick_grid = QGridLayout()
        quick_grid.setSpacing(14)
        quick_actions = [
            ("taskmgr", tr("Task Manager"), tr("View running processes and startup programs")),
            ("cleanup", tr("Disk Cleanup"), tr("Free up space by removing unnecessary files")),
            (
                "personal_backup",
                tr("Back Up My Files"),
                tr("Copy personal files to an external drive (not a system restore point)"),
            ),
            (
                "migrate",
                tr("Transfer"),
                tr("Bring files and settings from Windows or another Linux"),
            ),
        ]
        for i, (page_id, label, desc) in enumerate(quick_actions):
            card = _QuickActionCard(label, desc, page_id, content)
            card.clicked.connect(lambda pid=page_id: self.page_requested.emit(pid))
            quick_grid.addWidget(card, i // 2, i % 2)
        outer.addLayout(quick_grid)

        # Sistem sağlığı (gerçek değerler; sayfa her açıldığında yenilenir)
        health_label = QLabel(tr("System health"), content)
        health_label.setObjectName("Secondary")
        outer.addWidget(health_label)
        self._health = _HealthCard(content)
        self._health.page_requested.connect(self.page_requested)
        outer.addWidget(self._health)

        outer.addStretch(1)
        scroll.setWidget(content)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        self._show_checking()

    def _show_checking(self) -> None:
        _clear(self._sug_box)
        lbl = QLabel(tr("Checking what needs your attention…"), self._suggestions)
        lbl.setObjectName("Secondary")
        self._sug_box.addWidget(lbl)

    def refresh(self) -> None:
        self._health.refresh()
        if self._worker is not None and self._worker.isRunning():
            return
        for card in (self._updates_card, self._drivers_card, self._wifi_card):
            card.set_status(_Status(CHECKING, ""))
        self._show_checking()
        self._worker = _Worker()
        self._worker.done.connect(self._on_snapshot)
        self._worker.start()

    def _on_snapshot(self, snap: object) -> None:
        if not isinstance(snap, _Snapshot):
            for card in (self._updates_card, self._drivers_card, self._wifi_card):
                card.set_status(_Status(ERROR, tr("Could not be read")))
            _clear(self._sug_box)
            return
        self._computer.setText(snap.computer)
        self._model.setText(snap.model)
        self._model.setVisible(bool(snap.model))
        self._system.setText(snap.system)
        self._specs.setText(" · ".join(snap.specs))
        self._updates_card.set_status(snap.updates)
        self._drivers_card.set_status(snap.drivers)
        self._wifi_card.set_status(snap.network)
        _clear(self._sug_box)
        if not snap.suggestions:
            lbl = QLabel(tr("Nothing needs your attention right now."), self._suggestions)
            lbl.setObjectName("Secondary")
            self._sug_box.addWidget(lbl)
        for page_id, title, desc, button in snap.suggestions:
            row = QHBoxLayout()
            texts = QVBoxLayout()
            texts.setSpacing(2)
            t = QLabel(title, self._suggestions)
            t.setStyleSheet("font-weight: 600;")
            texts.addWidget(t)
            d = QLabel(desc, self._suggestions)
            d.setObjectName("Secondary")
            d.setWordWrap(True)
            texts.addWidget(d)
            row.addLayout(texts, 1)
            b = QPushButton(button, self._suggestions)
            b.setAccessibleName(f"{button}: {title}")
            b.clicked.connect(lambda _=False, pid=page_id: self.page_requested.emit(pid))
            row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
            self._sug_box.addLayout(row)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self.refresh()
        super().showEvent(event)  # type: ignore[misc]
