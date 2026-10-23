"""Kayıtlı Wi-Fi ağ ayarları: nmcli çıktı ayrıştırma, doğrulama ve argüman üretimi (Qt'siz)."""

import pytest

from linwas.backend import network
from linwas.backend.network import ProfileChange, ProfileError, WifiProfile

AUTO = """connection.autoconnect:yes
connection.metered:unknown
ipv4.method:auto
ipv4.addresses:
ipv4.gateway:--
ipv4.dns:
ipv4.ignore-auto-dns:no
"""

MANUAL = """connection.autoconnect:no
connection.metered:yes
ipv4.method:manual
ipv4.addresses:192.168.1.50/24, 10.0.0.2/24
ipv4.gateway:192.168.1.1
ipv4.dns:1.1.1.1,1.0.0.1
ipv4.ignore-auto-dns:yes
"""


def test_parse_profile_auto_and_manual():
    auto = network.parse_profile("Ev", AUTO)
    assert (auto.autoconnect, auto.metered, auto.ipv4_method) == (True, "unknown", "auto")
    assert (auto.address, auto.prefix, auto.gateway, auto.dns) == ("", None, "", [])
    assert auto.dns_choice == "auto" and auto.ip_editable

    manual = network.parse_profile("Ev", MANUAL)
    assert (manual.autoconnect, manual.metered, manual.ipv4_method) == (False, "yes", "manual")
    assert (manual.address, manual.prefix, manual.gateway) == ("192.168.1.50", 24, "192.168.1.1")
    assert manual.dns == ["1.1.1.1", "1.0.0.1"] and manual.ignore_auto_dns
    assert manual.dns_choice == "cloudflare"


def test_parse_profile_tolerates_garbage_and_special_modes():
    odd = network.parse_profile("X", "ipv4.method:shared\nconnection.metered:guess-yes\nbozuk\n")
    assert odd.ipv4_method == "shared" and not odd.ip_editable
    assert odd.metered == "unknown"  # profilde yalnızca unknown/yes/no
    assert network.parse_profile("X", "").ipv4_method == "auto"
    bad = network.parse_profile("X", "ipv4.addresses:belirsiz")
    assert (bad.address, bad.prefix) == ("belirsiz", None)


@pytest.mark.parametrize(
    ("dns", "choice"),
    [
        ([], "auto"),
        (["1.1.1.1", "1.0.0.1"], "cloudflare"),
        (["8.8.8.8", "8.8.4.4"], "google"),
        (["8.8.8.8"], "custom"),
        (["1.0.0.1", "1.1.1.1"], "custom"),  # sıra önemli: elle girilmiş sayılır
    ],
)
def test_dns_choice(dns, choice):
    assert WifiProfile("x", dns=dns).dns_choice == choice


def test_wifi_profile_reads_via_nmcli(monkeypatch):
    calls = []

    def fake(*args, timeout=10):
        calls.append(args)
        return MANUAL

    monkeypatch.setattr(network, "_nmcli", fake)
    profile = network.wifi_profile("Ev Ağı")
    assert profile is not None and profile.address == "192.168.1.50"
    assert calls[0][:3] == ("-t", "-f", network._PROFILE_FIELDS)
    assert calls[0][-3:] == ("connection", "show", "id") or calls[0][-4:] == (
        "connection",
        "show",
        "id",
        "Ev Ağı",
    )
    monkeypatch.setattr(network, "_nmcli", lambda *a, timeout=10: "")
    assert network.wifi_profile("Yok") is None


def test_build_args_basic_switches_only():
    args = network.build_modify_args("Ev Ağı", ProfileChange(autoconnect=False, metered="yes"))
    assert args == [
        "connection",
        "modify",
        "id",
        "Ev Ağı",
        "connection.autoconnect",
        "no",
        "connection.metered",
        "yes",
    ]  # fmt: skip  — IP ve DNS'e dokunulmaz


def test_build_args_dns_choices():
    def dns_args(choice, dns=()):
        return network.build_modify_args(
            "Ev", ProfileChange(autoconnect=True, dns_choice=choice, dns=list(dns))
        )[8:]

    assert dns_args("auto") == ["ipv4.dns", "", "ipv4.ignore-auto-dns", "no"]
    assert dns_args("cloudflare") == ["ipv4.dns", "1.1.1.1 1.0.0.1", "ipv4.ignore-auto-dns", "yes"]
    assert dns_args("google") == ["ipv4.dns", "8.8.8.8 8.8.4.4", "ipv4.ignore-auto-dns", "yes"]
    assert dns_args("custom", ["9.9.9.9", " 149.112.112.112 ", ""]) == [
        "ipv4.dns", "9.9.9.9 149.112.112.112", "ipv4.ignore-auto-dns", "yes",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("dns", "code"),
    [
        ([], "bad_dns"),
        (["abc"], "bad_dns"),
        (["8.8.8.8", "8.8.8.8"], "bad_dns"),
        (["1.1.1.1", "8.8.8.8", "9.9.9.9", "4.4.4.4"], "too_many_dns"),
        (["2001:4860:4860::8888"], "bad_dns"),  # yalnızca IPv4
    ],
)
def test_custom_dns_validation(dns, code):
    change = ProfileChange(autoconnect=True, dns_choice="custom", dns=dns)
    with pytest.raises(ProfileError) as exc:
        network.build_modify_args("Ev", change)
    assert exc.value.code == code


def manual(**kw):
    base = {
        "autoconnect": True,
        "ipv4_method": "manual",
        "address": "192.168.1.50",
        "netmask": "255.255.255.0",
        "gateway": "192.168.1.1",
        "dns_choice": "cloudflare",
    }
    base.update(kw)
    return ProfileChange(**base)


def test_build_args_manual_ip():
    args = network.build_modify_args("Ev", manual())
    assert args[8:] == [
        "ipv4.method", "manual", "ipv4.addresses", "192.168.1.50/24", "ipv4.gateway", "192.168.1.1",
        "ipv4.dns", "1.1.1.1 1.0.0.1", "ipv4.ignore-auto-dns", "yes",
    ]  # fmt: skip
    # Önek sayı olarak da verilebilir; ağ geçidi boş bırakılabilir
    plain = network.build_modify_args("Ev", manual(netmask="16", gateway=""))
    assert "192.168.1.50/16" in plain and plain[plain.index("ipv4.gateway") + 1] == ""


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"address": "300.1.1.1"}, "bad_address"),
        ({"address": ""}, "bad_address"),
        ({"address": "192.168.1.0"}, "bad_address"),  # ağ adresi
        ({"address": "192.168.1.255"}, "bad_address"),  # yayın adresi
        ({"netmask": "255.0.255.0"}, "bad_mask"),
        ({"netmask": "31"}, "bad_mask"),
        ({"netmask": "4"}, "bad_mask"),
        ({"netmask": "abc"}, "bad_mask"),
        ({"gateway": "abc"}, "bad_gateway"),
        ({"gateway": "10.0.0.1"}, "gateway_outside"),
        ({"gateway": "192.168.1.50"}, "gateway_outside"),  # kendisi
        ({"dns_choice": "auto"}, "no_dns"),  # elle IP + otomatik DNS çalışmaz
        ({"dns_choice": None}, "no_dns"),
    ],
)
def test_manual_ip_validation(changes, code):
    with pytest.raises(ProfileError) as exc:
        network.build_modify_args("Ev", manual(**changes))
    assert exc.value.code == code


def test_build_args_auto_clears_manual_values_and_rejects_bad_input():
    args = network.build_modify_args("Ev", ProfileChange(autoconnect=True, ipv4_method="auto"))
    assert args[8:] == ["ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", ""]
    with pytest.raises(ProfileError):
        network.build_modify_args("Ev", ProfileChange(autoconnect=True, metered="garip"))
    with pytest.raises(ProfileError):
        network.build_modify_args("Ev", ProfileChange(autoconnect=True, ipv4_method="shared"))


def test_reconnect_needed():
    old = network.parse_profile("Ev", MANUAL)
    same = manual(dns_choice="cloudflare")
    assert network.reconnect_needed(old, same) is False
    assert network.reconnect_needed(old, manual(address="192.168.1.51")) is True
    assert network.reconnect_needed(old, manual(dns_choice="google")) is True
    assert network.reconnect_needed(old, manual(gateway="192.168.1.2")) is True
    assert (
        network.reconnect_needed(old, ProfileChange(autoconnect=False)) is False
    )  # yalnız anahtar
    assert (
        network.reconnect_needed(old, ProfileChange(autoconnect=True, ipv4_method="auto")) is True
    )
    auto = network.parse_profile("Ev", AUTO)
    assert (
        network.reconnect_needed(auto, ProfileChange(autoconnect=True, ipv4_method="auto")) is False
    )
    assert (
        network.reconnect_needed(auto, ProfileChange(autoconnect=True, dns_choice="auto")) is False
    )
    assert (
        network.reconnect_needed(auto, ProfileChange(autoconnect=True, dns_choice="google")) is True
    )


def test_wifi_profile_save_runs_modify_then_optional_up(monkeypatch):
    calls = []

    def fake(cmd, timeout=30):
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(network, "_run_rc", fake)
    change = ProfileChange(autoconnect=True, dns_choice="google")
    assert network.wifi_profile_save("Ev", change) == (True, "")
    assert len(calls) == 1 and calls[0][:4] == ["nmcli", "connection", "modify", "id"]
    assert all(isinstance(part, str) for part in calls[0])  # kabuk yok, düz argüman listesi
    calls.clear()
    assert network.wifi_profile_save("Ev", change, reconnect=True) == (True, "")
    assert calls[1] == ["nmcli", "connection", "up", "id", "Ev"]

    results = iter([(1, "Error: yok"), (0, "")])
    monkeypatch.setattr(network, "_run_rc", lambda cmd, timeout=30: next(results))
    assert network.wifi_profile_save("Ev", change, reconnect=True) == (False, "Error: yok")
    # Geçersiz değer hiçbir komut çalıştırmadan reddedilir
    monkeypatch.setattr(network, "_run_rc", lambda *a, **k: pytest.fail("çalıştırılmamalı"))
    with pytest.raises(ProfileError):
        network.wifi_profile_save("Ev", ProfileChange(autoconnect=True, metered="x"))


def test_wifi_password_reads_secret_and_unescapes(monkeypatch):
    calls = []

    def fake(cmd, timeout=10):
        calls.append(cmd)
        return "p\\:ss\\\\wörd 1\n", ""

    monkeypatch.setattr(network, "_run", fake)
    assert network.wifi_password("Ev Ağı") == "p:ss\\wörd 1"  # ":" ve "\\" kaçırılmıştır
    assert calls[0] == [
        "nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", "id", "Ev Ağı",
    ]  # fmt: skip


@pytest.mark.parametrize("out", ["", "\n", "--\n"])
def test_wifi_password_unavailable(monkeypatch, out):
    monkeypatch.setattr(network, "_run", lambda cmd, timeout=10: (out, ""))
    assert network.wifi_password("Açık Ağ") is None
