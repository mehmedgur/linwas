"""Hotspot (erişim noktası): nmcli çıktı ayrıştırma, doğrulama ve komut üretimi (Qt'siz)."""

import pytest

from linwas.backend import network
from linwas.backend.network import HotspotError, WifiStatus

AP_OUT = "802-11-wireless.mode:ap\n802-11-wireless.ssid:Linwas Evi\n"
STATION_OUT = "802-11-wireless.mode:infrastructure\n802-11-wireless.ssid:Ev\n"


def test_parse_hotspot_only_for_ap_mode():
    info = network.parse_hotspot("Linwas Hotspot", "wlp2s0", AP_OUT)
    assert (info.name, info.ssid, info.device) == ("Linwas Hotspot", "Linwas Evi", "wlp2s0")
    assert network.parse_hotspot("Ev", "wlp2s0", STATION_OUT) is None
    assert network.parse_hotspot("Ev", "wlp2s0", "") is None
    # Ağ adı çıktıda yoksa bağlantı adı kullanılır
    bare = network.parse_hotspot("Bizim", "wlan0", "802-11-wireless.mode:AP\n")
    assert bare is not None and bare.ssid == "Bizim"


def test_parse_hotspot_unescapes_terse_values():
    out = "802-11-wireless.mode:ap\n802-11-wireless.ssid:A\\:B\n"
    assert network.parse_hotspot("x", "wlan0", out).ssid == "A:B"


def test_hotspot_info_queries_active_profile(monkeypatch):
    calls = []

    def fake(cmd, timeout=10):
        calls.append(cmd)
        return AP_OUT, ""

    monkeypatch.setattr(network, "_run", fake)
    status = WifiStatus(enabled=True, connected=True, ssid="Linwas Hotspot", device="wlp2s0")
    info = network.hotspot_info(status)
    assert info is not None and info.ssid == "Linwas Evi" and info.device == "wlp2s0"
    assert calls[0] == [
        "nmcli", "-t", "-f", "802-11-wireless.mode,802-11-wireless.ssid",
        "connection", "show", "id", "Linwas Hotspot",
    ]  # fmt: skip


@pytest.mark.parametrize(
    "status",
    [
        WifiStatus(enabled=True, connected=False, ssid="", device="wlan0"),
        WifiStatus(enabled=True, connected=True, ssid="Ev", device=""),
        WifiStatus(enabled=True, connected=True, ssid="", device="wlan0"),
    ],
)
def test_hotspot_info_needs_connected_named_network(monkeypatch, status):
    monkeypatch.setattr(network, "_run", lambda *a, **k: pytest.fail("çalıştırılmamalı"))
    assert network.hotspot_info(status) is None


@pytest.mark.parametrize(
    ("ssid", "password", "code"),
    [
        ("", "sifre1234", "bad_ssid"),
        ("a" * 33, "sifre1234", "bad_ssid"),
        ("ğ" * 17, "sifre1234", "bad_ssid"),  # 17 harf = 34 bayt
        ("Ağ\nadı", "sifre1234", "bad_ssid"),
        ("Ev", "kısa", "bad_password"),
        ("Ev", "1234567", "bad_password"),
        ("Ev", "a" * 64, "bad_password"),
        ("Ev", "şifre-uzun-12", "bad_password"),  # ASCII dışı karakter
        ("Ev", "bosluk\tvar123", "bad_password"),
    ],
)
def test_validate_hotspot_rejects(ssid, password, code):
    with pytest.raises(HotspotError) as err:
        network.validate_hotspot(ssid, password)
    assert err.value.code == code


@pytest.mark.parametrize(
    ("ssid", "password"),
    [("Ev", "12345678"), ("ğ" * 16, "a b c d e f g"), ("x" * 32, "p" * 63)],
)
def test_validate_hotspot_accepts_limits(ssid, password):
    network.validate_hotspot(ssid, password)


def test_default_ssid_fits_in_32_bytes(monkeypatch):
    monkeypatch.setattr(network.os, "uname", lambda: type("U", (), {"nodename": "ğ" * 40})())
    ssid = network.default_hotspot_ssid()
    assert 0 < len(ssid.encode("utf-8")) <= 32
    monkeypatch.setattr(network.os, "uname", lambda: type("U", (), {"nodename": ""})())
    assert network.default_hotspot_ssid() == "Linwas"


def test_generated_password_is_valid_and_unambiguous():
    seen = set()
    for _ in range(50):
        password = network.generate_hotspot_password()
        network.validate_hotspot("Ev", password)
        assert len(password) == 12 and set(password) <= set(network._PASSWORD_ALPHABET)
        assert not set(password) & set("lo01iIO")
        seen.add(password)
    assert len(seen) > 40  # rastgele
    assert len(network.generate_hotspot_password(20)) == 20


def test_hotspot_start_replaces_old_profile_then_creates(monkeypatch):
    calls = []

    def fake(cmd, timeout=30):
        calls.append(cmd)
        return 0, "Device 'wlp2s0' successfully activated"

    monkeypatch.setattr(network, "_run_rc", fake)
    ok, out = network.hotspot_start("wlp2s0", "Linwas Evi", "gizli-sifre-1")
    assert ok and "activated" in out
    assert calls[0] == ["nmcli", "connection", "delete", "id", "Linwas Hotspot"]
    assert calls[1] == [
        "nmcli", "device", "wifi", "hotspot", "ifname", "wlp2s0",
        "con-name", "Linwas Hotspot", "ssid", "Linwas Evi", "password", "gizli-sifre-1",
    ]  # fmt: skip
    assert all(isinstance(part, str) for call in calls for part in call)  # kabuk yok


def test_hotspot_start_failure_and_validation(monkeypatch):
    results = iter([(1, "Error: yok"), (4, "Error: Connection activation failed")])
    monkeypatch.setattr(network, "_run_rc", lambda cmd, timeout=30: next(results))
    ok, out = network.hotspot_start("wlan0", "Ev", "12345678")
    assert not ok and "activation failed" in out

    monkeypatch.setattr(network, "_run_rc", lambda *a, **k: pytest.fail("çalıştırılmamalı"))
    with pytest.raises(HotspotError):
        network.hotspot_start("wlan0", "", "12345678")  # geçersiz değer komuta ulaşmaz
    assert network.hotspot_start("", "Ev", "12345678") == (False, "no Wi-Fi device")


def test_hotspot_stop(monkeypatch):
    calls = []

    def fake(cmd, timeout=30):
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(network, "_run_rc", fake)
    assert network.hotspot_stop("Linwas Hotspot") is True
    assert calls == [["nmcli", "connection", "down", "id", "Linwas Hotspot"]]
    monkeypatch.setattr(network, "_run_rc", lambda cmd, timeout=30: (1, "hata"))
    assert network.hotspot_stop("Linwas Hotspot") is False


def test_hotspot_defaults_reuse_the_previous_profile(monkeypatch):
    monkeypatch.setattr(network, "_nmcli", lambda *a, **k: AP_OUT)
    monkeypatch.setattr(network, "wifi_password", lambda name: "eski-sifre-1")
    assert network.hotspot_defaults() == ("Linwas Evi", "eski-sifre-1")


def test_hotspot_defaults_suggest_new_values(monkeypatch):
    monkeypatch.setattr(network.os, "uname", lambda: type("U", (), {"nodename": "virci"})())
    # Profil yok → öneri
    monkeypatch.setattr(network, "_nmcli", lambda *a, **k: "")
    ssid, password = network.hotspot_defaults()
    assert ssid == "virci"
    network.validate_hotspot(ssid, password)
    # Profil var ama şifresi okunamıyor → yine öneri (eski ad kullanılmaz: ad+şifre birlikte gider)
    monkeypatch.setattr(network, "_nmcli", lambda *a, **k: AP_OUT)
    monkeypatch.setattr(network, "wifi_password", lambda name: None)
    ssid, password = network.hotspot_defaults()
    assert ssid == "virci"
    network.validate_hotspot(ssid, password)
