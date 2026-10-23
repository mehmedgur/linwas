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


# --- Bu bilgisayarın görünürlüğü ---

SHOW_HIDDEN = """Controller 00:11:22:33:44:55 (public)
\tManufacturer: 0x000f (15)
\tVersion: 0x0a (10)
\tName: virci
\tAlias: Benim Bilgisayarım
\tClass: 0x007c010c (8143116)
\tPowered: yes
\tPowerState: on
\tDiscoverable: no
\tDiscoverableTimeout: 0x000000b4 (180)
\tPairable: yes
\tUUID: Generic Attribute Profile (00001801-0000-1000-8000-00805f9b34fb)
"""


def test_parse_adapter_reads_name_visibility_and_timeout():
    info = network.parse_adapter(SHOW_HIDDEN)
    assert info.alias == "Benim Bilgisayarım"
    assert (info.discoverable, info.timeout, info.pairable) == (False, 180, True)
    visible = network.parse_adapter(
        SHOW_HIDDEN.replace("Discoverable: no", "Discoverable: yes")
        .replace("0x000000b4 (180)", "0x00000000 (0)")
        .replace("Pairable: yes", "Pairable: no")
    )
    assert (visible.discoverable, visible.timeout, visible.pairable) == (True, 0, False)


def test_parse_adapter_falls_back_to_name_and_tolerates_missing_fields():
    info = network.parse_adapter("Controller AA:BB:CC:DD:EE:FF\n\tName: virci\n")
    assert (info.alias, info.timeout, info.discoverable, info.pairable) == (
        "virci",
        None,
        False,
        True,
    )


@pytest.mark.parametrize("out", ["", "\n", "No default controller available\n", "Device AA:BB x\n"])
def test_parse_adapter_is_none_without_a_controller(out):
    assert network.parse_adapter(out) is None


class FakeController:
    """`bluetoothctl show/discoverable/...` komutlarını taklit eder."""

    def __init__(self, discoverable=False, timeout=180, pairable=True):
        self.state = {"discoverable": discoverable, "timeout": timeout, "pairable": pairable}
        self.calls = []

    def __call__(self, *args, timeout=15):
        self.calls.append(args)
        if args == ("show",):
            return 0, (
                "Controller 00:11:22:33:44:55 (public)\n\tName: virci\n\tAlias: virci\n"
                f"\tDiscoverable: {'yes' if self.state['discoverable'] else 'no'}\n"
                f"\tDiscoverableTimeout: 0x00000000 ({self.state['timeout']})\n"
                f"\tPairable: {'yes' if self.state['pairable'] else 'no'}\n"
            )
        if args[0] == "discoverable":
            self.state["discoverable"] = args[1] == "on"
        elif args[0] == "discoverable-timeout":
            self.state["timeout"] = int(args[1])
        elif args[0] == "pairable":
            self.state["pairable"] = args[1] == "on"
        return 0, ""


def test_make_visible_turns_discoverable_on_and_verifies(monkeypatch):
    fake = FakeController()
    monkeypatch.setattr(network, "_btctl", fake)
    assert network.bluetooth_set_visible(True) is True
    assert ("discoverable", "on") in fake.calls
    assert ("discoverable-timeout", "180") not in fake.calls  # süre zaten sınırlı: dokunulmaz
    assert ("pairable", "on") not in fake.calls
    assert network.bluetooth_set_visible(False) is True
    assert fake.state["discoverable"] is False


def test_make_visible_limits_an_unlimited_timeout_and_enables_pairing(monkeypatch):
    fake = FakeController(timeout=0, pairable=False)
    monkeypatch.setattr(network, "_btctl", fake)
    assert network.bluetooth_set_visible(True, seconds=120) is True
    assert fake.state["timeout"] == 120 and fake.state["pairable"] is True  # açık unutulmasın
    order = [c[0] for c in fake.calls if c[0] != "show"]
    assert order.index("discoverable-timeout") < order.index("discoverable")  # süre önce


def test_hiding_does_not_touch_timeout_or_pairing(monkeypatch):
    fake = FakeController(discoverable=True, timeout=0, pairable=False)
    monkeypatch.setattr(network, "_btctl", fake)
    assert network.bluetooth_set_visible(False) is True
    assert [c[0] for c in fake.calls if c[0] != "show"] == ["discoverable"]


def test_visibility_failures_are_reported(monkeypatch):
    monkeypatch.setattr(network, "_btctl", lambda *a, timeout=15: (1, "No default controller"))
    assert network.bluetooth_set_visible(True) is False  # denetleyici yok
    fake = FakeController()
    original = fake.__call__

    def stuck(*args, timeout=15):
        if args and args[0] == "discoverable":
            return 0, ""  # "başarılı" der, değiştirmez
        return original(*args, timeout=timeout)

    monkeypatch.setattr(network, "_btctl", stuck)
    assert network.bluetooth_set_visible(True) is False


def test_computer_name_is_written_on_the_adapter_object(monkeypatch):
    calls = []
    monkeypatch.setattr(network, "_run_rc", lambda cmd, timeout=30: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(network, "bluetooth_adapters", lambda: ["hci0"])
    assert network.bluetooth_set_computer_name("  Salon   Bilgisayarı ") == (True, "")
    assert calls == [
        [
            "busctl", "--system", "set-property", "--", "org.bluez", "/org/bluez/hci0",
            "org.bluez.Adapter1", "Alias", "s", "Salon Bilgisayarı",
        ]
    ]  # fmt: skip
    assert network.bluetooth_set_computer_name("")[0] is True and calls[-1][-1] == ""  # sıfırla


def test_computer_name_validation(monkeypatch):
    monkeypatch.setattr(network, "_run_rc", lambda *a, **k: pytest.fail("çalıştırılmamalı"))
    with pytest.raises(AliasError):
        network.bluetooth_set_computer_name("x" * 65)
