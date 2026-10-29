# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
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
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import btaudio, btfile, netquality, network
from linwas.backend.desktop import detect_desktop
from linwas.backend.network import (
    BluetoothAdapter,
    BluetoothDevice,
    HotspotInfo,
    WifiDetails,
    WifiNetwork,
    WifiProfile,
    WifiStatus,
)
from linwas.backend.settings_launcher import command_for, open_settings
from linwas.core import netadvice, netlog
from linwas.ui import icons
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.network_bluetooth import BluetoothDeviceDialog, ComputerCard
from linwas.ui.pages.network_hotspot import HotspotCard, HotspotDialog
from linwas.ui.pages.network_profile_dialog import NetworkSettingsDialog
from linwas.ui.pages.network_quality import QualityCard
from linwas.ui.widgets.advice_card import AdviceCard
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.details_toggle import DetailsToggle
from linwas.ui.widgets.jobs import Job as _Job
from linwas.ui.widgets.jobs import Jobs as _Jobs
from linwas.ui.widgets.layout_utils import clear_layout


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


def _more_button(parent: QWidget) -> QToolButton:
    """Listenin altındaki "N tanesini göster" düğmesi (kartın "Ayrıntılar" düğmesiyle aynı stil)."""
    btn = QToolButton(parent)
    btn.setObjectName("DetailsToggle")
    btn.setAutoRaise(True)
    btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    icons.bind(btn, "chevron_right", "secondary", 14)
    btn.setVisible(False)
    return btn


def _set_more_button(btn: QToolButton, count: int, expanded: bool, show: str, hide: str) -> None:
    """Gizlenen kayıt yoksa düğme görünmez; açıkken "gizle", kapalıyken "N tanesini göster"."""
    btn.setVisible(count > 0)
    btn.setText(hide if expanded else show.format(n=count))
    icons.bind(btn, "chevron_down" if expanded else "chevron_right", "secondary", 14)


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

    def show_state(
        self, title: str, subtitle: str, on: bool | None, highlight: bool | None = None
    ) -> None:
        """on: True açık, False kapalı, None aç/kapat yok (aygıt bulunamadı, hotspot açık).

        `highlight` simge kutusunu vurgular; verilmezse `on` değerini izler.
        """
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
        lit = bool(on) if highlight is None else highlight
        icons.bind(self._tile, self._icon_name, _ON_TILE if lit else "tile", 48)
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

    def add_footer(self, widget: QWidget) -> None:
        """Satırların altına (ör. "N zayıf ağı göster" düğmesi)."""
        self.layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignLeft)

    def set_rows(self, key: object, build: Callable[[], list[QWidget]], empty_text: str) -> None:
        """key değişmediyse yeniden kurulmaz (otomatik yenilemede titreme olmasın)."""
        if key == self._key:
            return
        self._key = key
        rows = build()
        clear_layout(self._rows)
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


def is_weak_unknown(net: WifiNetwork) -> bool:
    """Çok zayıf sinyalli ve ne bağlı ne kayıtlı: gürültü sayılır, varsayılan gizlenir."""
    return net.quality == "weak" and not net.active and not net.saved


def _security_text(net: WifiNetwork) -> str:
    return security_label(net.security)


def security_label(security: str) -> str:
    """Güvenlik bilgisi sade dille: boş = açık ağ; "WPA2 WPA3" → "Şifreli (WPA2)"."""
    if not security:
        return tr("Open network, not secured")
    return tr("Secured ({kind})").format(kind=security.split()[0])


def basic_rows(details: WifiDetails) -> list[tuple[str, str]]:
    """Varsayılan görünen satırlar (süzülmüş): günlük kullanıcının işine yarayan üç bilgi."""
    speed = " · ".join(
        part for part in (f"{details.rate} Mbit/s" if details.rate else "", details.band) if part
    )
    rows = [
        (tr("Speed"), speed),
        (tr("IP address"), details.ip),
        (tr("Security"), security_label(details.security)),
    ]
    return [(label, value) for label, value in rows if value]


def advanced_rows(details: WifiDetails) -> list[tuple[str, str]]:
    """ "Gelişmiş ayrıntılar" arkasındaki teknik satırlar."""
    rows = [
        (tr("Gateway"), details.gateway),
        (tr("DNS servers"), ", ".join(details.dns)),
        (tr("Channel"), str(details.channel) if details.channel else ""),
        (tr("Hardware address (MAC)"), details.mac),
        (tr("Access point (BSSID)"), details.bssid),
    ]
    return [(label, value) for label, value in rows if value]


def detail_rows(details: WifiDetails) -> list[tuple[str, str]]:
    """Tüm satırlar (\"Tümünü kopyala\" ve destek için); ekranda yalnızca temel olanlar görünür."""
    return basic_rows(details) + advanced_rows(details)


def _fill_grid(grid: QGridLayout, rows: list[tuple[str, str]], parent: QWidget) -> None:
    """İki sütunlu ızgarayı (etiket üstte, değer altta) yeniden kurar."""
    clear_layout(grid)
    for index, (label, value) in enumerate(rows):
        row, col = divmod(index, 2)
        name = QLabel(label, parent)
        name.setObjectName("Secondary")
        text = QLabel(value, parent)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setContentsMargins(0, 0, 0, 10)
        grid.addWidget(name, row * 2, col)
        grid.addWidget(text, row * 2 + 1, col)


def _new_grid() -> QGridLayout:
    grid = QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(0)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    return grid


class _DetailsCard(Card):
    """Bağlı ağın bilgileri: önce temel satırlar; teknik olanlar "Gelişmiş ayrıntılar" arkasında."""

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

        self._basic_grid = _new_grid()
        self.layout.addLayout(self._basic_grid)

        self._toggle = DetailsToggle(tr("Advanced details"), self)
        self.layout.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self._advanced = QWidget(self)
        self._advanced.setObjectName("DetailsBox")
        # Genel "QWidget" zemini kartın içinde şeritler gibi görünmesin
        self._advanced.setStyleSheet("QWidget#DetailsBox { background: transparent; }")
        self._advanced_grid = _new_grid()
        self._advanced.setLayout(self._advanced_grid)
        self.layout.addWidget(self._advanced)
        self._toggle.add_target(self._advanced)

        self._basic: list[tuple[str, str]] = []
        self._more: list[tuple[str, str]] = []
        self._ip = ""
        self._restore = QTimer(self)
        self._restore.setSingleShot(True)
        self._restore.setInterval(2000)
        self._restore.timeout.connect(self._reset_labels)

    @property
    def rows(self) -> list[tuple[str, str]]:
        """Varsayılan görünen satırlar."""
        return list(self._basic)

    @property
    def advanced(self) -> list[tuple[str, str]]:
        return list(self._more)

    def show_details(self, details: WifiDetails) -> None:
        """Satırlar değişmediyse yeniden kurulmaz (otomatik yenilemede titreme olmasın)."""
        self._ip = details.ip
        self._copy_ip.setVisible(bool(details.ip))
        basic, more = basic_rows(details), advanced_rows(details)
        if basic != self._basic:
            self._basic = basic
            _fill_grid(self._basic_grid, basic, self)
        if more != self._more:
            self._more = more
            _fill_grid(self._advanced_grid, more, self._advanced)
        self._toggle.setVisible(bool(more))
        if not more:
            self._advanced.setVisible(False)
        else:
            self._advanced.setVisible(self._toggle.isChecked())

    def _all_text(self) -> str:
        return "\n".join(f"{label}: {value}" for label, value in self._basic + self._more)

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
        self._show_weak = False  # çok zayıf (kullanılamaz) ağlar varsayılan gizli
        self._profile_job: _Job | None = None
        self._hotspot_job: _Job | None = None
        self._hotspot: HotspotInfo | None = None  # bu bilgisayar şu an hotspot yayınlıyorsa
        self._nets: list[WifiNetwork] = []

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        self._status_card = _StatusCard("network", content)
        self._status_card.toggle_clicked.connect(self._toggle_wifi)
        layout.addWidget(self._status_card)

        self._advice = AdviceCard(content)
        self._advice.review_requested.connect(self._advice_review)
        self._advice.dismissed.connect(self._advice_dismiss)
        layout.addWidget(self._advice)

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
        self._weak_btn = _more_button(self._list_card)
        self._weak_btn.clicked.connect(self._toggle_weak)
        self._list_card.add_footer(self._weak_btn)
        layout.addWidget(self._list_card)

        self._hotspot_card = HotspotCard(content)
        self._hotspot_card.setVisible(False)
        self._hotspot_card.start_requested.connect(self._hotspot_start)
        self._hotspot_card.stop_requested.connect(self._hotspot_stop)
        layout.addWidget(self._hotspot_card)

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

        def fetch() -> tuple[
            WifiStatus, list[WifiNetwork], WifiDetails | None, HotspotInfo | None, list
        ]:
            status = network.wifi_status()
            hotspot = network.hotspot_info(status)
            if hotspot is not None:  # erişim noktası kipinde ağ taraması/ayrıntı anlamsız
                return status, [], None, hotspot, []
            advice = netadvice.current(netadvice.RULE_WIFI)
            nets = network.wifi_list(rescan=rescan)
            return status, nets, network.wifi_details(status), None, advice

        self._loading = self._jobs.run(fetch, self._on_loaded)

    def _on_loaded(self, result: object) -> None:
        self._loading = None
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText(tr("Refresh"))
        if not isinstance(result, tuple):
            return
        status, nets, details, hotspot, advice = result
        self._status = status
        self._hotspot = hotspot
        self._advice.set_items(advice, lambda a: self._saved_network(a.subject, nets) is not None)
        self._advice.setVisible(bool(advice) and hotspot is None)
        self._show_status(status)
        self._show_details(details)
        self._quality.set_connection(
            status.connected and hotspot is None, details.gateway if details else ""
        )
        self._quality.setVisible(hotspot is None)  # hotspot'ta ölçülecek bir geçit yok
        self._show_networks(nets)
        self._hotspot_card.setVisible(bool(status.device) and status.enabled)
        self._hotspot_card.show_info(hotspot)

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
        elif self._hotspot is not None:
            self._status_card.show_state(
                tr("Hotspot is on"),
                tr("Broadcasting “{ssid}”.").format(ssid=self._hotspot.ssid),
                None,
                highlight=True,
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
        self._list_card.setVisible(bool(status.device) and status.enabled and self._hotspot is None)

    def _show_details(self, details: WifiDetails | None) -> None:
        self._details_card.setVisible(details is not None)
        if details is not None:
            self._details_card.show_details(details)

    def _show_networks(self, nets: list[WifiNetwork]) -> None:
        """Süzülmüş liste: bağlı, kayıtlı ve kullanılabilir ağlar; çok zayıf olanlar gizli."""
        self._nets = nets
        weak = [n for n in nets if is_weak_unknown(n)]
        visible = [n for n in nets if self._show_weak or not is_weak_unknown(n)]
        _set_more_button(
            self._weak_btn,
            len(weak),
            self._show_weak,
            tr("Show {n} weak networks"),
            tr("Hide weak networks"),
        )
        key = [(n.ssid, n.active, n.saved, n.quality, n.security) for n in visible]
        key.append(self._show_weak)  # type: ignore[arg-type]
        empty = (
            tr("Only weak networks were found. Move closer to the router or show them below.")
            if weak and not visible
            else tr("No networks found. Move closer to the router and press Refresh.")
        )
        self._list_card.set_rows(key, lambda: [self._row(net) for net in visible], empty)

    def _toggle_weak(self) -> None:
        self._show_weak = not self._show_weak
        self._list_card.reset()
        self._show_networks(self._nets)

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
            row.add_button(tr("Settings"), lambda: self._open_settings(net))
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

    # --- Hotspot ---

    def _hotspot_start(self) -> None:
        if self._hotspot_job is not None or self._status is None or not self._status.device:
            return
        self._hotspot_card.set_busy()
        self._hotspot_job = self._jobs.run(network.hotspot_defaults, self._on_hotspot_defaults)

    def _on_hotspot_defaults(self, result: object) -> None:
        self._hotspot_job = None
        if not (isinstance(result, tuple) and len(result) == 2) or self._status is None:
            self._hotspot_card.show_info(self._hotspot)
            return
        dlg = HotspotDialog(str(result[0]), str(result[1]), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self._hotspot_card.show_info(self._hotspot)
            return
        ssid, password = dlg.values()
        device = self._status.device
        current = self._status.ssid if self._status.connected else ""

        def work() -> tuple[bool, str]:
            if current:  # bağlı olduğu ağdan ayrılmak kullanıcının tercihi: kopma sayılmasın
                netquality.note_user_action(netlog.KIND_WIFI, current)
            return network.hotspot_start(device, ssid, password)

        self._start(work, self._hotspot_started)

    def _hotspot_started(self, result: object) -> None:
        ok, msg = result if isinstance(result, tuple) else (False, "")
        if not ok:
            _show_error(
                self,
                tr("Hotspot"),
                tr("The hotspot could not be turned on. This Wi-Fi card may not support it."),
                msg,
            )

    def _hotspot_stop(self) -> None:
        hotspot = self._hotspot
        if hotspot is None:
            return
        self._hotspot_card.set_busy()
        self._start(lambda: network.hotspot_stop(hotspot.name), lambda _r: None)

    # --- Öneriler ("Ayarlara bak" ilgili ağın ayar penceresini açar) ---

    @staticmethod
    def _saved_network(name: str, nets: list[WifiNetwork]) -> WifiNetwork | None:
        return next((n for n in nets if n.saved and n.ssid == name), None)

    def _advice_review(self, _rule: str, subject: str) -> None:
        net = self._saved_network(subject, self._nets)
        if net is not None:
            self._open_settings(net)

    def _advice_dismiss(self, rule: str, subject: str) -> None:
        self._jobs.run(lambda: netadvice.dismiss(rule, subject), lambda _r: self._load())

    # --- Ağ ayarları (otomatik bağlan, veri kullanımı, DNS, IP) ---

    def _open_settings(self, net: WifiNetwork) -> None:
        if self._profile_job is not None:
            return
        self._profile_job = self._jobs.run(
            lambda: network.wifi_profile(net.ssid),
            lambda profile: self._on_profile(net, profile),
        )

    def _on_profile(self, net: WifiNetwork, profile: object) -> None:
        self._profile_job = None
        if not isinstance(profile, WifiProfile):
            _show_error(
                self,
                tr("Network settings"),
                tr("This network's settings could not be read."),
                "",
            )
            return
        dlg = NetworkSettingsDialog(profile, net.active, self, secured=bool(net.security))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        change = dlg.change()
        reconnect = net.active and network.reconnect_needed(profile, change)
        self._start(
            lambda: network.wifi_profile_save(net.ssid, change, reconnect),
            self._settings_saved,
        )

    def _settings_saved(self, result: object) -> None:
        ok, msg = result if isinstance(result, tuple) else (False, "")
        if not ok:
            _show_error(
                self,
                tr("Network settings"),
                tr("The settings could not be saved."),
                msg,
            )

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
        self._show_unnamed = False  # adsız (yalnızca adresi olan) cihazlar varsayılan gizli
        self._devices: list[BluetoothDevice] = []

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        self._status_card = _StatusCard("bluetooth", content)
        self._status_card.toggle_clicked.connect(self._toggle_bt)
        layout.addWidget(self._status_card)

        self._advice = AdviceCard(content)
        self._advice.review_requested.connect(self._advice_review)
        self._advice.dismissed.connect(self._advice_dismiss)
        layout.addWidget(self._advice)

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
        self._unnamed_btn = _more_button(self._nearby)
        self._unnamed_btn.clicked.connect(self._toggle_unnamed)
        self._nearby.add_footer(self._unnamed_btn)
        layout.addWidget(self._nearby)

        self._computer = ComputerCard(content)
        self._computer.setVisible(False)
        self._computer.visibility_requested.connect(self._set_visible)
        self._computer.rename_requested.connect(self._rename_computer)
        layout.addWidget(self._computer)

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

        def fetch() -> tuple[str, list[BluetoothDevice], BluetoothAdapter | None, list]:
            state = network.bluetooth_state()
            if state != "on":
                return state, [], None, []
            devices = network.bluetooth_scan(_SCAN_SECONDS) if scan else None
            if devices is None:
                devices = network.bluetooth_list_devices()
            advice = netadvice.current(netadvice.RULE_BT)
            return state, devices, network.bluetooth_adapter_info(), advice

        self._loading = self._jobs.run(fetch, self._on_loaded)

    def _on_loaded(self, result: object) -> None:
        self._loading = None
        if self._scanning:
            self._scanning = False
            self._scan_btn.setEnabled(True)
            self._scan_btn.setText(tr("Search for devices"))
        if not isinstance(result, tuple):
            return
        state, devices, adapter, advice = result
        self._state = state
        self._show_state(state)
        on = state == "on"
        self._mine.setVisible(on)
        self._nearby.setVisible(on)
        self._computer.setVisible(on and adapter is not None)
        self._advice.set_items(
            advice, lambda a: self._paired_device(a.subject, devices) is not None
        )
        if not on:
            return
        self._computer.show_adapter(adapter)
        self._devices = devices
        self._show_devices()

    def _show_devices(self) -> None:
        """Eşleşmişler her zaman; yeni cihazlarda adsız olanlar ("AA-BB-…") varsayılan gizli."""
        paired = [d for d in self._devices if d.paired]
        others = [d for d in self._devices if not d.paired]
        unnamed = [d for d in others if network.is_unnamed_device(d)]
        shown = [d for d in others if self._show_unnamed or not network.is_unnamed_device(d)]
        _set_more_button(
            self._unnamed_btn,
            len(unnamed),
            self._show_unnamed,
            tr("Show {n} unnamed devices"),
            tr("Hide unnamed devices"),
        )
        self._mine.set_rows(
            [(d.mac, d.name, d.connected, d.battery, d.trusted) for d in paired],
            lambda: [self._row(d) for d in paired],
            tr("No paired devices yet. Search for devices below to add one."),
        )
        self._nearby.set_rows(
            [(d.mac, d.name, d.quality, self._show_unnamed) for d in shown],
            lambda: [self._row(d) for d in shown],
            tr("No new devices found yet."),
        )

    def _toggle_unnamed(self) -> None:
        self._show_unnamed = not self._show_unnamed
        self._nearby.reset()
        self._show_devices()

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
        if dev.paired and not dev.trusted:  # yalnızca istisna gösterilir (süzülmüş görünüm)
            subtitle += " · " + tr("won't connect by itself")
        icon_name = _BT_ICONS.get(dev.icon, "bluetooth")
        row = _Row(
            _tile(icon_name, _ON_TILE if dev.connected else "tile", 36, self),
            dev.name or dev.mac,
            subtitle,
            dev.connected,
            self,
        )
        if dev.connected:
            row.add_button(tr("Disconnect"), lambda: self._disconnect(dev))
        elif dev.paired:
            row.add_button(tr("Connect"), lambda: self._connect(dev, row))
        else:
            row.add_button(tr("Pair"), lambda: self._connect(dev, row), primary=True)
        if dev.paired:
            if dev.connected and btfile.can_receive(dev.icon):
                row.add_button(tr("Send file…"), lambda: self._send_file(dev))
            row.add_button(tr("Settings"), lambda: self._open_settings(dev))
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
        connected = [d for d in self._devices if d.connected]

        def work() -> bool:
            if on:  # kullanıcı kapatıyor: cihazların kopması kopma sayılmasın
                for dev in connected:
                    netquality.note_user_action(netlog.KIND_BT, dev.name, dev.mac)
            return network.bluetooth_set_enabled(not on)

        self._start(work, lambda _r: None)

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

    def _disconnect(self, dev: BluetoothDevice) -> None:
        def work() -> tuple[bool, str]:
            netquality.note_user_action(netlog.KIND_BT, dev.name, dev.mac)  # kopma sayılmasın
            return network.bluetooth_disconnect(dev.mac)

        self._start(work, lambda _r: None)

    def _forget(self, dev: BluetoothDevice) -> None:
        if _confirm_forget(
            self, dev.name or dev.mac, tr("You will need to pair this device again to use it.")
        ):

            def work() -> bool:
                netquality.note_user_action(netlog.KIND_BT, dev.name, dev.mac)
                return network.bluetooth_forget(dev.mac)

            self._start(work, lambda _r: None)

    # --- Öneriler ("Ayarlara bak" ilgili cihazın ayar penceresini açar) ---

    @staticmethod
    def _paired_device(mac: str, devices: list[BluetoothDevice]) -> BluetoothDevice | None:
        return next((d for d in devices if d.paired and d.mac == mac), None)

    def _advice_review(self, _rule: str, subject: str) -> None:
        dev = self._paired_device(subject, self._devices)
        if dev is not None:
            self._open_settings(dev)

    def _advice_dismiss(self, rule: str, subject: str) -> None:
        self._jobs.run(lambda: netadvice.dismiss(rule, subject), lambda _r: self._load())

    # --- Dosya gönderme (masaüstünün kendi Bluetooth aracıyla) ---

    def _send_file(self, dev: BluetoothDevice) -> None:
        name = dev.name or dev.mac
        if btfile.available_tool() is None:
            _show_error(
                self,
                tr("Send file"),
                tr(
                    "Sending files needs a Bluetooth file tool: “bluetooth-sendto” (GNOME "
                    "Bluetooth) or “blueman-sendto” (Blueman). Install one of them and try again."
                ),
                "",
            )
            return
        paths, _filter = QFileDialog.getOpenFileNames(
            self, tr("Choose files to send to {name}").format(name=name)
        )
        if not paths:
            return
        ok, msg = btfile.send(dev.mac, paths)
        if not ok:
            _show_error(self, tr("Send file"), tr("The files could not be sent."), msg)

    # --- Bu bilgisayarın görünürlüğü ve adı ---

    def _set_visible(self, visible: bool) -> None:
        self._computer.set_busy()
        self._start(lambda: network.bluetooth_set_visible(visible), self._visibility_done)

    def _visibility_done(self, result: object) -> None:
        if result is not True:
            _show_error(
                self,
                tr("Visibility"),
                tr("The visibility of this computer could not be changed."),
                "",
            )

    def _rename_computer(self) -> None:
        info = self._computer.info
        if info is None:
            return
        text, accepted = QInputDialog.getText(
            self,
            tr("Computer name"),
            tr("Name other devices see (leave empty to use the default):"),
            QLineEdit.EchoMode.Normal,
            info.alias,
        )
        if not accepted:
            return
        try:
            name = network.validate_alias(text)
        except network.AliasError:
            _show_error(self, tr("Computer name"), tr("This name is not valid."), "")
            return
        self._computer.set_busy()
        self._start(lambda: network.bluetooth_set_computer_name(name), self._rename_done)

    def _rename_done(self, result: object) -> None:
        ok, msg = result if isinstance(result, tuple) else (False, "")
        if not ok:
            _show_error(self, tr("Computer name"), tr("The name could not be changed."), str(msg))

    # --- Cihaz ayarları (ad, otomatik bağlan, ses) ---

    def _open_settings(self, dev: BluetoothDevice) -> None:
        dlg = BluetoothDeviceDialog(dev, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        change = dlg.change()
        if (
            change.name is None
            and change.trusted is None
            and change.audio_mode is None
            and not change.make_output
        ):
            return

        def work() -> list[str]:
            failures: list[str] = []
            if change.name is not None:
                ok, msg = network.bluetooth_rename(dev.mac, change.name)
                if not ok:
                    failures.append(msg or "rename")
            if change.trusted is not None and not network.bluetooth_set_trusted(
                dev.mac, change.trusted
            ):
                failures.append("trust")
            failures += btaudio.apply(dev.mac, change.audio_mode, change.make_output)
            return failures

        self._start(work, self._settings_saved)

    def _settings_saved(self, result: object) -> None:
        if isinstance(result, list) and not result:
            return
        _show_error(
            self,
            tr("Device settings"),
            tr("The settings could not be saved."),
            "\n".join(result) if isinstance(result, list) else "",
        )

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
