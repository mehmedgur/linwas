# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Ağ teşhisi: "internet yok" sorununun nedenini katman katman bulur (root gerekmez).

Sıra donanımdan internete doğrudur; ilk bozuk katman tanı olur, çünkü üstündekiler zaten
ondan dolayı çalışmaz:

  ağ kartı/sürücü → NetworkManager servisi → ağ kapalı mı → Wi-Fi anahtarı (rfkill) →
  bağlantı (kablo, Wi-Fi, yönetilmeyen kart) → IP adresi (DHCP) → varsayılan yol →
  adres çakışması (Docker/sanal makine ağı) → ağ geçidi (modem) → oturum açma sayfası →
  DNS → internet (VPN) → vekil sunucu

Komutlar `run` ile çalıştırılır (testte sahtesi verilir). Ağ ölçümleri `netquality`'den.
"""

from __future__ import annotations

import configparser
import ipaddress
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from linwas.backend import netquality

Runner = Callable[..., tuple[int, str]]

# DNS'ten bağımsız internet denemesi: iki ayrı sağlayıcının herkese açık adresleri
_IP_TARGETS = (("1.1.1.1", 443), ("9.9.9.9", 443))
_LINK_LOCAL = ipaddress.ip_network("169.254.0.0/16")
_WEAK_SIGNAL = 30
_VPN_TYPES = ("tun", "wireguard", "vpn", "ppp")


@dataclass
class NetFinding:
    cause: str  # "ok" ya da tanı kodu (arayüz çevirir)
    detail: str = ""  # ham teknik ayrıntı (İngilizce)
    target: str = ""  # düzeltmenin uygulanacağı aygıt/bağlantı adı


@dataclass
class Adapter:
    name: str
    kind: str  # "wifi" | "ethernet"
    carrier: bool | None  # kablo takılı mı (yalnızca ethernet; bilinmiyorsa None)


@dataclass
class NmDevice:
    name: str
    type: str
    state: str
    connection: str


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


# --- Donanım ---


def list_adapters(sysfs: Path = Path("/sys")) -> list[Adapter]:
    """Gerçek ağ kartları (Wi-Fi, Ethernet); sanal arayüzler (docker, köprü, VPN) sayılmaz."""
    adapters: list[Adapter] = []
    net = sysfs / "class" / "net"
    try:
        entries = sorted(net.iterdir())
    except OSError:
        return adapters
    for iface in entries:
        if not (iface / "device").exists():
            continue
        if (iface / "wireless").exists() or (iface / "phy80211").exists():
            adapters.append(Adapter(iface.name, "wifi", None))
        elif _read(iface / "type") == "1":  # ARPHRD_ETHER
            carrier = _read(iface / "carrier")
            adapters.append(Adapter(iface.name, "ethernet", carrier == "1" if carrier else None))
    return adapters


def network_controllers_without_driver(sysfs: Path = Path("/sys")) -> list[str]:
    """Sürücüsü yüklenmemiş PCI ağ denetleyicileri ("üretici:aygıt" kimlikleri)."""
    found: list[str] = []
    for dev in sorted((sysfs / "bus" / "pci" / "devices").glob("*")):
        # Sınıf 0x02xxxx = ağ denetleyicisi (Ethernet 0x0200, Wi-Fi 0x0280)
        if _read(dev / "class").startswith("0x02") and not (dev / "driver").exists():
            vendor, device = _read(dev / "vendor"), _read(dev / "device")
            found.append(f"{vendor.removeprefix('0x')}:{device.removeprefix('0x')}")
    return found


def wifi_rfkill(sysfs: Path = Path("/sys")) -> tuple[bool, bool]:
    """(donanımsal engel, yazılımsal engel) — herhangi bir Wi-Fi rfkill aygıtında."""
    hard = soft = False
    for dev in (sysfs / "class" / "rfkill").glob("rfkill*"):
        if _read(dev / "type") != "wlan":
            continue
        hard = hard or _read(dev / "hard") == "1"
        soft = soft or _read(dev / "soft") == "1"
    return hard, soft


# --- NetworkManager ---


def parse_devices(out: str) -> list[NmDevice]:
    """`nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device` çıktısı."""
    from linwas.backend.network import split_terse, unescape_terse

    devices = []
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) >= 4:
            name, kind, state, conn = (unescape_terse(p) for p in parts[:4])
            devices.append(NmDevice(name, kind, state, conn))
    return devices


def ifupdown_manages(names: list[str], path: Path = Path("/etc/network/interfaces")) -> list[str]:
    """/etc/network/interfaces'te tanımlı kartlar (NetworkManager bunları yönetmez)."""
    text = _read(path)
    return [
        n
        for n in names
        if re.search(rf"^\s*(iface|auto|allow-hotplug)\s.*\b{re.escape(n)}\b", text, re.M)
    ]


# --- IP katmanı ---


def parse_ipv4(out: str) -> dict[str, list[ipaddress.IPv4Interface]]:
    """`ip -4 -o addr show` → {arayüz: [adres/önek]}."""
    result: dict[str, list[ipaddress.IPv4Interface]] = {}
    for line in out.splitlines():
        m = re.match(r"\d+:\s+(\S+)\s+inet\s+(\S+)", line)
        if m:
            try:
                result.setdefault(m.group(1), []).append(ipaddress.IPv4Interface(m.group(2)))
            except ValueError:
                continue
    return result


def parse_default_route(out: str) -> tuple[str, str]:
    """`ip route show default` → (ağ geçidi, arayüz); ilk (en düşük metrikli) satır."""
    for line in out.splitlines():
        gw = re.search(r"\bvia\s+(\S+)", line)
        dev = re.search(r"\bdev\s+(\S+)", line)
        if dev:
            return (gw.group(1) if gw else ""), dev.group(1)
    return "", ""


def subnet_conflict(
    addrs: dict[str, list[ipaddress.IPv4Interface]], device: str, gateway: str, physical: set[str]
) -> str:
    """Sanal bir ağ (Docker, sanal makine) ev ağıyla aynı adres aralığındaysa onun adı.

    Böyle olunca modeme giden paketler sanal ağa gider; internet yok görünür.
    """
    try:
        gw = ipaddress.ip_address(gateway) if gateway else None
    except ValueError:
        gw = None
    own = [a.network for a in addrs.get(device, [])]
    for name, items in addrs.items():
        if name in physical or name == device or name == "lo":
            continue
        for item in items:
            if (gw is not None and gw in item.network) or any(
                item.network.overlaps(n) for n in own
            ):
                return name
    return ""


# --- Vekil sunucu ---


def configured_proxy(home: Path | None = None) -> tuple[str, int] | None:
    """Sistemde ayarlı HTTP(S) vekil sunucusu: ortam değişkeni, GNOME ya da KDE."""
    home = home or Path.home()
    for var in ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY"):
        if parsed := _host_port(os.environ.get(var, "")):
            return parsed
    if shutil.which("gsettings"):
        code, mode = _run(["gsettings", "get", "org.gnome.system.proxy", "mode"], timeout=5)
        if code == 0 and mode.strip("'") == "manual":
            _, host = _run(["gsettings", "get", "org.gnome.system.proxy.https", "host"], timeout=5)
            _, port = _run(["gsettings", "get", "org.gnome.system.proxy.https", "port"], timeout=5)
            host = host.strip("'")
            if host and port.isdigit() and int(port):
                return host, int(port)
    kde = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        kde.read(home / ".config" / "kioslaverc", encoding="utf-8")
    except (configparser.Error, OSError):
        return None
    section = "Proxy Settings"
    if kde.has_section(section) and kde.get(section, "ProxyType", fallback="0") == "1":
        value = kde.get(section, "httpsProxy", fallback="") or kde.get(
            section, "httpProxy", fallback=""
        )
        # KDE "http://host:port" ya da "host port" yazar
        return _host_port(value.replace(" ", ":"))
    return None


def _host_port(value: str) -> tuple[str, int] | None:
    m = re.match(r"^(?:\w+://)?(?:[^@/]*@)?\[?([^\]/:]+)\]?:(\d+)", value.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def proxy_problem() -> NetFinding | None:
    proxy = configured_proxy()
    if proxy is None:
        return None
    ok, _ = netquality.tcp_connect(proxy[0], proxy[1], timeout=4.0)
    return None if ok else NetFinding("proxy_down", f"{proxy[0]}:{proxy[1]}")


# --- Teşhis ---


def diagnose(run: Runner = _run, sysfs: Path = Path("/sys")) -> NetFinding:
    adapters = list_adapters(sysfs)
    if not adapters:
        missing = network_controllers_without_driver(sysfs)
        if missing:
            return NetFinding("no_driver", ", ".join(missing))
        return NetFinding("no_adapter")
    physical = {a.name for a in adapters}

    devices: list[NmDevice] = []
    if shutil.which("nmcli"):
        _, active = run(["systemctl", "is-active", "NetworkManager"])
        if active.strip() != "active":
            _, enabled = run(["systemctl", "is-enabled", "NetworkManager"])
            return NetFinding("nm_stopped", f"active={active.strip()} enabled={enabled.strip()}")
        _, state = run(["nmcli", "networking"])
        if state.strip() == "disabled":
            return NetFinding("networking_off")
        _, out = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"])
        devices = parse_devices(out)

    _, addr_out = run(["ip", "-4", "-o", "addr", "show"])
    addrs = parse_ipv4(addr_out)
    _, route_out = run(["ip", "route", "show", "default"])
    gateway, route_dev = parse_default_route(route_out)

    connected = [d for d in devices if d.name in physical and d.state.startswith("connected")]
    # NetworkManager yoksa (ör. systemd-networkd) adresi olan gerçek kart bağlı sayılır
    if not devices:
        connected = [NmDevice(n, "", "connected", "") for n in physical if addrs.get(n)]

    if not connected:
        finding = _not_connected(adapters, devices, sysfs, run)
        if finding:
            return finding

    names = [d.name for d in connected]
    device = route_dev if route_dev in names else (names[0] if names else route_dev)

    usable = [a for a in addrs.get(device, []) if a.ip not in _LINK_LOCAL]
    if not usable:
        # 169.254.x.x: modemden adres alınamadı, kart kendine adres verdi
        detail = ", ".join(str(a) for a in addrs.get(device, [])) or "no IPv4 address"
        return NetFinding("no_address", detail, device)
    if not gateway:
        return NetFinding("no_route", str(usable[0]), device)

    clash = subnet_conflict(addrs, device, gateway, physical)
    if clash:
        return NetFinding("subnet_conflict", f"{clash} overlaps {usable[0].network}", clash)

    gw_ping = netquality.ping(gateway, count=3)
    if gw_ping.available and gw_ping.received == 0:
        wifi = device in {a.name for a in adapters if a.kind == "wifi"}
        if wifi and devices and is_weak(device, run):
            return NetFinding("weak_signal", gateway, device)
        return NetFinding("gateway_down", gateway, device)

    nm_state = netquality.nm_connectivity() if devices else "unknown"
    if nm_state == "portal":
        return NetFinding("portal", "", device)

    dns_ok, _, _ = netquality.resolve(netquality.TEST_HOST)
    ip_ok = any(netquality.tcp_connect(host, port)[0] for host, port in _IP_TARGETS)
    vpn = next(
        (d for d in devices if d.type in _VPN_TYPES and d.state.startswith("connected")), None
    )
    if not ip_ok:
        if vpn is not None:
            return NetFinding("vpn_blocking", vpn.name, vpn.connection or vpn.name)
        return NetFinding("internet_down", f"gateway {gateway} answers", device)
    if not dns_ok:
        return NetFinding("dns_failed", _nameservers(), device)

    return proxy_problem() or NetFinding("ok", nm_state, device)


def _not_connected(
    adapters: list[Adapter], devices: list[NmDevice], sysfs: Path, run: Runner
) -> NetFinding | None:
    physical = {a.name for a in adapters}
    ours = [d for d in devices if d.name in physical]
    unmanaged = [d.name for d in ours if d.state == "unmanaged"]
    if ours and len(unmanaged) == len(ours):
        managed_by = ifupdown_manages(unmanaged)
        detail = ", ".join(unmanaged) + (" (/etc/network/interfaces)" if managed_by else "")
        return NetFinding("unmanaged", detail, unmanaged[0])
    connecting = next((d for d in ours if d.state.startswith("connecting")), None)
    if connecting:
        return NetFinding("getting_address", connecting.state, connecting.name)

    wifi = [a for a in adapters if a.kind == "wifi"]
    ethernet = [a for a in adapters if a.kind == "ethernet"]
    if ethernet and any(a.carrier for a in ethernet):
        # Kablo takılı ama bağlanmamış
        name = next(a.name for a in ethernet if a.carrier)
        return NetFinding("ethernet_not_connected", name, name)
    if wifi:
        hard, soft = wifi_rfkill(sysfs)
        if hard:
            return NetFinding("wifi_hard_blocked", wifi[0].name)
        _, radio = run(["nmcli", "radio", "wifi"]) if devices else (0, "enabled")
        if soft or radio.strip() == "disabled":
            return NetFinding("wifi_off", wifi[0].name)
        return NetFinding("wifi_not_connected", wifi[0].name, wifi[0].name)
    if ethernet:
        return NetFinding("cable_unplugged", ", ".join(a.name for a in ethernet))
    return None


def _nameservers(path: Path = Path("/etc/resolv.conf")) -> str:
    servers = re.findall(r"^\s*nameserver\s+(\S+)", _read(path), re.M)
    return "nameservers: " + (", ".join(servers) if servers else "none in /etc/resolv.conf")


def signal_of(device: str, run: Runner = _run) -> int | None:
    """Bağlı Wi-Fi ağının sinyali (0–100)."""
    _, out = run(
        [
            "nmcli",
            "-t",
            "-f",
            "IN-USE,SIGNAL",
            "device",
            "wifi",
            "list",
            "ifname",
            device,
            "--rescan",
            "no",
        ]
    )
    for line in out.splitlines():
        if line.startswith("*:"):
            value = line.split(":", 1)[1]
            return int(value) if value.isdigit() else None
    return None


def is_weak(device: str, run: Runner = _run) -> bool:
    signal = signal_of(device, run)
    return signal is not None and signal < _WEAK_SIGNAL


# --- Düzeltmeler (kullanıcı yetkisiyle; root gerekmez, NetworkManager polkit'le izin verir) ---


def networking_on(run: Runner = _run) -> bool:
    return run(["nmcli", "networking", "on"])[0] == 0


def wifi_on(run: Runner = _run) -> bool:
    return run(["nmcli", "radio", "wifi", "on"])[0] == 0


def reconnect(device: str, run: Runner = _run) -> bool:
    """Kartı yeniden bağlar: yeni adres ister (DHCP), modemle bağlantıyı tazeler."""
    if not re.fullmatch(r"[\w.:-]{1,15}", device):
        return False
    return run(["nmcli", "device", "connect", device], timeout=45)[0] == 0


def vpn_down(connection: str, run: Runner = _run) -> bool:
    if not connection or connection.startswith("-"):
        return False
    return run(["nmcli", "connection", "down", "id", connection], timeout=30)[0] == 0
