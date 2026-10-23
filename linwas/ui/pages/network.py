"""Wi-Fi ve Bluetooth sayfası.

Her sekmede üstte durum kartı (simge, durum, aç/kapat), altında kart içinde liste
(Windows 11 Ayarlar ve macOS Denetim Merkezi düzeni). nmcli/bluetoothctl çağrılarının hepsi
arka planda çalışır; arayüz donmaz.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import netquality, network
from linwas.backend.desktop import detect_desktop
from linwas.backend.network import BluetoothDevice, WifiDetails, WifiNetwork, WifiStatus
from linwas.backend.settings_launcher import command_for, open_settings
from linwas.core import netlog
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.network_quality import QualityCard
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.jobs import Job as _Job
from linwas.ui.widgets.jobs import Jobs as _Jobs


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkPage", text)


# Açık durumdaki simge kutusunun rengi (kenar çubuğundaki Wi-Fi & Bluetooth ile aynı)
_ON_TILE = "tile:#007aff"


# --- Ortak parçalar ---


def quality_text(quality: str) -> str:
    return {
        "excellent": tr("Excellent"),
        "good": tr("Good"),
        "fair": tr("Fair"),
        "weak": tr("Weak"),
    }.get(quality, "")


_QUALITY_BARS = {"excellent": 4, "good": 3, "fair": 2, "weak": 1}


class SignalBars(QWidget):
    """Dört çubuklu sinyal göstergesi; tema vurgu rengiyle, dolu çubuk sayısı kaliteye göre."""

    def __init__(self, quality: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._quality = quality
        self.setFixedSize(22, 16)
        text = quality_text(quality) if quality else tr("Unknown")
        self.setAccessibleName(tr("Signal: {quality}").format(quality=text))
        self.setToolTip(tr("Signal: {quality}").format(quality=text))

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        filled = _QUALITY_BARS.get(self._quality or "", 0)
        color = QColor(icons.color_for("accent"))
        empty = QColor(icons.color_for("secondary"))
        empty.setAlpha(70)
        bar_w, gap = 4, 2
        for i in range(4):
            h = 4 + i * 4
            painter.setBrush(color if i < filled else empty)
            painter.drawRoundedRect(i * (bar_w + gap), self.height() - h, bar_w, h, 1.5, 1.5)
        painter.end()


def _tile(name: str, role: str, size: int, parent: QWidget) -> QLabel:
    lbl = QLabel(parent)
    lbl.setFixedSize(size, size)
    icons.bind(lbl, name, role, size)
    return lbl


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class _StatusCard(Card):
    """Simge kutusu + başlık + açıklama + aç/kapat düğmesi."""

    toggle_clicked = Signal()

    def __init__(self, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        row = QHBoxLayout()
        row.setSpacing(16)
        self._tile = _tile(icon_name, "tile", 48, self)
        row.addWidget(self._tile, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._title = QLabel(tr("Checking…"), self)
        self._title.setObjectName("H2")
        self._title.setWordWrap(True)
        texts.addWidget(self._title)
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("Secondary")
        self._subtitle.setWordWrap(True)
        texts.addWidget(self._subtitle)
        row.addLayout(texts, 1)
        self._toggle = QPushButton("", self)
        self._toggle.setMinimumWidth(110)
        self._toggle.setVisible(False)
        self._toggle.clicked.connect(self.toggle_clicked)
        row.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        self.layout.addLayout(row)

    def show_state(self, title: str, subtitle: str, on: bool | None) -> None:
        """on: True açık, False kapalı, None aç/kapat yok (aygıt bulunamadı)."""
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
        icons.bind(self._tile, self._icon_name, _ON_TILE if on else "tile", 48)
        self._toggle.setVisible(on is not None)
        self._toggle.setEnabled(True)
        self._toggle.setText(tr("Turn off") if on else tr("Turn on"))
        self._toggle.setProperty("primary", on is False)
        _repolish(self._toggle)

    def set_busy(self) -> None:
        self._toggle.setEnabled(False)


class _ListCard(Card):
    """Başlıklı kart içinde ayırıcı çizgili satır listesi; boşsa açıklama metni."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        header = QHBoxLayout()
        heading = QLabel(title, self)
        heading.setObjectName("H2")
        header.addWidget(heading)
        header.addStretch(1)
        self.header = header
        self.layout.addLayout(header)
        self._rows = QVBoxLayout()
        self._rows.setSpacing(0)
        self.layout.addLayout(self._rows)
        self._key: object = None

    def add_header_button(self, button: QPushButton) -> None:
        self.header.addWidget(button)

    def set_rows(self, key: object, build: Callable[[], list[QWidget]], empty_text: str) -> None:
        """key değişmediyse yeniden kurulmaz (otomatik yenilemede titreme olmasın)."""
        if key == self._key:
            return
        self._key = key
        rows = build()
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not rows:
            lbl = QLabel(empty_text, self)
            lbl.setObjectName("Secondary")
            lbl.setWordWrap(True)
            self._rows.addWidget(lbl)
            return
        for i, row in enumerate(rows):
            if i:
                sep = QFrame(self)
                sep.setObjectName("Separator")
                sep.setFixedHeight(1)
                self._rows.addWidget(sep)
            self._rows.addWidget(row)

    def reset(self) -> None:
        self._key = None


class _Row(QWidget):
    """Liste satırı: öndeki simge, başlık + açıklama, sağda düğmeler."""

    def __init__(
        self, leading: QWidget, title: str, subtitle: str, bold: bool, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardRow")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 10, 0, 10)
        self._row.setSpacing(12)
        leading.setParent(self)
        self._row.addWidget(leading, 0, Qt.AlignmentFlag.AlignVCenter)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        name = QLabel(title, self)
        if bold:
            font = name.font()
            font.setBold(True)
            name.setFont(font)
        texts.addWidget(name)
        if subtitle:
            sub = QLabel(subtitle, self)
            sub.setObjectName("Secondary")
            texts.addWidget(sub)
        self._row.addLayout(texts, 1)
        self.buttons: list[QPushButton] = []

    def add_trailing(self, widget: QWidget) -> None:
        self._row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_button(self, text: str, slot: Callable[[], None], primary: bool = False) -> None:
        btn = QPushButton(text, self)
        btn.setProperty("primary", primary)
        btn.clicked.connect(slot)
        self._row.addWidget(btn)
        self.buttons.append(btn)


def _settings_button(item_id: str, text: str, parent: QWidget) -> QPushButton:
    desktop = detect_desktop(os.environ).value
    btn = QPushButton(text, parent)
    btn.setEnabled(command_for(item_id, desktop) is not None)
    btn.clicked.connect(lambda: open_settings(item_id, desktop))
    return btn


def _confirm_forget(parent: QWidget, name: str, text: str) -> bool:
    answer = QMessageBox.question(
        parent,
        tr("Forget {name}?").format(name=name),
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    return answer == QMessageBox.StandardButton.Yes


def _show_error(parent: QWidget, title: str, text: str, details: str) -> None:
    box = QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok, parent)
    if details:
        box.setDetailedText(details)
    box.exec()


def _scrolling(content: QWidget, parent: QWidget) -> QScrollArea:
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


# --- Şifre penceresi ---


class _PasswordDialog(QDialog):
    """Şifre (ve gizli ağda ağ adı) sorar; "Şifreyi göster" kutusu vardır."""

    def __init__(self, ssid: str, parent: QWidget | None = None, hidden: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            tr("Connect to a hidden network")
            if hidden
            else tr("Connect to {ssid}").format(ssid=ssid)
        )
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        self._ssid_field = QLineEdit(ssid, self)
        if hidden:
            layout.addWidget(QLabel(tr("Network name:"), self))
            layout.addWidget(self._ssid_field)
        layout.addWidget(
            QLabel(tr("Password (leave empty for an open network):") if hidden else tr("Password:"))
        )
        self._field = QLineEdit(self)
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        self._field.returnPressed.connect(self.accept)
        layout.addWidget(self._field)
        show = QCheckBox(tr("Show password"), self)
        show.toggled.connect(
            lambda on: self._field.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(show)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Connect"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        (self._ssid_field if hidden else self._field).setFocus()

    @property
    def ssid(self) -> str:
        return self._ssid_field.text().strip()

    @property
    def password(self) -> str:
        return self._field.text()


# --- Wi-Fi sekmesi ---


def _security_text(net: WifiNetwork) -> str:
    if not net.security:
        return tr("Open network, not secured")
    return tr("Secured ({kind})").format(kind=net.security.split()[0])


def detail_rows(details: WifiDetails) -> list[tuple[str, str]]:
    """Bağlantı ayrıntıları kartının (etiket, değer) satırları; boş değerler atlanır."""
    if details.band and details.channel:
        band = tr("{band} · channel {channel}").format(band=details.band, channel=details.channel)
    elif details.band:
        band = details.band
    elif details.channel:
        band = tr("Channel {channel}").format(channel=details.channel)
    else:
        band = ""
    rows = [
        (tr("IP address"), details.ip),
        (tr("Gateway"), details.gateway),
        (tr("DNS servers"), ", ".join(details.dns)),
        (tr("Hardware address (MAC)"), details.mac),
        (tr("Access point (BSSID)"), details.bssid),
        (tr("Band"), band),
        (tr("Link speed"), f"{details.rate} Mbit/s" if details.rate else ""),
        (tr("Security"), details.security or tr("Open network, not secured")),
    ]
    return [(label, value) for label, value in rows if value]


class _DetailsCard(Card):
    """Bağlı ağın ayrıntıları: iki sütunlu ızgara; IP adresini ya da hepsini panoya kopyalar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        header = QHBoxLayout()
        heading = QLabel(tr("Connection details"), self)
        heading.setObjectName("H2")
        header.addWidget(heading)
        header.addStretch(1)
        self._copy_ip = QPushButton(tr("Copy IP address"), self)
        self._copy_ip.clicked.connect(lambda: self._copy(self._ip, self._copy_ip))
        header.addWidget(self._copy_ip)
        self._copy_all = QPushButton(tr("Copy all"), self)
        self._copy_all.clicked.connect(lambda: self._copy(self._all_text(), self._copy_all))
        header.addWidget(self._copy_all)
        self.layout.addLayout(header)
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(24)
        self._grid.setVerticalSpacing(0)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self.layout.addLayout(self._grid)
        self._rows: list[tuple[str, str]] = []
        self._ip = ""
        self._restore = QTimer(self)
        self._restore.setSingleShot(True)
        self._restore.setInterval(2000)
        self._restore.timeout.connect(self._reset_labels)

    @property
    def rows(self) -> list[tuple[str, str]]:
        return list(self._rows)

    def show_details(self, details: WifiDetails) -> None:
        """Satırlar değişmediyse yeniden kurulmaz (otomatik yenilemede titreme olmasın)."""
        rows = detail_rows(details)
        self._ip = details.ip
        self._copy_ip.setVisible(bool(details.ip))
        if rows == self._rows:
            return
        self._rows = rows
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, (label, value) in enumerate(rows):
            row, col = divmod(index, 2)
            name = QLabel(label, self)
            name.setObjectName("Secondary")
            text = QLabel(value, self)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.setContentsMargins(0, 0, 0, 10)
            self._grid.addWidget(name, row * 2, col)
            self._grid.addWidget(text, row * 2 + 1, col)

    def _all_text(self) -> str:
        return "\n".join(f"{label}: {value}" for label, value in self._rows)

    def _copy(self, text: str, button: QPushButton) -> None:
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        button.setText(tr("Copied"))
        self._restore.start()

    def _reset_labels(self) -> None:
        self._copy_ip.setText(tr("Copy IP address"))
        self._copy_all.setText(tr("Copy all"))


class _WifiTab(QWidget):
    ai_help_requested = Signal(str, str)  # bağlantı testi sonucu → asistana sor

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._jobs = _Jobs()
        self._loading: _Job | None = None
        self._status: WifiStatus | None = None
        self._busy = False

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        self._status_card = _StatusCard("network", content)
        self._status_card.toggle_clicked.connect(self._toggle_wifi)
        layout.addWidget(self._status_card)

        self._details_card = _DetailsCard(content)
        self._details_card.setVisible(False)
        layout.addWidget(self._details_card)

        self._quality = QualityCard(content)
        self._quality.ai_help_requested.connect(self.ai_help_requested)
        layout.addWidget(self._quality)

        self._list_card = _ListCard(tr("Networks"), content)
        hidden_btn = QPushButton(tr("Hidden network…"), self._list_card)
        hidden_btn.setToolTip(tr("Connect to a network that does not show its name"))
        hidden_btn.clicked.connect(self._connect_hidden)
        self._list_card.add_header_button(hidden_btn)
        self._refresh_btn = QPushButton(tr("Refresh"), self._list_card)
        icons.bind(self._refresh_btn, "refresh", "normal", 16)
        self._refresh_btn.clicked.connect(lambda: self._load(rescan=True))
        self._list_card.add_header_button(self._refresh_btn)
        layout.addWidget(self._list_card)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(_settings_button("wifi", tr("More Wi-Fi settings"), content))
        layout.addLayout(footer)
        layout.addStretch(1)

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(_scrolling(content, self))

        # Otomatik yenileme (yalnızca sayfa görünürken; tarama yapmaz)
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._auto_refresh)
        self._load()

    def _auto_refresh(self) -> None:
        if self.isVisible() and not self._busy:
            self._load()

    def _load(self, rescan: bool = False) -> None:
        if self._loading is not None:
            return
        if rescan:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText(tr("Searching…"))

        def fetch() -> tuple[WifiStatus, list[WifiNetwork], WifiDetails | None]:
            status = network.wifi_status()
            return status, network.wifi_list(rescan=rescan), network.wifi_details(status)

        self._loading = self._jobs.run(fetch, self._on_loaded)

    def _on_loaded(self, result: object) -> None:
        self._loading = None
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText(tr("Refresh"))
        if not isinstance(result, tuple):
            return
        status, nets, details = result
        self._status = status
        self._show_status(status)
        self._show_details(details)
        self._quality.set_connection(status.connected, details.gateway if details else "")
        self._show_networks(nets)

    def _show_status(self, status: WifiStatus) -> None:
        if not status.device:
            self._status_card.show_state(
                tr("No Wi-Fi adapter found"),
                tr("Your Wi-Fi card may need a driver. Open the Drivers page to check."),
                None,
            )
        elif not status.enabled:
            self._status_card.show_state(
                tr("Wi-Fi is off"), tr("Turn it on to see networks nearby."), False
            )
        elif status.connected:
            details = [
                tr("Signal: {quality}").format(
                    quality=quality_text(network.signal_quality(status.signal))
                )
            ]
            if status.ip:
                details.append(tr("IP address {ip}").format(ip=status.ip))
            self._status_card.show_state(
                tr("Connected to {ssid}").format(ssid=status.ssid), " · ".join(details), True
            )
        else:
            self._status_card.show_state(
                tr("Not connected"), tr("Choose a network below to connect."), True
            )
        self._list_card.setVisible(bool(status.device) and status.enabled)

    def _show_details(self, details: WifiDetails | None) -> None:
        self._details_card.setVisible(details is not None)
        if details is not None:
            self._details_card.show_details(details)

    def _show_networks(self, nets: list[WifiNetwork]) -> None:
        key = [(n.ssid, n.active, n.saved, n.quality, n.security) for n in nets]
        self._list_card.set_rows(
            key,
            lambda: [self._row(net) for net in nets],
            tr("No networks found. Move closer to the router and press Refresh."),
        )

    def _row(self, net: WifiNetwork) -> _Row:
        if net.active:
            subtitle = tr("Connected")
        elif net.saved:
            subtitle = tr("Saved") + " · " + _security_text(net)
        else:
            subtitle = _security_text(net)
        row = _Row(
            SignalBars(net.quality),
            net.ssid or tr("(Hidden network)"),
            subtitle,
            net.active,
            self._list_card,
        )
        if net.security:
            row.add_trailing(_tile("lock", "secondary", 16, row))
        if net.active:
            row.add_button(tr("Disconnect"), self._disconnect)
        else:
            row.add_button(tr("Connect"), lambda: self._connect(net, row))
        if net.saved:
            row.add_button(tr("Forget"), lambda: self._forget(net.ssid))
        return row

    # --- İşlemler ---

    def _start(self, fn: Callable[[], object], slot: Callable[[object], None]) -> None:
        self._busy = True
        self._list_card.setEnabled(False)

        def finished(result: object) -> None:
            self._busy = False
            self._list_card.setEnabled(True)
            self._list_card.reset()
            slot(result)
            self._load()

        self._jobs.run(fn, finished)

    def _toggle_wifi(self) -> None:
        enabled = self._status.enabled if self._status else True
        ssid = self._status.ssid if self._status else ""
        self._status_card.set_busy()

        def work() -> bool:
            if enabled and ssid:  # kullanıcı kapatıyor: kopma sayılmasın
                netquality.note_user_action(netlog.KIND_WIFI, ssid)
            return network.wifi_set_enabled(not enabled)

        self._start(work, lambda _r: None)

    def _connect(self, net: WifiNetwork, row: _Row, password: str = "") -> None:
        if net.security and not net.saved and not password:
            dlg = _PasswordDialog(net.ssid, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            password = dlg.password
        if row.buttons:
            row.buttons[0].setText(tr("Connecting…"))

        def done(result: object) -> None:
            ok, msg = result if isinstance(result, tuple) else (False, "")
            if ok:
                return
            if net.saved and net.security and not password:
                # Kayıtlı şifre değişmiş olabilir: yeni şifreyi sor
                dlg = _PasswordDialog(net.ssid, self)
                if dlg.exec() == QDialog.DialogCode.Accepted and dlg.password:
                    new_password = dlg.password
                    self._start(
                        lambda: network.wifi_connect(net.ssid, new_password),
                        lambda r: self._connect_done(r, net.ssid),
                    )
                return
            self._connect_done((ok, msg), net.ssid)

        self._start(
            lambda: network.wifi_connect(net.ssid, password, saved=net.saved),
            done,
        )

    def _connect_done(self, result: object, ssid: str) -> None:
        ok, msg = result if isinstance(result, tuple) else (False, "")
        if not ok:
            _show_error(
                self,
                tr("Connection failed"),
                tr("Could not connect to {ssid}. Check the password and try again.").format(
                    ssid=ssid
                ),
                msg,
            )

    def _connect_hidden(self) -> None:
        dlg = _PasswordDialog("", self, hidden=True)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.ssid:
            return
        ssid, password = dlg.ssid, dlg.password
        self._start(
            lambda: network.wifi_connect(ssid, password, hidden=True),
            lambda r: self._connect_done(r, ssid),
        )

    def _disconnect(self) -> None:
        ssid = self._status.ssid if self._status else ""

        def work() -> bool:
            netquality.note_user_action(netlog.KIND_WIFI, ssid)  # kopma sayılmasın
            return network.wifi_disconnect()

        self._start(work, lambda _r: None)

    def _forget(self, ssid: str) -> None:
        if _confirm_forget(
            self, ssid, tr("You will need the password to connect to this network again.")
        ):
            active = self._status.ssid if self._status else ""

            def work() -> bool:
                if ssid == active:  # bağlı ağı unutmak bağlantıyı da keser
                    netquality.note_user_action(netlog.KIND_WIFI, ssid)
                return network.wifi_forget(ssid)

            self._start(work, lambda _r: None)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.start()
        super().showEvent(event)  # type: ignore[misc]

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[misc]


# --- Bluetooth sekmesi ---


# BlueZ "Icon" alanı → simge adı (theme/icon_data.py)
_BT_ICONS = {
    "phone": "phone",
    "audio-headset": "headphones",
    "audio-headphones": "headphones",
    "audio-card": "sound",
    "input-mouse": "mouse",
    "input-tablet": "mouse",
    "input-keyboard": "keyboard",
    "input-gaming": "gamepad",
    "computer": "laptop",
    "printer": "printer",
    "camera-photo": "camera",
    "camera-video": "camera",
}

_SCAN_SECONDS = 10


class _BtTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._jobs = _Jobs()
        self._loading: _Job | None = None
        self._state = ""
        self._busy = False
        self._scanning = False

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        self._status_card = _StatusCard("bluetooth", content)
        self._status_card.toggle_clicked.connect(self._toggle_bt)
        layout.addWidget(self._status_card)

        self._mine = _ListCard(tr("My devices"), content)
        layout.addWidget(self._mine)

        self._nearby = _ListCard(tr("Other devices"), content)
        self._scan_btn = QPushButton(tr("Search for devices"), self._nearby)
        self._scan_btn.setProperty("primary", True)
        self._scan_btn.clicked.connect(self._scan)
        self._nearby.add_header_button(self._scan_btn)
        hint = QLabel(
            tr("Put the device in pairing mode first (see its manual), then search."),
            self._nearby,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        self._nearby.layout.insertWidget(1, hint)
        layout.addWidget(self._nearby)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(_settings_button("bluetooth", tr("More Bluetooth settings"), content))
        layout.addLayout(footer)
        layout.addStretch(1)

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(_scrolling(content, self))

        # Bağlantı ve pil durumu değişsin diye yenile (tarama yapmaz)
        self._timer = QTimer(self)
        self._timer.setInterval(10000)
        self._timer.timeout.connect(self._auto_refresh)
        self._load()

    def _auto_refresh(self) -> None:
        if self.isVisible() and not self._busy and not self._scanning:
            self._load()

    def _load(self, scan: bool = False) -> None:
        if self._loading is not None:
            return

        def fetch() -> tuple[str, list[BluetoothDevice]]:
            state = network.bluetooth_state()
            if state != "on":
                return state, []
            devices = network.bluetooth_scan(_SCAN_SECONDS) if scan else None
            return state, devices if devices is not None else network.bluetooth_list_devices()

        self._loading = self._jobs.run(fetch, self._on_loaded)

    def _on_loaded(self, result: object) -> None:
        self._loading = None
        if self._scanning:
            self._scanning = False
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText(tr("Search for devices"))
        if not isinstance(result, tuple):
            return
        state, devices = result
        self._state = state
        self._show_state(state)
        on = state == "on"
        self._mine.setVisible(on)
        self._nearby.setVisible(on)
        if not on:
            return
        paired = [d for d in devices if d.paired]
        others = [d for d in devices if not d.paired]
        self._mine.set_rows(
            [(d.mac, d.name, d.connected, d.battery) for d in paired],
            lambda: [self._row(d) for d in paired],
            tr("No paired devices yet. Search for devices below to add one."),
        )
        self._nearby.set_rows(
            [(d.mac, d.name, d.quality) for d in others],
            lambda: [self._row(d) for d in others],
            tr("No new devices found yet."),
        )

    def _show_state(self, state: str) -> None:
        if state == "missing":
            self._status_card.show_state(
                tr("No Bluetooth adapter found"),
                tr("This computer has no Bluetooth, or it needs a driver. Check the Drivers page."),
                None,
            )
        elif state == "blocked":
            self._status_card.show_state(
                tr("Bluetooth is turned off by a switch"),
                tr(
                    "Turn it on with the wireless switch or key (often Fn + a key with an antenna)."
                ),
                None,
            )
        elif state == "off":
            self._status_card.show_state(
                tr("Bluetooth is off"), tr("Turn it on to use headphones, mice and phones."), False
            )
        else:
            self._status_card.show_state(
                tr("Bluetooth is on"), tr("Paired devices connect automatically when nearby."), True
            )

    def _row(self, dev: BluetoothDevice) -> _Row:
        if dev.connected:
            subtitle = tr("Connected")
            if dev.battery is not None:
                subtitle += " · " + tr("battery %{n}").format(n=dev.battery)
        elif dev.paired:
            subtitle = tr("Paired, not connected")
        elif dev.quality:
            subtitle = tr("Signal: {quality}").format(quality=quality_text(dev.quality))
        else:
            subtitle = tr("Ready to pair")
        icon_name = _BT_ICONS.get(dev.icon, "bluetooth")
        row = _Row(
            _tile(icon_name, _ON_TILE if dev.connected else "tile", 36, self),
            dev.name or dev.mac,
            subtitle,
            dev.connected,
            self,
        )
        if dev.connected:
            row.add_button(tr("Disconnect"), lambda: self._disconnect(dev.mac))
        elif dev.paired:
            row.add_button(tr("Connect"), lambda: self._connect(dev, row))
        else:
            row.add_button(tr("Pair"), lambda: self._connect(dev, row), primary=True)
        if dev.paired:
            row.add_button(tr("Forget"), lambda: self._forget(dev))
        return row

    # --- İşlemler ---

    def _start(self, fn: Callable[[], object], slot: Callable[[object], None]) -> None:
        self._busy = True
        self._mine.setEnabled(False)
        self._nearby.setEnabled(False)

        def finished(result: object) -> None:
            self._busy = False
            self._mine.setEnabled(True)
            self._nearby.setEnabled(True)
            self._mine.reset()
            self._nearby.reset()
            slot(result)
            self._load()

        self._jobs.run(fn, finished)

    def _scan(self) -> None:
        if self._loading is not None:
            return
        self._scanning = True
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText(tr("Searching…"))
        self._load(scan=True)

    def _toggle_bt(self) -> None:
        on = self._state == "on"
        self._status_card.set_busy()
        self._start(lambda: network.bluetooth_set_enabled(not on), lambda _r: None)

    def _connect(self, dev: BluetoothDevice, row: _Row) -> None:
        row.buttons[0].setText(tr("Connecting…") if dev.paired else tr("Pairing…"))

        def done(result: object) -> None:
            ok, msg = result if isinstance(result, tuple) else (False, "")
            if not ok:
                _show_error(
                    self,
                    tr("Connection failed"),
                    tr(
                        "Could not connect to {name}. Make sure it is on and nearby. If it asks "
                        "for a code, use More Bluetooth settings."
                    ).format(name=dev.name or dev.mac),
                    msg,
                )

        self._start(lambda: network.bluetooth_connect(dev.mac), done)

    def _disconnect(self, mac: str) -> None:
        self._start(lambda: network.bluetooth_disconnect(mac), lambda _r: None)

    def _forget(self, dev: BluetoothDevice) -> None:
        if _confirm_forget(
            self, dev.name or dev.mac, tr("You will need to pair this device again to use it.")
        ):
            self._start(lambda: network.bluetooth_forget(dev.mac), lambda _r: None)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.start()
        super().showEvent(event)  # type: ignore[misc]

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[misc]


# --- Ana sayfa ---


class NetworkPage(BasePage):
    """Wi-Fi ve Bluetooth sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 12)
        layout.setSpacing(12)

        title = QLabel(tr("Wi-Fi & Bluetooth"), self)
        title.setObjectName("H1")
        layout.addWidget(title)

        tabs = QTabWidget(self)
        wifi = _WifiTab(tabs)
        wifi.ai_help_requested.connect(self.ai_help_requested)
        tabs.addTab(wifi, tr("Wi-Fi"))
        tabs.addTab(_BtTab(tabs), tr("Bluetooth"))
        layout.addWidget(tabs, 1)
