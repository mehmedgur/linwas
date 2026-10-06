"""Wi-Fi ve Bluetooth sayfası."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from linwas.backend.network import (
    BluetoothDevice,
    WifiNetwork,
    WifiStatus,
    bluetooth_connect,
    bluetooth_disconnect,
    bluetooth_enabled,
    bluetooth_forget,
    bluetooth_list_devices,
    bluetooth_scan,
    bluetooth_set_enabled,
    wifi_connect,
    wifi_disconnect,
    wifi_forget,
    wifi_list,
    wifi_set_enabled,
    wifi_status,
)
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("NetworkPage", text)


# --- Workers ---

class _WifiWorker(QThread):
    status_ready = Signal(object)   # WifiStatus
    networks_ready = Signal(object) # list[WifiNetwork]

    def run(self) -> None:
        try:
            self.status_ready.emit(wifi_status())
            self.networks_ready.emit(wifi_list())
        except Exception:
            self.status_ready.emit(None)
            self.networks_ready.emit([])


class _BtWorker(QThread):
    done = Signal(object)  # list[BluetoothDevice]
    scanning = False

    def __init__(self, scan: bool = False) -> None:
        super().__init__()
        self._scan = scan

    def run(self) -> None:
        try:
            if self._scan:
                self.done.emit(bluetooth_scan())
            else:
                self.done.emit(bluetooth_list_devices())
        except Exception:
            self.done.emit([])


class _ConnectWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, ssid: str, password: str) -> None:
        super().__init__()
        self._ssid = ssid
        self._password = password

    def run(self) -> None:
        ok, msg = wifi_connect(self._ssid, self._password)
        self.done.emit(ok, msg)


# --- Password Dialog ---

class _PasswordDialog(QDialog):
    def __init__(self, ssid: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Connect to {ssid}").format(ssid=ssid))
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Password:"), self))
        self._field = QLineEdit(self)
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        self._field.returnPressed.connect(self.accept)
        layout.addWidget(self._field)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    @property
    def password(self) -> str:
        return self._field.text()


# --- Sinyal gücü çubuğu ---

def _signal_bars(signal: int) -> str:
    if signal >= 80:
        return "▂▄▆█"
    if signal >= 55:
        return "▂▄▆_"
    if signal >= 30:
        return "▂▄__"
    return "▂___"


# --- Wi-Fi ağ satırı ---

class _WifiRow(QWidget):
    connect_requested = Signal(str)   # ssid
    forget_requested = Signal(str)

    def __init__(self, net: WifiNetwork, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ssid = net.ssid
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 6, 4, 6)
        row.setSpacing(8)

        # Sinyal göstergesi
        bars_lbl = QLabel(_signal_bars(net.signal), self)
        bars_lbl.setFixedWidth(32)
        row.addWidget(bars_lbl)

        # SSID
        name_lbl = QLabel(net.ssid or tr("(Hidden network)"), self)
        if net.active:
            name_lbl.setStyleSheet("font-weight: bold; color: #0067c0;")
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(name_lbl)

        # Güvenlik rozeti
        if net.security:
            sec = QLabel(net.security.split()[0], self)
            sec.setObjectName("Secondary")
            row.addWidget(sec)

        if net.active:
            dis_btn = QPushButton(tr("Disconnect"), self)
            dis_btn.clicked.connect(self._disconnect)
            row.addWidget(dis_btn)
            forget_btn = QPushButton(tr("Forget"), self)
            forget_btn.clicked.connect(lambda: self.forget_requested.emit(self._ssid))
            row.addWidget(forget_btn)
        else:
            con_btn = QPushButton(tr("Connect"), self)
            con_btn.setProperty("primary", True)
            con_btn.clicked.connect(lambda: self.connect_requested.emit(self._ssid))
            row.addWidget(con_btn)

    def _disconnect(self) -> None:
        wifi_disconnect()


# --- Wi-Fi sekmesi ---

class _WifiTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _WifiWorker | None = None
        self._connect_worker: _ConnectWorker | None = None
        self._status: WifiStatus | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # Durum kartı
        self._status_card = Card(self)
        status_row = QHBoxLayout()
        self._status_lbl = QLabel(tr("Checking…"), self._status_card)
        self._status_lbl.setObjectName("H2")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch(1)
        self._toggle_btn = QPushButton("", self._status_card)
        self._toggle_btn.setFixedWidth(90)
        self._toggle_btn.clicked.connect(self._toggle_wifi)
        status_row.addWidget(self._toggle_btn)
        self._status_card.layout.addLayout(status_row)
        layout.addWidget(self._status_card)

        # Ağ listesi başlık + yenile
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel(tr("Available networks"), self))
        list_header.addStretch(1)
        self._refresh_btn = QPushButton(tr("Refresh"), self)
        self._refresh_btn.clicked.connect(self._load)
        list_header.addWidget(self._refresh_btn)
        layout.addLayout(list_header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        net_content = QWidget()
        self._net_layout = QVBoxLayout(net_content)
        self._net_layout.setContentsMargins(0, 0, 0, 0)
        self._net_layout.setSpacing(0)
        scroll.setWidget(net_content)
        layout.addWidget(scroll, 1)

        # Otomatik yenile
        self._timer = QTimer(self)
        self._timer.setInterval(10000)
        self._timer.timeout.connect(self._load)
        self._timer.start()
        self._load()

    def _load(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._worker = _WifiWorker()
        self._worker.status_ready.connect(self._on_status)
        self._worker.networks_ready.connect(self._on_networks)
        self._worker.finished.connect(lambda: self._refresh_btn.setEnabled(True))
        self._worker.start()

    def _on_status(self, status: object) -> None:
        if not isinstance(status, WifiStatus):
            return
        self._status = status
        if status.enabled:
            if status.connected:
                self._status_lbl.setText(tr("Connected: {ssid}").format(ssid=status.ssid))
            else:
                self._status_lbl.setText(tr("Wi-Fi enabled — not connected"))
            self._toggle_btn.setText(tr("Turn off"))
            self._toggle_btn.setProperty("primary", False)
        else:
            self._status_lbl.setText(tr("Wi-Fi is off"))
            self._toggle_btn.setText(tr("Turn on"))
            self._toggle_btn.setProperty("primary", True)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)

    def _on_networks(self, nets: object) -> None:
        net_list: list[WifiNetwork] = nets  # type: ignore[assignment]
        while self._net_layout.count():
            item = self._net_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for net in net_list:
            row = _WifiRow(net, self)
            row.connect_requested.connect(self._on_connect_request)
            row.forget_requested.connect(self._on_forget)
            self._net_layout.addWidget(row)
            sep = QFrame(self)
            sep.setFrameShape(QFrame.Shape.HLine)
            self._net_layout.addWidget(sep)
        self._net_layout.addStretch(1)

    def _toggle_wifi(self) -> None:
        enabled = self._status.enabled if self._status else True
        wifi_set_enabled(not enabled)
        self._load()

    def _on_connect_request(self, ssid: str) -> None:
        # Şifre gerekli mi kontrol et
        nets = wifi_list()
        net = next((n for n in nets if n.ssid == ssid), None)
        password = ""
        if net and net.security:
            dlg = _PasswordDialog(ssid, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            password = dlg.password

        self._refresh_btn.setEnabled(False)
        self._connect_worker = _ConnectWorker(ssid, password)
        self._connect_worker.done.connect(self._on_connect_done)
        self._connect_worker.finished.connect(lambda: self._refresh_btn.setEnabled(True))
        self._connect_worker.start()

    def _on_connect_done(self, ok: bool, msg: str) -> None:
        self._load()
        if not ok:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr("Connection failed"), msg)

    def _on_forget(self, ssid: str) -> None:
        wifi_forget(ssid)
        self._load()

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.start()
        super().showEvent(event)  # type: ignore[misc]

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self._timer.stop()
        super().hideEvent(event)  # type: ignore[misc]


# --- Bluetooth cihaz satırı ---

class _BtRow(QWidget):
    connect_req = Signal(str)
    disconnect_req = Signal(str)
    forget_req = Signal(str)

    def __init__(self, dev: BluetoothDevice, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 6, 4, 6)

        name_lbl = QLabel(dev.name or dev.mac, self)
        if dev.connected:
            name_lbl.setStyleSheet("font-weight: bold; color: #0067c0;")
        row.addWidget(name_lbl, 1)

        mac_lbl = QLabel(dev.mac, self)
        mac_lbl.setObjectName("Secondary")
        row.addWidget(mac_lbl)

        if dev.connected:
            dis_btn = QPushButton(tr("Disconnect"), self)
            dis_btn.clicked.connect(lambda: self.disconnect_req.emit(dev.mac))
            row.addWidget(dis_btn)
        else:
            con_btn = QPushButton(tr("Connect"), self)
            con_btn.setProperty("primary", True)
            con_btn.clicked.connect(lambda: self.connect_req.emit(dev.mac))
            row.addWidget(con_btn)

        forget_btn = QPushButton(tr("Forget"), self)
        forget_btn.clicked.connect(lambda: self.forget_req.emit(dev.mac))
        row.addWidget(forget_btn)


# --- Bluetooth sekmesi ---

class _BtTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _BtWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # Durum + toggle
        top_row = QHBoxLayout()
        self._status_lbl = QLabel("", self)
        self._status_lbl.setObjectName("H2")
        top_row.addWidget(self._status_lbl)
        top_row.addStretch(1)
        self._toggle_btn = QPushButton("", self)
        self._toggle_btn.setFixedWidth(90)
        self._toggle_btn.clicked.connect(self._toggle_bt)
        top_row.addWidget(self._toggle_btn)
        self._scan_btn = QPushButton(tr("Scan"), self)
        self._scan_btn.clicked.connect(self._scan)
        top_row.addWidget(self._scan_btn)
        layout.addLayout(top_row)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._dev_layout = QVBoxLayout(content)
        self._dev_layout.setContentsMargins(0, 0, 0, 0)
        self._dev_layout.setSpacing(0)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        self._refresh_status()
        self._load()

    def _refresh_status(self) -> None:
        enabled = bluetooth_enabled()
        if enabled:
            self._status_lbl.setText(tr("Bluetooth is on"))
            self._toggle_btn.setText(tr("Turn off"))
            self._scan_btn.setEnabled(True)
        else:
            self._status_lbl.setText(tr("Bluetooth is off"))
            self._toggle_btn.setText(tr("Turn on"))
            self._toggle_btn.setProperty("primary", True)
            self._scan_btn.setEnabled(False)
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)

    def _load(self, scan: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._scan_btn.setEnabled(False)
        self._worker = _BtWorker(scan=scan)
        self._worker.done.connect(self._on_devices)
        self._worker.finished.connect(lambda: self._scan_btn.setEnabled(bluetooth_enabled()))
        self._worker.start()

    def _scan(self) -> None:
        self._status_lbl.setText(tr("Scanning…"))
        self._load(scan=True)

    def _toggle_bt(self) -> None:
        bluetooth_set_enabled(not bluetooth_enabled())
        self._refresh_status()
        self._load()

    def _on_devices(self, devs: object) -> None:
        dev_list: list[BluetoothDevice] = devs  # type: ignore[assignment]
        while self._dev_layout.count():
            item = self._dev_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not dev_list:
            lbl = QLabel(tr("No paired devices."), self)
            lbl.setObjectName("Secondary")
            self._dev_layout.addWidget(lbl)
        else:
            for dev in dev_list:
                row = _BtRow(dev, self)
                row.connect_req.connect(self._on_connect)
                row.disconnect_req.connect(self._on_disconnect)
                row.forget_req.connect(self._on_forget)
                self._dev_layout.addWidget(row)
                sep = QFrame(self)
                sep.setFrameShape(QFrame.Shape.HLine)
                self._dev_layout.addWidget(sep)

        self._dev_layout.addStretch(1)
        self._refresh_status()

    def _on_connect(self, mac: str) -> None:
        bluetooth_connect(mac)
        self._load()

    def _on_disconnect(self, mac: str) -> None:
        bluetooth_disconnect(mac)
        self._load()

    def _on_forget(self, mac: str) -> None:
        bluetooth_forget(mac)
        self._load()


# --- Ana sayfa ---

class NetworkPage(BasePage):
    """Wi-Fi ve Bluetooth sayfası."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel(tr("Wi-Fi & Bluetooth"), self)
        title.setObjectName("H1")
        layout.addWidget(title)

        tabs = QTabWidget(self)
        tabs.addTab(_WifiTab(tabs), tr("Wi-Fi"))
        tabs.addTab(_BtTab(tabs), tr("Bluetooth"))
        layout.addWidget(tabs)
