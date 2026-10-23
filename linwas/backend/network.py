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


def leading_int(text: str) -> int | None:
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
        details.channel = leading_int(row[4])
        details.frequency = leading_int(row[5])
        details.rate = leading_int(row[6])
        details.signal = leading_int(row[7]) or 0
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


# --- Wi-Fi ağ ayarları (kayıtlı bağlantı profili) ---

# Hazır DNS seçenekleri (sağlayıcıların herkese açık adresleri)
DNS_PRESETS: dict[str, tuple[str, ...]] = {
    "cloudflare": ("1.1.1.1", "1.0.0.1"),
    "google": ("8.8.8.8", "8.8.4.4"),
}
METERED_VALUES = ("unknown", "yes", "no")  # connection.metered (profilde yalnız bu üçü geçerli)
MAX_DNS = 3
_PROFILE_FIELDS = (
    "connection.autoconnect,connection.metered,ipv4.method,ipv4.addresses,"
    "ipv4.gateway,ipv4.dns,ipv4.ignore-auto-dns"
)


class ProfileError(ValueError):
    """Geçersiz ağ ayarı; `code` arayüzde sade bir iletiye çevrilir."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class WifiProfile:
    name: str
    autoconnect: bool = True
    metered: str = "unknown"
    ipv4_method: str = "auto"  # "auto" | "manual" | başka (shared, link-local, disabled)
    address: str = ""  # ilk IPv4 adresi (önek olmadan)
    prefix: int | None = None
    gateway: str = ""
    dns: list[str] = field(default_factory=list)
    ignore_auto_dns: bool = False

    @property
    def ip_editable(self) -> bool:
        """Yalnızca otomatik (DHCP) ve elle IP düzenlenir; diğer kipler olduğu gibi kalır."""
        return self.ipv4_method in ("auto", "manual")

    @property
    def dns_choice(self) -> str:
        """ "auto" | "cloudflare" | "google" | "custom"."""
        if not self.dns:
            return "auto"
        for key, servers in DNS_PRESETS.items():
            if tuple(self.dns) == servers:
                return key
        return "custom"


@dataclass
class ProfileChange:
    """Ayarlar penceresinden gelen değişiklik. None olan alanlara dokunulmaz."""

    autoconnect: bool
    metered: str = "unknown"
    ipv4_method: str | None = None  # "auto" | "manual"
    address: str = ""
    netmask: str = ""  # "24" ya da "255.255.255.0"
    gateway: str = ""
    dns_choice: str | None = None  # "auto" | "cloudflare" | "google" | "custom"
    dns: list[str] = field(default_factory=list)  # yalnızca "custom" için


def _split_list(value: str) -> list[str]:
    """nmcli'nin liste değerini ("a, b", "a b", "a|b") parçalar; "--" ve boşlar atılır."""
    return [part for part in re.split(r"[,\s|]+", value) if part and part != "--"]


def parse_profile(name: str, out: str) -> WifiProfile:
    """`nmcli -t -f connection.autoconnect,... connection show id AD` çıktısı."""
    values: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            values[key.strip()] = unescape_terse(value).strip()
    profile = WifiProfile(name=name)
    profile.autoconnect = values.get("connection.autoconnect", "yes").lower() != "no"
    metered = values.get("connection.metered", "unknown").lower()
    profile.metered = metered if metered in ("yes", "no") else "unknown"
    profile.ipv4_method = values.get("ipv4.method", "auto") or "auto"
    addresses = _split_list(values.get("ipv4.addresses", ""))
    if addresses:
        try:
            iface = ipaddress.ip_interface(addresses[0])
            profile.address, profile.prefix = str(iface.ip), iface.network.prefixlen
        except ValueError:
            profile.address = addresses[0].split("/")[0]
    profile.gateway = (_split_list(values.get("ipv4.gateway", "")) or [""])[0]
    profile.dns = _split_list(values.get("ipv4.dns", ""))
    profile.ignore_auto_dns = values.get("ipv4.ignore-auto-dns", "no").lower() == "yes"
    return profile


def wifi_profile(name: str) -> WifiProfile | None:
    """Kayıtlı ağın ayarları; okunamazsa None."""
    out = _nmcli("-t", "-f", _PROFILE_FIELDS, "connection", "show", "id", name)
    return parse_profile(name, out) if out.strip() else None


def _prefix_of(netmask: str) -> int:
    """ "24" ya da "255.255.255.0" → 24 (8-30 arası; ev/ofis ağları için makul)."""
    try:
        prefix = ipaddress.IPv4Network(f"0.0.0.0/{netmask.strip()}").prefixlen
    except ValueError:
        raise ProfileError("bad_mask") from None
    if not 8 <= prefix <= 30:
        raise ProfileError("bad_mask")
    return prefix


def _servers_of(change: ProfileChange) -> list[str] | None:
    """Seçime göre DNS sunucuları: None = dokunma, [] = otomatik, liste = elle."""
    if change.dns_choice is None:
        return None
    if change.dns_choice == "auto":
        return []
    if change.dns_choice in DNS_PRESETS:
        return list(DNS_PRESETS[change.dns_choice])
    servers: list[str] = []
    for raw in change.dns:
        raw = raw.strip()
        if not raw:
            continue
        try:
            addr = ipaddress.IPv4Address(raw)
        except ValueError:
            raise ProfileError("bad_dns") from None
        if str(addr) in servers:
            raise ProfileError("bad_dns")
        servers.append(str(addr))
    if not servers:
        raise ProfileError("bad_dns")
    if len(servers) > MAX_DNS:
        raise ProfileError("too_many_dns")
    return servers


def build_modify_args(name: str, change: ProfileChange) -> list[str]:
    """`nmcli` argümanları (komut çalıştırmaz). Geçersiz değerde ProfileError."""
    if change.metered not in METERED_VALUES:
        raise ProfileError("bad_metered")
    args = [
        "connection",
        "modify",
        "id",
        name,
        "connection.autoconnect",
        "yes" if change.autoconnect else "no",
        "connection.metered",
        change.metered,
    ]
    servers: list[str] | None = None
    if change.ipv4_method == "manual":
        try:
            ip = ipaddress.IPv4Address(change.address.strip())
        except ValueError:
            raise ProfileError("bad_address") from None
        iface = ipaddress.IPv4Interface(f"{ip}/{_prefix_of(change.netmask)}")
        net = iface.network
        if ip in (net.network_address, net.broadcast_address):
            raise ProfileError("bad_address")
        gateway = change.gateway.strip()
        if gateway:
            try:
                gw = ipaddress.IPv4Address(gateway)
            except ValueError:
                raise ProfileError("bad_gateway") from None
            if gw not in net or gw in (ip, net.network_address, net.broadcast_address):
                raise ProfileError("gateway_outside")
        servers = _servers_of(change)  # önce adres hataları, sonra DNS
        if not servers:
            # Elle IP'de DHCP'nin DNS'i gelmez: adlar çözülsün diye bir DNS şart
            raise ProfileError("no_dns")
        args += [
            "ipv4.method",
            "manual",
            "ipv4.addresses",
            str(iface),
            "ipv4.gateway",
            gateway,
        ]
    elif change.ipv4_method == "auto":
        args += ["ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", ""]
        servers = _servers_of(change)
    elif change.ipv4_method is not None:
        raise ProfileError("bad_method")
    else:
        servers = _servers_of(change)
    if servers is not None:
        # Boş değer özelliği varsayılana döndürür (nmcli(1), connection modify)
        args += ["ipv4.dns", " ".join(servers), "ipv4.ignore-auto-dns", "yes" if servers else "no"]
    return args


def wifi_password(name: str) -> str | None:
    """Kayıtlı ağın şifresi (WPA/WPA2/WPA3-Personal parolası); yoksa ya da okunamazsa None.

    `nmcli -s` (--show-secrets) gizli bilgiyi gösterir; açık ve kurumsal (802.1X) ağlarda ya da
    şifre başka bir hesabın/anahtarlığın elindeyse boş döner. Şifre hiçbir yere kaydedilmez.
    """
    out, _ = _run(
        ["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", "id", name]
    )
    value = unescape_terse(out.rstrip("\n"))
    return value if value and value != "--" else None


def reconnect_needed(old: WifiProfile, change: ProfileChange) -> bool:
    """IP ya da DNS değiştiyse etkin bağlantı yeniden kurulur (diğerleri anında işler)."""
    servers = _servers_of(change)
    if servers is not None and servers != old.dns:
        return True
    if change.ipv4_method is None:
        return False
    if change.ipv4_method != old.ipv4_method:
        return True
    if change.ipv4_method == "manual":
        return (
            change.address.strip() != old.address
            or _prefix_of(change.netmask) != old.prefix
            or change.gateway.strip() != old.gateway
        )
    return False


def wifi_profile_save(
    name: str, change: ProfileChange, reconnect: bool = False
) -> tuple[bool, str]:
    """Ayarları yazar; `reconnect` ise etkin bağlantıyı yeniden kurar. (başarılı, çıktı)."""
    args = build_modify_args(name, change)
    code, out = _run_rc(["nmcli", *args], timeout=30)
    if code != 0:
        return False, out
    if reconnect:
        code, out = _run_rc(["nmcli", "connection", "up", "id", name], timeout=60)
        return code == 0, out
    return True, ""


# --- Hotspot (erişim noktası) ---

HOTSPOT_NAME = "Linwas Hotspot"  # Linwas'ın oluşturduğu hotspot bağlantısının adı
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # karışan harfler (l, o, 0, 1, i) yok


class HotspotError(ValueError):
    """Geçersiz hotspot ayarı; `code` arayüzde sade bir iletiye çevrilir."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class HotspotInfo:
    name: str  # bağlantı adı
    ssid: str  # yayınlanan ağ adı
    device: str


def parse_hotspot(name: str, device: str, out: str) -> HotspotInfo | None:
    """`nmcli -t -f 802-11-wireless.mode,802-11-wireless.ssid connection show id AD` çıktısı.

    Kip "ap" ise bağlantı bir erişim noktasıdır (hotspot).
    """
    values: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            values[key.strip()] = unescape_terse(value).strip()
    if values.get("802-11-wireless.mode", "").lower() != "ap":
        return None
    return HotspotInfo(name=name, ssid=values.get("802-11-wireless.ssid") or name, device=device)


def hotspot_info(status: WifiStatus) -> HotspotInfo | None:
    """Wi-Fi kartı şu an bir hotspot yayınlıyorsa bilgisi; değilse None.

    `status.ssid` aslında etkin bağlantının (profilin) adıdır; Linwas'ınkinde HOTSPOT_NAME.
    """
    if not status.connected or not status.device or not status.ssid:
        return None
    out = _nmcli(
        "-t",
        "-f",
        "802-11-wireless.mode,802-11-wireless.ssid",
        "connection",
        "show",
        "id",
        status.ssid,
    )
    return parse_hotspot(status.ssid, status.device, out)


def is_hotspot(name: str) -> bool:
    """Bu bağlantı profili bir erişim noktası (hotspot) mı? Başka araçların hotspot'u da sayılır."""
    out = _nmcli("-t", "-f", "802-11-wireless.mode", "connection", "show", "id", name)
    return parse_hotspot(name, "", out) is not None


def default_hotspot_ssid() -> str:
    """Bilgisayar adı (en çok 32 bayt); alınamazsa "Linwas"."""
    name = (os.uname().nodename if hasattr(os, "uname") else "") or "Linwas"
    return name.encode("utf-8")[:32].decode("utf-8", errors="ignore") or "Linwas"


def generate_hotspot_password(length: int = 12) -> str:
    """Okunaklı, tahmini zor rastgele şifre (WPA2 için 8-63 karakter)."""
    import secrets

    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def hotspot_defaults() -> tuple[str, str]:
    """Hotspot penceresinin ilk (ağ adı, şifre) değerleri.

    Daha önce Linwas hotspot'u açıldıysa adı ve şifresi korunur (diğer cihazlar aynı ağa
    kendiliğinden bağlanır). Yoksa bilgisayar adı ve rastgele bir şifre önerilir.
    """
    out = _nmcli(
        "-t",
        "-f",
        "802-11-wireless.mode,802-11-wireless.ssid",
        "connection",
        "show",
        "id",
        HOTSPOT_NAME,
    )
    previous = parse_hotspot(HOTSPOT_NAME, "", out)
    if previous is not None:
        password = wifi_password(HOTSPOT_NAME)
        if password:
            return previous.ssid, password
    return default_hotspot_ssid(), generate_hotspot_password()


def validate_hotspot(ssid: str, password: str) -> None:
    """Ağ adı 1-32 bayt, şifre 8-63 yazdırılabilir ASCII olmalı; değilse HotspotError."""
    if not ssid or len(ssid.encode("utf-8")) > 32 or any(ord(ch) < 32 for ch in ssid):
        raise HotspotError("bad_ssid")
    if not 8 <= len(password) <= 63 or any(not 32 <= ord(ch) <= 126 for ch in password):
        raise HotspotError("bad_password")


def hotspot_start(device: str, ssid: str, password: str) -> tuple[bool, str]:
    """Hotspot'u açar (bu Wi-Fi kartı o an bağlı olduğu ağdan ayrılır). (başarılı, çıktı).

    Eski Linwas hotspot profili silinip yenisi oluşturulur; şifre profilde saklanır.
    """
    validate_hotspot(ssid, password)
    if not device:
        return False, "no Wi-Fi device"
    _run_rc(["nmcli", "connection", "delete", "id", HOTSPOT_NAME])  # yoksa hata yok sayılır
    cmd = [
        "nmcli",
        "device",
        "wifi",
        "hotspot",
        "ifname",
        device,
        "con-name",
        HOTSPOT_NAME,
        "ssid",
        ssid,
        "password",
        password,
    ]
    code, out = _run_rc(cmd, timeout=45)
    return code == 0, out


def hotspot_stop(name: str) -> bool:
    """Hotspot'u kapatır (`nmcli connection down`)."""
    return _run_rc(["nmcli", "connection", "down", "id", name])[0] == 0


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
    trusted: bool = False  # güvenilir cihaz: açılınca kendiliğinden bağlanabilir

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
        trusted=fields.get("Trusted") == "yes",
    )


# BlueZ adı olmayan cihaza adresinden bir ad uydurur ("AA-BB-CC-DD-EE-FF")
_RE_ADDRESS_NAME = re.compile(r"^[0-9A-Fa-f]{2}([-:][0-9A-Fa-f]{2}){5}$")


def is_unnamed_device(device: BluetoothDevice) -> bool:
    """Adı yok ya da yalnızca adresinden ibaret (çoğu zaman çevredeki rastgele BLE cihazları)."""
    name = (device.name or "").strip()
    return not name or bool(_RE_ADDRESS_NAME.match(name))


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


def bluetooth_set_trusted(mac: str, trusted: bool) -> bool:
    """Cihazı güvenilir yapar/yapmaz (`bluetoothctl trust|untrust`); sonucu geri okuyup doğrular."""
    if not _valid_mac(mac):
        return False
    _btctl("trust" if trusted else "untrust", mac)
    return parse_info(mac, mac, _btctl("info", mac)[1]).trusted == trusted


class AliasError(ValueError):
    """Geçersiz cihaz adı; `code` arayüzde sade bir iletiye çevrilir."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


ALIAS_MAX = 64


def validate_alias(name: str) -> str:
    """Cihaz takma adını temizler (boşlukları sadeleştirir). Boş ad, cihazın kendi adına döner."""
    alias = " ".join(name.split())
    if len(alias) > ALIAS_MAX:
        raise AliasError("too_long")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in alias):
        raise AliasError("bad_chars")
    return alias


def bluetooth_adapters(sysfs: Path = Path("/sys/class/bluetooth")) -> list[str]:
    """Bluetooth denetleyicilerinin BlueZ adları ("hci0", "hci1"…); bulunamazsa ["hci0"].

    Çekirdek `/sys/class/bluetooth` altında bağlantılar için "hci0:256" gibi girdiler de açar;
    yalnızca denetleyiciler alınır.
    """
    try:
        names = [p.name for p in sysfs.iterdir() if re.fullmatch(r"hci\d+", p.name)]
    except OSError:
        names = []
    return sorted(names, key=lambda n: int(n[3:])) or ["hci0"]


def bluetooth_device_path(adapter: str, mac: str) -> str:
    """BlueZ D-Bus nesne yolu: /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF (org.bluez.Device belgesi)."""
    return f"/org/bluez/{adapter}/dev_{mac.replace(':', '_')}"


def _set_alias(interface: str, paths: list[str], alias: str) -> tuple[bool, str]:
    """D-Bus özelliği `Alias`'ı `busctl set-property` ile yazar; ilk başarılı nesnede durur.

    Ad kullanıcıdan geldiği için komutta `--` sonrasına konur: yoksa "-H sunucu" gibi bir ad
    busctl'e seçenek olarak geçerdi (uzak makineye bağlanma seçeneği dahil).
    """
    last = ""
    for path in paths:
        code, out = _run_rc(
            [
                "busctl",
                "--system",
                "set-property",
                "--",
                "org.bluez",
                path,
                interface,
                "Alias",
                "s",
                alias,
            ],
            timeout=10,
        )
        if code == 0:
            return True, ""
        last = out
    return False, last


def bluetooth_rename(mac: str, name: str) -> tuple[bool, str]:
    """Cihaza takma ad verir (`org.bluez.Device1` özelliği `Alias`); boş ad varsayılana döndürür.

    `bluetoothctl set-alias` "geçerli cihaz"a bağlıdır, tek seferlik komutta kullanılamaz; bu yüzden
    D-Bus özelliği yazılır. Cihaz hangi denetleyiciye bağlıysa onun yolunda başarılı olur.
    """
    if not _valid_mac(mac):
        return False, "invalid address"
    alias = validate_alias(name)
    paths = [bluetooth_device_path(adapter, mac) for adapter in bluetooth_adapters()]
    return _set_alias("org.bluez.Device1", paths, alias)


# --- Bu bilgisayarın Bluetooth görünürlüğü ---

VISIBLE_SECONDS = 180  # "görünür yap" süresi; BlueZ'un varsayılanı (DiscoverableTimeout)


@dataclass
class BluetoothAdapter:
    """Bu bilgisayarın Bluetooth denetleyicisi (`bluetoothctl show`)."""

    alias: str = ""  # diğer cihazların bu bilgisayarı gördüğü ad
    discoverable: bool = False  # yakındaki cihazlar bulabiliyor mu
    timeout: int | None = None  # görünürlük süresi (sn); 0 = süresiz, None = bilinmiyor
    pairable: bool = True  # eşleştirme isteklerini kabul ediyor mu


def parse_adapter(out: str) -> BluetoothAdapter | None:
    """`bluetoothctl show` çıktısı (bluetoothctl kaynağındaki `print_property` biçimi).

    "Controller AA:… (public)" satırı yoksa (denetleyici yok) None.
    """
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("Controller "):
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        key, sep, value = line.strip().partition(": ")
        if sep and key not in fields:
            fields[key] = value.strip()
    timeout = None
    m = re.search(r"\((\d+)\)", fields.get("DiscoverableTimeout", ""))
    if m:
        timeout = int(m.group(1))
    return BluetoothAdapter(
        alias=fields.get("Alias") or fields.get("Name") or "",
        discoverable=fields.get("Discoverable") == "yes",
        timeout=timeout,
        pairable=fields.get("Pairable", "yes") == "yes",
    )


def bluetooth_adapter_info() -> BluetoothAdapter | None:
    return parse_adapter(_btctl("show")[1])


def bluetooth_set_visible(visible: bool, seconds: int = VISIBLE_SECONDS) -> bool:
    """Bilgisayarı yakındaki cihazlara görünür yapar ya da gizler; sonucu geri okuyup doğrular.

    Görünürlük süresi "süresiz" (0) ayarlıysa `seconds` olarak sınırlanır: açık unutulmasın.
    Eşleştirme kapalıysa açılır (aksi halde telefon bu bilgisayarla eşleşemez).
    """
    info = bluetooth_adapter_info()
    if info is None:
        return False
    if visible:
        if info.timeout == 0:
            _btctl("discoverable-timeout", str(int(seconds)))
        if not info.pairable:
            _btctl("pairable", "on")
    _btctl("discoverable", "on" if visible else "off")
    after = bluetooth_adapter_info()
    return after is not None and after.discoverable == visible


def bluetooth_set_computer_name(name: str) -> tuple[bool, str]:
    """Bu bilgisayarın diğer cihazlarda görünen adını değiştirir (`org.bluez.Adapter1` `Alias`).

    Boş ad, sistemin verdiği ada (bilgisayar adı) döndürür.
    """
    alias = validate_alias(name)
    paths = [f"/org/bluez/{adapter}" for adapter in bluetooth_adapters()]
    return _set_alias("org.bluez.Adapter1", paths, alias)


def bluetooth_scan(timeout: int = 10) -> list[BluetoothDevice]:
    """Yakındaki cihazları `timeout` saniye tarar, sonra listeyi döner."""
    _btctl("--timeout", str(timeout), "scan", "on", timeout=timeout + 10)
    return bluetooth_list_devices()
