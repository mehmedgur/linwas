"""Ağ/Wi-Fi/Bluetooth yönetimi — NetworkManager (nmcli) ve bluetoothctl.

Root gerekmez; NetworkManager ve bluetoothctl kendi yetki yönetimini yapar.
nmcli dil bağımsız ama UTF-8 çalıştırılır (C.UTF-8): mesajlar İngilizce,
Türkçe karakterli ağ/cihaz adları bozulmaz (LANG=C'de "ş" → "?" olur).
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# --- Yardımcılar ---


def _run(cmd: list[str], timeout: int = 10) -> tuple[str, str]:
    """(stdout, stderr) döner; LANG=C ile dil bağımsız çıktı."""
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.stdout, r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "", ""


def _run_rc(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    """(dönüş kodu, stdout+stderr)."""
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def split_terse(line: str) -> list[str]:
    """`nmcli -t` satırını alanlara böler: ayırıcı ":", alan içindeki ":" ve "\\"
    ters eğik çizgiyle kaçırılır (nmcli(1), --terse)."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields


def unescape_terse(value: str) -> str:
    """`nmcli -t` değerindeki kaçırılmış ":" ve "\\" karakterlerini geri getirir."""
    out: list[str] = []
    escaped = False
    for ch in value:
        if escaped:
            out.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        else:
            out.append(ch)
    return "".join(out)


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
    saved: bool = False  # bu ağ için kayıtlı bağlantı var (şifre yeniden sorulmaz)

    @property
    def quality(self) -> str:
        """ "excellent" | "good" | "fair" | "weak"."""
        return signal_quality(self.signal)


def signal_quality(signal: int) -> str:
    if signal >= 75:
        return "excellent"
    if signal >= 50:
        return "good"
    if signal >= 30:
        return "fair"
    return "weak"


@dataclass
class WifiStatus:
    enabled: bool
    connected: bool
    ssid: str  # bağlı ağ adı; bağlı değilse ""
    device: str  # ör. "wlan0"
    signal: int = 0  # bağlı ağın sinyali (0-100)
    ip: str = ""  # bağlı ağdaki IPv4 adresi (ör. "192.168.1.5")


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
        parts = split_terse(line)
        if len(parts) < 4:
            continue
        dev, typ, state, conn = parts[0], parts[1], parts[2], parts[3]
        if typ == "wifi":
            device = dev
            if state == "connected":
                connected = True
                ssid = conn
            break

    signal = 0
    ip = ""
    if connected:
        active = next((n for n in wifi_list(rescan=False) if n.active), None)
        signal = active.signal if active else 0
        ip = parse_ip4(_nmcli("-t", "-f", "IP4.ADDRESS", "device", "show", device))
    return WifiStatus(
        enabled=enabled, connected=connected, ssid=ssid, device=device, signal=signal, ip=ip
    )


def parse_ip4(out: str) -> str:
    """`nmcli -t -f IP4.ADDRESS device show DEV` → ilk adres, önek uzunluğu olmadan."""
    for line in out.splitlines():
        _, sep, value = line.partition(":")
        if sep and value.strip():
            return value.strip().split("/")[0]
    return ""


@dataclass
class WifiDetails:
    """Bağlı Wi-Fi ağının ayrıntıları (Wi-Fi sekmesindeki "Bağlantı ayrıntıları" kartı)."""

    ssid: str
    device: str
    ip: str = ""  # IPv4 adresi (önek olmadan)
    prefix: int | None = None  # ağ öneki (ör. 24)
    gateway: str = ""
    dns: list[str] = field(default_factory=list)
    mac: str = ""  # bu bilgisayarın Wi-Fi kartının donanım adresi
    bssid: str = ""  # bağlı olunan erişim noktası
    band: str = ""  # "2.4 GHz" | "5 GHz" | "6 GHz"
    channel: int | None = None
    frequency: int | None = None  # MHz
    rate: int | None = None  # Mbit/s (bağlantı hızı)
    signal: int = 0  # 0-100
    security: str = ""  # "WPA2", "" (açık)


def parse_device_show(out: str) -> dict[str, list[str]]:
    """`nmcli -t -f ALAN,... device show DEV` → {alan: [değerler]}.

    Çoklu alanlardaki "[n]" dizini atılır (IP4.DNS[1], IP4.DNS[2] → "IP4.DNS"); kaçırılmış
    ":" geri getirilir (MAC adresi); boş değerler atlanır.
    """
    result: dict[str, list[str]] = {}
    for line in out.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = re.sub(r"\[\d+\]$", "", key.strip())
        value = unescape_terse(value).strip()
        if value:
            result.setdefault(key, []).append(value)
    return result


def band_from_frequency(mhz: int | None) -> str:
    """Merkez frekansından (MHz) bant: 2.4 / 5 / 6 GHz; bilinmiyorsa boş."""
    if mhz is None:
        return ""
    if 2400 <= mhz <= 2500:
        return "2.4 GHz"
    if 4900 <= mhz <= 5895:
        return "5 GHz"
    if 5925 <= mhz <= 7125:
        return "6 GHz"
    return ""


def _leading_int(text: str) -> int | None:
    """ "2412 MHz" → 2412, "130 Mbit/s" → 130; sayı yoksa None."""
    m = re.match(r"\s*(\d+)", text)
    return int(m.group(1)) if m else None


def build_wifi_details(ssid: str, device: str, show_out: str, list_out: str) -> WifiDetails:
    """`device show` ve `device wifi list` çıktılarından ayrıntıları kurar (komut çalıştırmaz).

    list_out alanları: ACTIVE,DEVICE,BSSID,SSID,CHAN,FREQ,RATE,SIGNAL,SECURITY.
    """
    info = parse_device_show(show_out)
    details = WifiDetails(ssid=ssid, device=device)
    details.mac = (info.get("GENERAL.HWADDR") or [""])[0]
    details.gateway = (info.get("IP4.GATEWAY") or [""])[0]
    details.dns = list(info.get("IP4.DNS", []))
    address = (info.get("IP4.ADDRESS") or [""])[0]
    if address:
        try:
            iface = ipaddress.ip_interface(address)
            details.ip, details.prefix = str(iface.ip), iface.network.prefixlen
        except ValueError:
            details.ip = address.split("/")[0]

    rows = [split_terse(line) for line in list_out.splitlines()]
    rows = [r for r in rows if len(r) >= 9 and r[0].strip().lower() == "yes"]
    row = next((r for r in rows if r[1] == device), rows[0] if rows else None)
    if row is not None:
        details.bssid = row[2]
        details.channel = _leading_int(row[4])
        details.frequency = _leading_int(row[5])
        details.rate = _leading_int(row[6])
        details.signal = _leading_int(row[7]) or 0
        details.security = row[8].strip()
        details.band = band_from_frequency(details.frequency)
    return details


def wifi_details(status: WifiStatus) -> WifiDetails | None:
    """Bağlı ağın ayrıntıları; bağlı değilse None."""
    if not status.connected or not status.device:
        return None
    show = _nmcli(
        "-t",
        "-f",
        "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
        "device",
        "show",
        status.device,
    )
    listing = _nmcli(
        "-t",
        "-f",
        "ACTIVE,DEVICE,BSSID,SSID,CHAN,FREQ,RATE,SIGNAL,SECURITY",
        "device",
        "wifi",
        "list",
        "--rescan",
        "no",
        timeout=30,
    )
    return build_wifi_details(status.ssid, status.device, show, listing)


def parse_wifi_list(out: str) -> list[WifiNetwork]:
    """`nmcli -t -f ACTIVE,BSSID,SSID,SIGNAL,SECURITY device wifi list` çıktısı.

    Aynı ad birden fazla erişim noktasında görünürse en güçlü (ya da bağlı olan) kalır.
    """
    best: dict[str, WifiNetwork] = {}
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) < 5:
            continue
        active, bssid, ssid, signal_str, security = parts[:5]
        if not ssid:
            continue
        try:
            signal = int(signal_str)
        except ValueError:
            signal = 0
        net = WifiNetwork(
            ssid=ssid,
            signal=signal,
            security=security.strip(),
            active=active.strip().lower() == "yes",
            bssid=bssid,
        )
        old = best.get(ssid)
        if old is None or (net.active, net.signal) > (old.active, old.signal):
            best[ssid] = net
    return sorted(best.values(), key=lambda n: (not n.active, -n.signal))


def wifi_list(rescan: bool = True) -> list[WifiNetwork]:
    """Görünen Wi-Fi ağlarını döner; bağlı olan önce, sonra sinyale göre."""
    args = ["-t", "-f", "ACTIVE,BSSID,SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
    if not rescan:
        args += ["--rescan", "no"]
    nets = parse_wifi_list(_nmcli(*args, timeout=30))
    saved = set(wifi_saved_connections())
    for net in nets:
        net.saved = net.ssid in saved
    return nets


def wifi_connect(
    ssid: str, password: str = "", saved: bool = False, hidden: bool = False
) -> tuple[bool, str]:
    """Wi-Fi ağına bağlanır. (başarılı, hata_mesajı) döner.

    Kayıtlı ağda kayıtlı bağlantı açılır (yeni, yinelenen bağlantı oluşmaz).
    """
    if saved and not password:
        code, out = _run_rc(["nmcli", "connection", "up", "id", ssid], timeout=45)
        if code == 0:
            return True, ""
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    if hidden:
        cmd += ["hidden", "yes"]
    code, out = _run_rc(cmd, timeout=45)
    return (True, "") if code == 0 else (False, out)


def wifi_disconnect() -> bool:
    status = wifi_status()
    if not status.device:
        return False
    out, _ = _run(["nmcli", "device", "disconnect", status.device])
    return "successfully disconnected" in out.lower()


def wifi_set_enabled(enabled: bool) -> bool:
    return _run_rc(["nmcli", "radio", "wifi", "on" if enabled else "off"])[0] == 0


def wifi_saved_connections() -> list[str]:
    """Kayıtlı Wi-Fi bağlantılarını döner."""
    out = _nmcli("-t", "-f", "NAME,TYPE", "connection")
    names = []
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) >= 2 and parts[1] == "802-11-wireless":
            names.append(parts[0])
    return names


def wifi_forget(ssid: str) -> bool:
    """Kayıtlı bağlantıyı siler."""
    return _run_rc(["nmcli", "connection", "delete", "id", ssid])[0] == 0


# --- Bluetooth ---


@dataclass
class BluetoothDevice:
    mac: str
    name: str
    paired: bool
    connected: bool
    icon: str = ""  # "phone", "audio-headset", "input-mouse"... (BlueZ)
    rssi: int | None = None  # dBm; yalnızca yakın zamanda taramada görüldüyse
    battery: int | None = None  # yüzde (destekleyen cihazlarda)

    @property
    def quality(self) -> str | None:
        """RSSI'den sinyal kalitesi; bilinmiyorsa None."""
        if self.rssi is None:
            return None
        # Yaklaşık: -50 dBm ve üstü çok iyi, -90 dBm ve altı zayıf
        percent = max(0, min(100, 2 * (self.rssi + 100)))
        return signal_quality(percent)


_RE_MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")


def bluetooth_enabled() -> bool:
    return bluetooth_state() == "on"


def parse_rfkill(out: str) -> str:
    """`rfkill list bluetooth` → "missing" (aygıt yok) | "blocked" (donanım anahtarı kapalı)
    | "off" | "on"."""
    if not out.strip():
        return "missing"
    if "Hard blocked: yes" in out:
        return "blocked"
    return "off" if "Soft blocked: yes" in out else "on"


def bluetooth_state() -> str:
    if shutil.which("rfkill") is None:
        # rfkill kurulu değilse (bazı Debian kurulumları) yalnızca aygıtın varlığına bakılır
        sysfs = Path("/sys/class/bluetooth")
        return "on" if sysfs.is_dir() and any(sysfs.iterdir()) else "missing"
    return parse_rfkill(_run(["rfkill", "list", "bluetooth"])[0])


def bluetooth_set_enabled(enabled: bool) -> bool:
    cmd = ["rfkill", "unblock" if enabled else "block", "bluetooth"]
    _run(cmd)
    return True


def _btctl(*args: str, timeout: int = 15) -> tuple[int, str]:
    """bluetoothctl'i komut kipinde çalıştırır (ör. `bluetoothctl info MAC`)."""
    return _run_rc(["bluetoothctl", *args], timeout=timeout)


def parse_devices(out: str) -> list[tuple[str, str]]:
    """`bluetoothctl devices` → [(MAC, ad)]."""
    found = []
    for line in out.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2 and parts[0] == "Device" and _RE_MAC.match(parts[1]):
            found.append((parts[1], parts[2].strip() if len(parts) > 2 else parts[1]))
    return found


def parse_info(mac: str, name: str, out: str) -> BluetoothDevice:
    """`bluetoothctl info MAC` çıktısı."""
    fields: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.strip().partition(": ")
        if sep and key not in fields:
            fields[key] = value.strip()
    rssi = None
    m = re.match(r"(-?\d+)", fields.get("RSSI", ""))
    if m:
        rssi = int(m.group(1))
    battery = None
    m = re.search(r"\((\d+)\)", fields.get("Battery Percentage", ""))
    if m:
        battery = int(m.group(1))
    return BluetoothDevice(
        mac=mac,
        name=fields.get("Alias") or fields.get("Name") or name,
        paired=fields.get("Paired") == "yes",
        connected=fields.get("Connected") == "yes",
        icon=fields.get("Icon", ""),
        rssi=rssi,
        battery=battery,
    )


def bluetooth_list_devices() -> list[BluetoothDevice]:
    """Bilinen cihazlar (eşleşmiş + taramada bulunan); bağlı ve eşleşmiş olanlar önce."""
    devices = [
        parse_info(mac, name, _btctl("info", mac)[1])
        for mac, name in parse_devices(_btctl("devices")[1])
    ]
    return sorted(devices, key=lambda d: (not d.connected, not d.paired, -(d.rssi or -999)))


def _valid_mac(mac: str) -> bool:
    return bool(_RE_MAC.match(mac))


def bluetooth_connect(mac: str) -> tuple[bool, str]:
    if not _valid_mac(mac):
        return False, "invalid address"
    # Eşleşmemiş cihaz önce eşleştirilir ve güvenilir yapılır
    info = parse_info(mac, mac, _btctl("info", mac)[1])
    if not info.paired:
        code, out = _btctl("pair", mac, timeout=30)
        if code != 0:
            return False, out
        _btctl("trust", mac)
    code, out = _btctl("connect", mac, timeout=30)
    return code == 0, out


def bluetooth_disconnect(mac: str) -> tuple[bool, str]:
    if not _valid_mac(mac):
        return False, "invalid address"
    code, out = _btctl("disconnect", mac)
    return code == 0, out


def bluetooth_forget(mac: str) -> bool:
    return _valid_mac(mac) and _btctl("remove", mac)[0] == 0


def bluetooth_scan(timeout: int = 10) -> list[BluetoothDevice]:
    """Yakındaki cihazları `timeout` saniye tarar, sonra listeyi döner."""
    _btctl("--timeout", str(timeout), "scan", "on", timeout=timeout + 10)
    return bluetooth_list_devices()
