"""Bluetooth: güvenilir cihaz (otomatik bağlan) ve yeniden adlandırma (Qt'siz)."""

import pytest

from linwas.backend import network
from linwas.backend.network import AliasError

MAC = "AA:BB:CC:DD:EE:FF"


def test_parse_info_reads_trusted():
    trusted = network.parse_info(MAC, "x", "\tPaired: yes\n\tTrusted: yes\n\tConnected: no\n")
    assert trusted.trusted and trusted.paired
    untrusted = network.parse_info(MAC, "x", "\tPaired: yes\n\tTrusted: no\n")
    assert not untrusted.trusted
    assert not network.parse_info(MAC, "x", "").trusted  # bilinmiyorsa güvenilir sayılmaz


def test_set_trusted_runs_trust_and_verifies_by_reading_back(monkeypatch):
    calls = []
    state = {"trusted": False}

    def fake(*args, timeout=15):
        calls.append(args)
        if args[0] == "trust":
            state["trusted"] = True
        elif args[0] == "untrust":
            state["trusted"] = False
        elif args[0] == "info":
            return 0, f"\tPaired: yes\n\tTrusted: {'yes' if state['trusted'] else 'no'}\n"
        return 0, ""

    monkeypatch.setattr(network, "_btctl", fake)
    assert network.bluetooth_set_trusted(MAC, True) is True
    assert calls[0] == ("trust", MAC) and calls[1] == ("info", MAC)
    assert network.bluetooth_set_trusted(MAC, False) is True
    assert calls[2] == ("untrust", MAC)


def test_set_trusted_reports_failure_when_state_did_not_change(monkeypatch):
    monkeypatch.setattr(network, "_btctl", lambda *a, timeout=15: (0, "\tTrusted: no\n"))
    assert (
        network.bluetooth_set_trusted(MAC, True) is False
    )  # komut "başarılı" dese de doğrulanamadı


def test_set_trusted_rejects_bad_address_without_running_anything(monkeypatch):
    monkeypatch.setattr(network, "_btctl", lambda *a, **k: pytest.fail("çalıştırılmamalı"))
    assert network.bluetooth_set_trusted("--agent", True) is False
    assert network.bluetooth_set_trusted("aa:bb:cc:dd:ee:ff", True) is False


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Kulaklık", "Kulaklık"),
        ("  Benim   Kulaklık \t", "Benim Kulaklık"),
        ("", ""),  # boş ad: cihazın kendi adına dönülür
        ("   ", ""),
        ("-H sunucu", "-H sunucu"),  # geçerli ad; komuta `--` ile güvenle verilir
        ("a" * 64, "a" * 64),
    ],
)
def test_validate_alias_accepts(raw, clean):
    assert network.validate_alias(raw) == clean


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("a" * 65, "too_long"),
        ("bir\x00ad", "bad_chars"),
        ("zil\x07", "bad_chars"),
        ("x\x7f", "bad_chars"),
    ],
)
def test_validate_alias_rejects(raw, code):
    with pytest.raises(AliasError) as err:
        network.validate_alias(raw)
    assert err.value.code == code


def test_adapters_come_from_sysfs_and_ignore_connection_entries(tmp_path):
    for name in ("hci10", "hci2", "hci0", "hci0:256", "rfkill1", "hcix"):
        (tmp_path / name).mkdir()
    assert network.bluetooth_adapters(tmp_path) == ["hci0", "hci2", "hci10"]
    assert network.bluetooth_adapters(tmp_path / "yok") == ["hci0"]  # sysfs yoksa varsayılan
    empty = tmp_path / "bos"
    empty.mkdir()
    assert network.bluetooth_adapters(empty) == ["hci0"]


def test_device_object_path():
    assert network.bluetooth_device_path("hci1", MAC) == "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF"


def test_rename_writes_the_alias_property_with_options_terminated(monkeypatch):
    calls = []

    def fake(cmd, timeout=30):
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(network, "_run_rc", fake)
    monkeypatch.setattr(network, "bluetooth_adapters", lambda: ["hci0"])
    assert network.bluetooth_rename(MAC, "  -H  sunucu ") == (True, "")
    assert calls == [
        [
            "busctl", "--system", "set-property", "--", "org.bluez",
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF", "org.bluez.Device1", "Alias", "s", "-H sunucu",
        ]
    ]  # fmt: skip
    # `--` kullanıcıdan gelen ilk değerden önce: ad seçenek sayılamaz
    assert calls[0].index("--") < calls[0].index("-H sunucu")


def test_rename_empty_name_resets_to_the_device_name(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_run_rc", lambda cmd, timeout=30: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(network, "bluetooth_adapters", lambda: ["hci0"])
    assert network.bluetooth_rename(MAC, "  ")[0] is True
    assert calls[0][-3:] == ["Alias", "s", ""]


def test_rename_tries_every_adapter_until_one_knows_the_device(monkeypatch):
    calls = []

    def fake(cmd, timeout=30):
        calls.append(cmd[5])
        if "/hci1/" in cmd[5]:
            return 0, ""
        return 1, "Unknown object"

    monkeypatch.setattr(network, "_run_rc", fake)
    monkeypatch.setattr(network, "bluetooth_adapters", lambda: ["hci0", "hci1", "hci2"])
    assert network.bluetooth_rename(MAC, "Kulaklık") == (True, "")
    assert calls == [
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
        "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF",
    ]  # bulunca durur


def test_rename_failure_returns_the_last_error(monkeypatch):
    monkeypatch.setattr(network, "_run_rc", lambda cmd, timeout=30: (1, "Access denied"))
    monkeypatch.setattr(network, "bluetooth_adapters", lambda: ["hci0"])
    assert network.bluetooth_rename(MAC, "Ad") == (False, "Access denied")


def test_rename_validates_before_running_anything(monkeypatch):
    monkeypatch.setattr(network, "_run_rc", lambda *a, **k: pytest.fail("çalıştırılmamalı"))
    assert network.bluetooth_rename("--version", "Ad") == (False, "invalid address")
    with pytest.raises(AliasError):
        network.bluetooth_rename(MAC, "a" * 65)
