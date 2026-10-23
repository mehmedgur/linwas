"""Ağ bağlantı testi ve arka plan kalite örnekleyicisi. Qt'ye bağımlı değildir.

Bağlantı testi yalnızca kullanıcı "Bağlantıyı test et"e basınca çalışır: yerel ağ geçidine ping, bir
ad çözümleme ve bir TCP bağlantısı (hedef `TEST_HOST`, IANA'nın belge alan adı). Örnekleyici
yalnızca açık rıza (`app_settings.net_measure`) varken çalışır ve dakikada bir **yalnızca yerel ağ
geçidine** ping atar, eşleşmiş Bluetooth cihazlarının durumunu (bağlı mı, pil) okur; dışarıya hiçbir
şey gönderilmez. Komutlar: nmcli (NetworkManager) ve ping
(iputils); seçenekler resmi belgelerden doğrulandı (ping: -n -c -i -W; nmcli networking
connectivity: full/limited/portal/none/unknown).
"""

from __future__ import annotations

import ipaddress
import re
import shutil
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from linwas.backend import network
from linwas.core import app_settings, netlog

TEST_HOST = "example.com"
TEST_PORT = 443
PING_COUNT = 3
PING_INTERVAL = 0.4  # sn; iputils: yetkisiz kullanıcı için alt sınır eski sürümlerde 0,2 sn
PING_TIMEOUT = 1.0  # sn (-W)
LOSSY_THRESHOLD = 0.3  # ağ geçidine giden denemelerin bu orandan fazlası kayıpsa "kararsız"
PRUNE_EVERY = 6 * 3600  # sn

# Cevap satırındaki süre: "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=2.31 ms"
_RE_TIME = re.compile(r"time[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms")


# --- Ping ---


@dataclass
class PingResult:
    available: bool  # ping aracı var ve çalıştırılabildi
    sent: int = 0
    received: int = 0
    rtts: list[float] = field(default_factory=list)

    @property
    def loss(self) -> float | None:
        return None if not self.sent else 1 - self.received / self.sent

    @property
    def avg_ms(self) -> float | None:
        return sum(self.rtts) / len(self.rtts) if self.rtts else None


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def ping(host: str, count: int = PING_COUNT) -> PingResult:
    """`host` (yalnızca IP adresi) için `count` ping; süreleri cevap satırlarından okur.

    Özet satırının biçimine bağlı değildir. Ping yoksa ya da izin verilmiyorsa (kapsayıcı)
    `available=False`.
    """
    if not _is_ip(host) or shutil.which("ping") is None:
        return PingResult(available=False)
    cmd = [
        "ping",
        "-n",
        "-c",
        str(count),
        "-i",
        str(PING_INTERVAL),
        "-W",
        str(PING_TIMEOUT),
        host,
    ]
    out, err = network._run(cmd, timeout=int(count * (PING_INTERVAL + PING_TIMEOUT)) + 4)
    rtts = [float(m.group(1)) for m in _RE_TIME.finditer(out)]
    lowered = err.lower()
    if not rtts and ("not permitted" in lowered or "permission denied" in lowered):
        return PingResult(available=False)
    return PingResult(available=True, sent=count, received=len(rtts), rtts=rtts)


# --- Ad çözümleme ve TCP ---


def resolve(host: str, timeout: float = 3.0) -> tuple[bool, float | None, str]:
    """Sistem çözümleyicisiyle ad çözer: (başarılı, ms, ilk adres)."""
    result: dict[str, str] = {}

    def work() -> None:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            result["addr"] = str(infos[0][4][0]) if infos else ""
        except OSError:
            result["addr"] = ""

    started = time.perf_counter()
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    addr = result.get("addr", "")
    elapsed = (time.perf_counter() - started) * 1000
    return bool(addr), (elapsed if addr else None), addr


def tcp_connect(
    host: str, port: int = TEST_PORT, timeout: float = 4.0
) -> tuple[bool, float | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.perf_counter() - started) * 1000
    except OSError:
        return False, None


def nm_connectivity() -> str:
    """NetworkManager'ın bağlantı denetimi: full | limited | portal | none | unknown."""
    out, _ = network._run(["nmcli", "networking", "connectivity", "check"], timeout=20)
    state = out.strip().lower()
    return state if state in ("full", "limited", "portal", "none", "unknown") else "unknown"


# --- Bağlantı testi ---


@dataclass
class ConnectivityReport:
    gateway: str
    gateway_ping: PingResult | None = None
    nm_state: str = "unknown"
    dns_ok: bool | None = None  # None: denenmedi
    dns_ms: float | None = None
    dns_addr: str = ""
    internet_ok: bool | None = None
    internet_ms: float | None = None
    diagnosis: str = "ok"

    def as_text(self) -> str:
        """Asistana göndermek için düz metin özeti (İngilizce, tanılama amaçlı)."""
        gw = self.gateway_ping
        lines = [f"Gateway: {self.gateway or '(none)'}"]
        if gw is not None and gw.available:
            lines.append(
                f"Gateway ping: {gw.received}/{gw.sent} replies"
                + (f", average {gw.avg_ms:.1f} ms" if gw.avg_ms is not None else "")
            )
        elif gw is not None:
            lines.append("Gateway ping: ping tool not available")
        lines.append(f"NetworkManager connectivity: {self.nm_state}")
        lines.append(f"DNS lookup of {TEST_HOST}: {_yes_no(self.dns_ok)}")
        lines.append(f"TCP {TEST_PORT} to {TEST_HOST}: {_yes_no(self.internet_ok)}")
        lines.append(f"Diagnosis: {self.diagnosis}")
        return "\n".join(lines)


def _yes_no(value: bool | None) -> str:
    return "not tested" if value is None else ("ok" if value else "failed")


def diagnose(
    gateway: str,
    gw: PingResult | None,
    nm_state: str,
    dns_ok: bool | None,
    internet_ok: bool | None,
) -> str:
    """Test sonucundan tek bir tanı kodu: ok | no_address | gateway_down | gateway_lossy |
    portal | dns_failed | internet_down | slow."""
    if not gateway:
        return "no_address"
    if gw is not None and gw.available:
        if gw.received == 0:
            return "gateway_down"
        if (gw.loss or 0.0) >= LOSSY_THRESHOLD:
            return "gateway_lossy"
    if nm_state == "portal":
        return "portal"
    if dns_ok is False:
        return "dns_failed"
    if internet_ok is False:
        return "internet_down"
    if gw is not None and gw.available and (gw.avg_ms or 0.0) > netlog.FAIR_RTT_MS:
        return "slow"
    return "ok"


def run_connectivity_test(gateway: str) -> ConnectivityReport:
    """Sırayla: ağ geçidi pingi → NetworkManager denetimi → ad çözümleme → TCP bağlantısı."""
    report = ConnectivityReport(gateway=gateway)
    if gateway:
        report.gateway_ping = ping(gateway)
    report.nm_state = nm_connectivity()
    report.dns_ok, report.dns_ms, report.dns_addr = resolve(TEST_HOST)
    if report.dns_ok:
        report.internet_ok, report.internet_ms = tcp_connect(report.dns_addr, TEST_PORT)
    report.diagnosis = diagnose(
        gateway, report.gateway_ping, report.nm_state, report.dns_ok, report.internet_ok
    )
    return report


# --- Arka plan örnekleyici ---


def _active_wifi() -> tuple[str, str, str, int | None, int | None] | None:
    """(aygıt, ağ adı, BSSID, sinyal, frekans MHz) — bağlı değilse ("", ...) boş ağ adı; Wi-Fi
    kapalıysa ya da kart yoksa None."""
    if network._nmcli("-t", "-f", "WIFI", "radio").strip().lower() != "enabled":
        return None
    dev_out = network._nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device")
    device = ssid = ""
    connected = False
    for line in dev_out.splitlines():
        parts = network.split_terse(line)
        if len(parts) >= 4 and parts[1] == "wifi":
            device = parts[0]
            connected = parts[2] == "connected"
            ssid = parts[3] if connected else ""
            break
    if not device:
        return None
    if not connected:
        return device, "", "", None, None
    listing = network._nmcli(
        "-t",
        "-f",
        "ACTIVE,DEVICE,BSSID,SIGNAL,FREQ",
        "device",
        "wifi",
        "list",
        "--rescan",
        "no",
        timeout=30,
    )
    bssid, signal, freq = "", None, None
    for line in listing.splitlines():
        row = network.split_terse(line)
        if len(row) >= 5 and row[0].strip().lower() == "yes" and row[1] == device:
            bssid = row[2]
            signal = network.leading_int(row[3])
            freq = network.leading_int(row[4])
            break
    return device, ssid, bssid, signal, freq


def _gateway_of(device: str) -> str:
    out = network._nmcli("-t", "-f", "IP4.GATEWAY", "device", "show", device)
    return (network.parse_device_show(out).get("IP4.GATEWAY") or [""])[0]


def collect_wifi_sample(now: int | None = None) -> netlog.Sample | None:
    """Tek bir Wi-Fi örneği. Wi-Fi kapalı ya da kart yoksa None (çizelgede boşluk kalır)."""
    ts = int(time.time()) if now is None else now
    active = _active_wifi()
    if active is None:
        return None
    device, ssid, bssid, signal, freq = active
    if not ssid:
        return netlog.Sample(ts=ts, kind=netlog.KIND_WIFI, name="", connected=False)
    if network.is_hotspot(ssid):  # hotspot yayınlarken bir ağa istemci değiliz: ölçülecek geçit yok
        return None
    rtt = loss = None
    gateway = _gateway_of(device)
    if gateway:
        result = ping(gateway)
        if result.available:
            rtt, loss = result.avg_ms, result.loss
    return netlog.Sample(
        ts=ts,
        kind=netlog.KIND_WIFI,
        name=ssid,
        ident=bssid,
        connected=True,
        signal=signal,
        rtt_ms=None if rtt is None else round(rtt, 1),
        loss=None if loss is None else round(loss, 2),
        band=network.band_from_frequency(freq).removesuffix(" GHz"),
    )


def collect_bluetooth_samples(now: int | None = None) -> list[netlog.Sample]:
    """Eşleşmiş cihazların durumu (bağlı mı, sinyal, pil). Bluetooth kapalı/yoksa boş liste."""
    if network.bluetooth_state() != "on":
        return []
    ts = int(time.time()) if now is None else now
    return [
        netlog.Sample(
            ts=ts,
            kind=netlog.KIND_BT,
            name=dev.name,
            ident=dev.mac,
            connected=dev.connected,
            signal=dev.rssi,
            battery=dev.battery,
        )
        for dev in network.bluetooth_list_devices()
        if dev.paired
    ]


def note_user_action(kind: str, name: str, ident: str = "") -> None:
    """Kullanıcı Linwas'tan bağlantıyı kesti/kapattı: kopma sayılmaması için işaret düşer.

    Ölçüm kapalıysa hiçbir şey yazılmaz.
    """
    if not app_settings.load().net_measure:
        return
    netlog.append(
        netlog.Sample(
            ts=int(time.time()), kind=kind, name=name, ident=ident, connected=False, user=True
        )
    )


class Sampler:
    """Dakikada bir örnek alan arka plan iş parçacığı; hiçbir hata uygulamayı düşürmez."""

    def __init__(
        self,
        interval: float = netlog.DEFAULT_INTERVAL,
        collectors: list[Callable[[], object]] | None = None,
        store: Callable[[netlog.Sample], None] = netlog.append,
    ) -> None:
        self._interval = interval
        self._collectors = (
            collectors
            if collectors is not None
            else [collect_wifi_sample, collect_bluetooth_samples]
        )
        self._store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            # Her başlatmada yeni bir durdurma işareti: eski iş parçacığı sonlanırken de güvenli
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._loop, args=(self._stop,), name="linwas-netquality", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self, stop: threading.Event) -> None:
        last_prune = 0.0
        while not stop.is_set():
            if time.monotonic() - last_prune > PRUNE_EVERY:
                netlog.prune()
                last_prune = time.monotonic()
            self.sample_once()
            if stop.wait(self._interval):
                break

    def sample_once(self) -> None:
        for collect in self._collectors:
            try:
                result = collect()
            except Exception:  # örnekleyici hiçbir zaman uygulamayı düşürmemeli
                continue
            items = result if isinstance(result, list) else [result]
            for sample in items:
                if isinstance(sample, netlog.Sample):
                    self._store(sample)


# Uygulama genelinde tek örnekleyici (MainWindow ve Wi-Fi sayfası paylaşır)
SAMPLER = Sampler()
