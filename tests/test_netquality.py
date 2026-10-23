"""Bağlantı testi, ping ayrıştırma, Wi-Fi örnekleme ve arka plan örnekleyici (Qt'siz)."""

import time

import pytest

from linwas.backend import netquality as nq
from linwas.backend import network
from linwas.core import app_settings, netlog, user_data

PING_OK = """PING 192.168.1.1 (192.168.1.1) 56(84) bytes of data.
64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=2.31 ms
64 bytes from 192.168.1.1: icmp_seq=2 ttl=64 time=1.87 ms
64 bytes from 192.168.1.1: icmp_seq=3 ttl=64 time=3.02 ms

--- 192.168.1.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 804ms
"""


@pytest.fixture
def fake_run(monkeypatch):
    """network._run yerine: (stdout, stderr) döndürür; çağrıları kaydeder."""
    state = {"out": PING_OK, "err": "", "calls": []}

    def run(cmd, timeout=10):
        state["calls"].append(cmd)
        return state["out"], state["err"]

    monkeypatch.setattr(network, "_run", run)
    monkeypatch.setattr(nq.shutil, "which", lambda name: "/bin/" + name)
    return state


def test_ping_parses_reply_lines_and_builds_safe_command(fake_run):
    result = nq.ping("192.168.1.1")
    assert (result.available, result.sent, result.received) == (True, 3, 3)
    assert result.avg_ms == pytest.approx((2.31 + 1.87 + 3.02) / 3)
    assert result.loss == 0
    cmd = fake_run["calls"][0]
    assert cmd == ["ping", "-n", "-c", "3", "-i", "0.4", "-W", "1.0", "192.168.1.1"]


def test_ping_partial_and_total_loss(fake_run):
    fake_run["out"] = "64 bytes from 10.0.0.1: icmp_seq=2 ttl=64 time=40.5 ms\n"
    partial = nq.ping("10.0.0.1")
    assert (partial.received, partial.loss) == (1, pytest.approx(2 / 3))
    fake_run["out"] = (
        "PING 10.0.0.1\n\n--- 10.0.0.1 ping statistics ---\n3 packets transmitted, 0 received\n"
    )
    none = nq.ping("10.0.0.1")
    assert (none.available, none.received, none.loss, none.avg_ms) == (True, 0, 1.0, None)


def test_ping_unavailable_cases(fake_run, monkeypatch):
    fake_run["out"], fake_run["err"] = "", "ping: socket: Operation not permitted"
    assert nq.ping("192.168.1.1").available is False
    # Seçenek enjeksiyonu ve ad: yalnızca IP adresi kabul edilir; komut çalıştırılmaz
    fake_run["calls"].clear()
    for bad in ("-c9", "example.com", "", "1.2.3"):
        assert nq.ping(bad).available is False
    assert fake_run["calls"] == []
    monkeypatch.setattr(nq.shutil, "which", lambda name: None)
    assert nq.ping("192.168.1.1").available is False


def test_resolve_and_tcp(monkeypatch):
    monkeypatch.setattr(
        nq.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )
    ok, ms, addr = nq.resolve("example.com")
    assert ok and addr == "93.184.216.34" and ms is not None

    def boom(*a, **k):
        raise nq.socket.gaierror("yok")

    monkeypatch.setattr(nq.socket, "getaddrinfo", boom)
    assert nq.resolve("example.com") == (False, None, "")

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(nq.socket, "create_connection", lambda *a, **k: Conn())
    ok, ms = nq.tcp_connect("93.184.216.34")
    assert ok and ms is not None

    def refuse(*a, **k):
        raise ConnectionRefusedError

    monkeypatch.setattr(nq.socket, "create_connection", refuse)
    assert nq.tcp_connect("93.184.216.34") == (False, None)


@pytest.mark.parametrize(
    ("out", "state"),
    [
        ("full\n", "full"),
        ("portal", "portal"),
        ("LIMITED", "limited"),
        ("garip", "unknown"),
        ("", "unknown"),
    ],
)
def test_nm_connectivity_normalizes(fake_run, out, state):
    fake_run["out"] = out
    assert nq.nm_connectivity() == state
    assert fake_run["calls"][-1] == ["nmcli", "networking", "connectivity", "check"]


GOOD = nq.PingResult(True, 3, 3, [2.0, 2.0, 2.0])
DOWN = nq.PingResult(True, 3, 0, [])
LOSSY = nq.PingResult(True, 3, 1, [5.0])
SLOW = nq.PingResult(True, 3, 3, [300.0, 300.0, 300.0])


@pytest.mark.parametrize(
    ("gateway", "gw", "nm", "dns", "net", "expected"),
    [
        ("", None, "full", True, True, "no_address"),
        ("10.0.0.1", DOWN, "full", True, True, "gateway_down"),
        ("10.0.0.1", LOSSY, "full", True, True, "gateway_lossy"),
        ("10.0.0.1", GOOD, "portal", False, None, "portal"),
        ("10.0.0.1", GOOD, "limited", False, None, "dns_failed"),
        ("10.0.0.1", GOOD, "limited", True, False, "internet_down"),
        ("10.0.0.1", SLOW, "full", True, True, "slow"),
        ("10.0.0.1", GOOD, "full", True, True, "ok"),
        # ping yok: ağ geçidi hakkında yorum yapılmaz, sonuç diğer adımlardan çıkar
        ("10.0.0.1", nq.PingResult(False), "full", True, True, "ok"),
        ("10.0.0.1", None, "unknown", True, False, "internet_down"),
    ],
)
def test_diagnose(gateway, gw, nm, dns, net, expected):
    assert nq.diagnose(gateway, gw, nm, dns, net) == expected


def test_run_connectivity_test_orders_steps_and_reports(monkeypatch):
    order = []
    monkeypatch.setattr(nq, "ping", lambda host: order.append("ping") or GOOD)
    monkeypatch.setattr(nq, "nm_connectivity", lambda: order.append("nm") or "full")
    monkeypatch.setattr(nq, "resolve", lambda host: order.append("dns") or (True, 12.0, "1.2.3.4"))
    monkeypatch.setattr(
        nq, "tcp_connect", lambda h, p: order.append(f"tcp:{h}:{p}") or (True, 30.0)
    )
    report = nq.run_connectivity_test("192.168.1.1")
    assert order == ["ping", "nm", "dns", "tcp:1.2.3.4:443"]
    assert report.diagnosis == "ok" and report.internet_ms == 30.0
    text = report.as_text()
    assert "Gateway ping: 3/3 replies" in text and "Diagnosis: ok" in text

    # DNS çözülmezse TCP denenmez
    order.clear()
    monkeypatch.setattr(nq, "resolve", lambda host: (False, None, ""))
    failed = nq.run_connectivity_test("192.168.1.1")
    assert failed.diagnosis == "dns_failed" and failed.internet_ok is None
    assert not any(step.startswith("tcp") for step in order)
    assert "not tested" in failed.as_text()
    # Ağ geçidi yoksa ping denenmez
    order.clear()
    assert nq.run_connectivity_test("").diagnosis == "no_address" and "ping" not in order


def fake_nmcli(table):
    def nmcli(*args, timeout=10):
        for key, value in table.items():
            if key in args or key in " ".join(args):
                return value
        return ""

    return nmcli


def test_collect_wifi_sample_connected(monkeypatch):
    table = {
        "WIFI": "enabled\n",
        "DEVICE,TYPE,STATE,CONNECTION": "wlan0:wifi:connected:Ev Ağı\neth0:ethernet:unavailable:\n",
        "ACTIVE,DEVICE,BSSID,SIGNAL,FREQ": r"yes:wlan0:AA\:00\:00\:00\:00\:01:72:5180 MHz",
        "IP4.GATEWAY": "IP4.GATEWAY:192.168.1.1\n",
    }
    monkeypatch.setattr(network, "_nmcli", fake_nmcli(table))
    monkeypatch.setattr(nq, "ping", lambda host: nq.PingResult(True, 3, 3, [2.0, 4.0, 3.0]))
    s = nq.collect_wifi_sample(now=1000)
    assert (s.ts, s.kind, s.name, s.ident, s.connected) == (
        1000,
        "wifi",
        "Ev Ağı",
        "AA:00:00:00:00:01",
        True,
    )
    assert (s.signal, s.band, s.rtt_ms, s.loss) == (72, "5", 3.0, 0.0)


def test_collect_wifi_sample_variants(monkeypatch):
    base = {
        "WIFI": "enabled\n",
        "DEVICE,TYPE,STATE,CONNECTION": "wlan0:wifi:disconnected:\n",
    }
    monkeypatch.setattr(network, "_nmcli", fake_nmcli(base))
    s = nq.collect_wifi_sample(now=5)
    assert (s.connected, s.name, s.ts) == (False, "", 5)  # radyo açık, bağlı değil: kopuk örneği
    monkeypatch.setattr(network, "_nmcli", fake_nmcli({**base, "WIFI": "disabled\n"}))
    assert nq.collect_wifi_sample(now=5) is None  # radyo kapalı: boşluk
    monkeypatch.setattr(network, "_nmcli", fake_nmcli({"WIFI": "enabled\n"}))
    assert nq.collect_wifi_sample(now=5) is None  # Wi-Fi kartı yok
    connected = {
        "WIFI": "enabled\n",
        "DEVICE,TYPE,STATE,CONNECTION": "wlan0:wifi:connected:Ev\n",
        "ACTIVE,DEVICE,BSSID,SIGNAL,FREQ": r"yes:wlan0:AA\:00:60:2412 MHz",
        "IP4.GATEWAY": "IP4.GATEWAY:10.0.0.1\n",
    }
    monkeypatch.setattr(network, "_nmcli", fake_nmcli(connected))
    monkeypatch.setattr(nq, "ping", lambda host: nq.PingResult(False))
    no_ping = nq.collect_wifi_sample(now=5)
    assert (no_ping.rtt_ms, no_ping.loss, no_ping.band) == (None, None, "2.4")


def test_note_user_action_requires_consent(monkeypatch):
    written = []
    monkeypatch.setattr(netlog, "append", lambda sample, path=None: written.append(sample))
    monkeypatch.setattr(
        app_settings, "load", lambda path=None: app_settings.AppSettings(net_measure=False)
    )
    nq.note_user_action("wifi", "Ev")
    assert written == []
    monkeypatch.setattr(
        app_settings, "load", lambda path=None: app_settings.AppSettings(net_measure=True)
    )
    nq.note_user_action("wifi", "Ev")
    assert [(s.name, s.connected, s.user) for s in written] == [("Ev", False, True)]


def test_sampler_swallows_errors_and_stores_samples():
    stored = []

    def broken():
        raise RuntimeError("x")

    good = netlog.Sample(ts=1, kind="wifi", name="Ev")
    sampler = nq.Sampler(
        collectors=[broken, lambda: good, lambda: None, lambda: [good, "çöp"]], store=stored.append
    )
    sampler.sample_once()
    assert stored == [good, good]


def test_sampler_thread_start_stop_restart():
    stored = []
    sample = netlog.Sample(ts=1, kind="wifi", name="Ev")
    sampler = nq.Sampler(interval=0.05, collectors=[lambda: sample], store=stored.append)
    assert not sampler.running
    sampler.set_enabled(True)
    sampler.start()  # ikinci çağrı yeni iş parçacığı başlatmaz
    deadline = time.time() + 3
    while len(stored) < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert sampler.running and len(stored) >= 2
    sampler.set_enabled(False)
    assert not sampler.running
    time.sleep(0.2)
    count = len(stored)
    time.sleep(0.2)
    assert len(stored) == count  # durdu
    sampler.set_enabled(True)  # tekrar açılabilir
    assert sampler.running
    sampler.stop()


def test_settings_and_user_data_integration():
    assert app_settings.AppSettings().net_measure is False
    assert app_settings.from_dict({"net_measure": True}).net_measure is True
    assert app_settings.from_dict({"net_measure": "evet"}).net_measure is False
    item = next(i for i in user_data.items() if i.key == "network")
    assert item.path.name == netlog.FILE_NAME
