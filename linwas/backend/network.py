"""Ağ/Wi-Fi/Bluetooth yönetimi — NetworkManager (nmcli) ve bluetoothctl.

Root gerekmez; NetworkManager ve bluetoothctl kendi yetki yönetimini yapar.
nmcli dil bağımsız çalıştırılır (LANG=C).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

# --- Yardımcılar ---


def _run(cmd: list[str], timeout: int = 10) -> tuple[str, str]:
    """(stdout, stderr) döner; LANG=C ile dil bağımsız çıktı."""
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.stdout, r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "", ""


def _nmcli(*args: str, timeout: int = 10) -> str:
    out, _ = _run(["nmcli", *args], timeout)
    return out


# --- Wi-Fi ---


@dataclass
class WifiNetwork:
    ssid: str
    signal: int  # 0-100
    security: str  # "WPA2", "WPA1", "OWE", "" (açık)
    active: bool
    bssid: str


@dataclass
class WifiStatus:
    enabled: bool
    connected: bool
    ssid: str  # bağlı ağ adı; bağlı değilse ""
    device: str  # ör. "wlan0"


def wifi_status() -> WifiStatus:
    """Aktif Wi-Fi durumunu döner."""
    # Radio durumu
    radio_out = _nmcli("-t", "-f", "WIFI", "radio")
    enabled = radio_out.strip().lower() == "enabled"

    # Bağlı cihaz
    dev_out = _nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device")
    device = ""
    ssid = ""
    connected = False
    for line in dev_out.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        dev, typ, state, conn = parts[0], parts[1], parts[2], ":".join(parts[3:])
        if typ == "wifi":
            device = dev
            if state == "connected":
                connected = True
                ssid = conn
            break

    return WifiStatus(enabled=enabled, connected=connected, ssid=ssid, device=device)


def wifi_list() -> list[WifiNetwork]:
    """Görünen Wi-Fi ağlarını döner; sinyal gücüne göre azalan sırada."""
    out = _nmcli("-t", "-f", "ACTIVE,BSSID,SSID,SIGNAL,SECURITY", "device", "wifi", "list")
    networks: list[WifiNetwork] = []
    seen_ssids: set[str] = set()
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 5:
            continue
        active_str = parts[0].strip().lower()
        bssid = parts[1].strip().replace("\\:", ":")
        ssid = parts[2].strip()
        signal_str = parts[3].strip()
        security = ":".join(parts[4:]).strip()

        if not ssid or ssid in seen_ssids:
            continue
        seen_ssids.add(ssid)
        try:
            signal = int(signal_str)
        except ValueError:
            signal = 0

        networks.append(
            WifiNetwork(
                ssid=ssid,
                signal=signal,
                security=security,
                active=active_str == "yes",
                bssid=bssid,
            )
        )
    return sorted(networks, key=lambda n: (not n.active, -n.signal))


def wifi_connect(ssid: str, password: str = "") -> tuple[bool, str]:
    """Wi-Fi ağına bağlanır. (başarılı, hata_mesajı) döner."""
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    out, err = _run(cmd, timeout=30)
    success = "successfully activated" in out.lower() or "device" in out.lower()
    if not success:
        msg = err.strip() or out.strip()
        return False, msg
    return True, ""


def wifi_disconnect() -> bool:
    status = wifi_status()
    if not status.device:
        return False
    out, _ = _run(["nmcli", "device", "disconnect", status.device])
    return "successfully disconnected" in out.lower()


def wifi_set_enabled(enabled: bool) -> bool:
    out, _ = _run(["nmcli", "radio", "wifi", "on" if enabled else "off"])
    return True  # nmcli hata kodu yerine stderr'e yazar


def wifi_saved_connections() -> list[str]:
    """Kayıtlı Wi-Fi bağlantılarını döner."""
    out = _nmcli("-t", "-f", "NAME,TYPE", "connection")
    return [line.split(":")[0] for line in out.splitlines() if ":wifi" in line.lower()]


def wifi_forget(ssid: str) -> bool:
    """Kayıtlı bağlantıyı siler."""
    out, _ = _run(["nmcli", "connection", "delete", ssid])
    return "successfully deleted" in out.lower()


# --- Bluetooth ---


@dataclass
class BluetoothDevice:
    mac: str
    name: str
    paired: bool
    connected: bool


def bluetooth_enabled() -> bool:
    out, _ = _run(["rfkill", "list", "bluetooth"])
    return "Soft blocked: yes" not in out


def bluetooth_set_enabled(enabled: bool) -> bool:
    cmd = ["rfkill", "unblock" if enabled else "block", "bluetooth"]
    _run(cmd)
    return True


def _bt_run(commands: list[str], timeout: int = 8) -> str:
    """bluetoothctl'e komut satırları gönderir."""
    script = "\n".join(commands) + "\n"
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            ["bluetoothctl"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=env,
        )
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def bluetooth_list_devices() -> list[BluetoothDevice]:
    """Eşleştirilmiş ve bilinen Bluetooth cihazlarını döner."""
    devices: list[BluetoothDevice] = []
    out = _bt_run(["devices", "exit"])
    paired_macs: set[str] = set()
    connected_macs: set[str] = set()

    # Eşleşmiş cihazlar
    out_paired = _bt_run(["devices Paired", "exit"])
    for line in out_paired.splitlines():
        if line.startswith("Device "):
            parts = line.split(" ", 2)
            if len(parts) >= 2:
                paired_macs.add(parts[1])

    # Bağlı cihazlar
    out_connected = _bt_run(["devices Connected", "exit"])
    for line in out_connected.splitlines():
        if line.startswith("Device "):
            parts = line.split(" ", 2)
            if len(parts) >= 2:
                connected_macs.add(parts[1])

    for line in out.splitlines():
        if not line.startswith("Device "):
            continue
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        mac = parts[1]
        name = parts[2].strip()
        devices.append(
            BluetoothDevice(
                mac=mac,
                name=name,
                paired=mac in paired_macs or True,  # 'devices' zaten eşleşmişleri gösterir
                connected=mac in connected_macs,
            )
        )
    return devices


def bluetooth_connect(mac: str) -> tuple[bool, str]:
    out = _bt_run([f"connect {mac}", "exit"], timeout=15)
    success = "successful" in out.lower() or "connected" in out.lower()
    return success, out.strip()


def bluetooth_disconnect(mac: str) -> tuple[bool, str]:
    out = _bt_run([f"disconnect {mac}", "exit"])
    success = "successful" in out.lower()
    return success, out.strip()


def bluetooth_forget(mac: str) -> bool:
    out = _bt_run([f"remove {mac}", "exit"])
    return "removed" in out.lower()


def bluetooth_scan(timeout: int = 8) -> list[BluetoothDevice]:
    """Yeni cihazları tarar ve bulduklarını döner."""
    _bt_run(["scan on", "exit"], timeout=timeout)
    # Tarama sonrası bilinen cihazları döndür
    return bluetooth_list_devices()
