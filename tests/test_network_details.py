# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Wi-Fi bağlantı ayrıntıları: nmcli çıktı ayrıştırıcıları (Qt'siz) ve ayrıntı kartı."""

import os

import pytest

from linwas.backend import network

SHOW = r"""GENERAL.HWADDR:AA\:BB\:CC\:DD\:EE\:FF
IP4.ADDRESS[1]:192.168.1.5/24
IP4.GATEWAY:192.168.1.1
IP4.DNS[1]:192.168.1.1
IP4.DNS[2]:8.8.8.8
"""

# ACTIVE,DEVICE,BSSID,SSID,CHAN,FREQ,RATE,SIGNAL,SECURITY
LIST = "\n".join(
    [
        r"no:wlan0:11\:22\:33\:44\:55\:66:Komşu:1:2412 MHz:130 Mbit/s:40:WPA2",
        r"yes:wlan0:AA\:00\:00\:00\:00\:01:Ev Ağı:36:5180 MHz:866 Mbit/s:72:WPA2 WPA3",
    ]
)


def test_unescape_terse():
    assert network.unescape_terse(r"AA\:BB\\C") == "AA:BB\\C"
    assert network.unescape_terse("düz") == "düz"


def test_parse_device_show_strips_index_and_unescapes():
    info = network.parse_device_show(SHOW + "IP4.ROUTE[1]:\nbozuk satır\n")
    assert info["GENERAL.HWADDR"] == ["AA:BB:CC:DD:EE:FF"]
    assert info["IP4.DNS"] == ["192.168.1.1", "8.8.8.8"]
    assert info["IP4.GATEWAY"] == ["192.168.1.1"]
    assert "IP4.ROUTE" not in info  # boş değer atlanır


@pytest.mark.parametrize(
    ("mhz", "band"),
    [
        (2412, "2.4 GHz"),
        (2484, "2.4 GHz"),
        (5180, "5 GHz"),
        (5885, "5 GHz"),
        (5955, "6 GHz"),
        (7115, "6 GHz"),
        (1000, ""),
        (None, ""),
    ],
)
def test_band_from_frequency(mhz, band):
    assert network.band_from_frequency(mhz) == band


def test_build_wifi_details_picks_active_row():
    d = network.build_wifi_details("Ev Ağı", "wlan0", SHOW, LIST)
    assert (d.ip, d.prefix, d.gateway) == ("192.168.1.5", 24, "192.168.1.1")
    assert d.dns == ["192.168.1.1", "8.8.8.8"]
    assert d.mac == "AA:BB:CC:DD:EE:FF"
    assert d.bssid == "AA:00:00:00:00:01"
    assert (d.band, d.channel, d.frequency, d.rate, d.signal) == ("5 GHz", 36, 5180, 866, 72)
    assert d.security == "WPA2 WPA3"


def test_build_wifi_details_prefers_matching_device_and_tolerates_gaps():
    two = LIST + "\n" + r"yes:wlan1:CC\:00\:00\:00\:00\:02:Başka:6:2437 MHz:72 Mbit/s:55:WPA2"
    assert network.build_wifi_details("Başka", "wlan1", "", two).bssid == "CC:00:00:00:00:02"
    empty = network.build_wifi_details("Ev", "wlan0", "", "")
    assert (empty.ip, empty.gateway, empty.dns, empty.band, empty.rate) == ("", "", [], "", None)
    # Bozuk adres: önek yok sayılır ama ham değer korunur
    odd = network.build_wifi_details("Ev", "wlan0", "IP4.ADDRESS[1]:belirsiz", "")
    assert (odd.ip, odd.prefix) == ("belirsiz", None)


def test_wifi_details_not_connected_returns_none():
    status = network.WifiStatus(enabled=True, connected=False, ssid="", device="wlan0")
    assert network.wifi_details(status) is None


def test_wifi_details_runs_two_nmcli_calls(monkeypatch):
    calls = []

    def fake(*args, timeout=10):
        calls.append(args)
        return SHOW if "show" in args else LIST

    monkeypatch.setattr(network, "_nmcli", fake)
    status = network.WifiStatus(enabled=True, connected=True, ssid="Ev Ağı", device="wlan0")
    d = network.wifi_details(status)
    assert d is not None and d.ip == "192.168.1.5"
    assert calls[0][-3:] == ("device", "show", "wlan0")
    assert "--rescan" in calls[1]


# --- Ayrıntı kartı (PySide6 yoksa atlanır) ---


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # sistem kütüphanesi (ör. libEGL) eksik
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    return QApplication.instance() or QApplication([])


def test_basic_rows_are_filtered_and_advanced_holds_the_rest(qapp):
    from linwas.ui.pages.network import advanced_rows, basic_rows, detail_rows

    full = network.build_wifi_details("Ev Ağı", "wlan0", SHOW, LIST)
    basic = dict(basic_rows(full))
    # Varsayılan görünen: hız (+bant), IP adresi, güvenlik — teknik alanlar yok
    assert list(basic) == ["Speed", "IP address", "Security"]
    assert basic["Speed"] == "866 Mbit/s · 5 GHz"
    assert basic["Security"] == "Secured (WPA2)"
    advanced = dict(advanced_rows(full))
    assert list(advanced) == [
        "Gateway",
        "DNS servers",
        "Channel",
        "Hardware address (MAC)",
        "Access point (BSSID)",
    ]
    assert advanced["DNS servers"] == "192.168.1.1, 8.8.8.8" and advanced["Channel"] == "36"
    assert [label for label, _ in detail_rows(full)] == list(basic) + list(advanced)

    sparse = network.build_wifi_details("Ev", "wlan0", "", "")
    assert dict(basic_rows(sparse)) == {"Security": "Open network, not secured"}
    assert advanced_rows(sparse) == []
    # Hız bilinmiyorsa yalnızca bant gösterilir
    only_band = network.WifiDetails("Ev", "wlan0", band="2.4 GHz")
    assert dict(basic_rows(only_band))["Speed"] == "2.4 GHz"


def test_details_card_hides_advanced_by_default_and_copies_everything(qapp):
    from PySide6.QtGui import QGuiApplication

    from linwas.ui.pages.network import _DetailsCard

    card = _DetailsCard()
    card.show()
    details = network.build_wifi_details("Ev Ağı", "wlan0", SHOW, LIST)
    card.show_details(details)
    assert ("IP address", "192.168.1.5") in card.rows and len(card.rows) == 3
    assert card._toggle.isVisible() and not card._advanced.isVisible()  # teknik satırlar gizli
    assert len(card.advanced) == 5

    cells = card._basic_grid.count()
    card.show_details(details)  # aynı veri: yeniden kurulmaz
    assert card._basic_grid.count() == cells

    card._toggle.click()
    assert card._advanced.isVisible()
    card._toggle.click()
    assert not card._advanced.isVisible()

    card._copy_ip.click()
    assert QGuiApplication.clipboard().text() == "192.168.1.5"
    assert card._copy_ip.text() == "Copied"
    card._copy_all.click()
    text = QGuiApplication.clipboard().text()  # destek için her şey kopyalanır
    assert "IP address: 192.168.1.5" in text and "Gateway: 192.168.1.1" in text
    assert "Hardware address (MAC): AA:BB:CC:DD:EE:FF" in text

    bare = network.WifiDetails("Ev", "wlan0")  # gelişmiş veri yoksa düğme de yok
    card.show_details(bare)
    assert not card._toggle.isVisible() and not card._advanced.isVisible()


def test_weak_unknown_networks_are_noise():
    from linwas.backend.network import WifiNetwork

    def net(signal, active=False, saved=False):
        return WifiNetwork("x", signal, "WPA2", active, "AA", saved=saved)

    pytest.importorskip("PySide6")
    from linwas.ui.pages.network import is_weak_unknown

    assert is_weak_unknown(net(10))
    assert not is_weak_unknown(net(10, active=True))
    assert not is_weak_unknown(net(10, saved=True))
    assert not is_weak_unknown(net(45))


def test_is_unnamed_device():
    def dev(name):
        return network.BluetoothDevice("AA:BB:CC:DD:EE:FF", name, False, False)

    assert network.is_unnamed_device(dev(""))
    assert network.is_unnamed_device(dev("AA-BB-CC-DD-EE-FF"))
    assert network.is_unnamed_device(dev("aa:bb:cc:dd:ee:ff"))
    assert not network.is_unnamed_device(dev("Kulaklık"))
    assert not network.is_unnamed_device(dev("JBL Flip 5"))


def _wait(condition, timeout=3.0):
    from PySide6.QtTest import QTest

    waited = 0
    while not condition() and waited < timeout * 1000:
        QTest.qWait(20)
        waited += 20
    return condition()


def test_wifi_tab_collapses_weak_networks(qapp, monkeypatch, tmp_path):
    from linwas.ui.pages.network import _Row, _WifiTab

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    status = network.WifiStatus(True, True, "Ev", "wlan0", 72, "10.0.0.5")
    nets = [
        network.WifiNetwork("Ev", 72, "WPA2", True, "A", saved=True),
        network.WifiNetwork("İyi", 60, "WPA2", False, "B"),
        network.WifiNetwork("Zayıf1", 10, "WPA2", False, "C"),
        network.WifiNetwork("Zayıf2", 12, "", False, "D"),
        network.WifiNetwork("KayıtlıZayıf", 8, "WPA2", False, "E", saved=True),
    ]
    monkeypatch.setattr(network, "wifi_status", lambda: status)
    monkeypatch.setattr(network, "wifi_list", lambda rescan=True: nets)
    monkeypatch.setattr(network, "wifi_details", lambda s: None)
    tab = _WifiTab()
    tab.show()
    assert _wait(lambda: len(tab._list_card.findChildren(_Row)) > 0)
    from PySide6.QtWidgets import QLabel

    def names():
        return [r.findChildren(QLabel)[0].text() for r in tab._list_card.findChildren(_Row)]

    assert sorted(names()) == ["Ev", "KayıtlıZayıf", "İyi"]  # zayıf+bilinmeyenler gizli
    assert tab._weak_btn.isVisible() and "2" in tab._weak_btn.text()
    tab._weak_btn.click()
    assert _wait(lambda: len(tab._list_card.findChildren(_Row)) == 5)
    assert tab._weak_btn.text() == "Hide weak networks"
    tab._weak_btn.click()
    assert _wait(lambda: len(tab._list_card.findChildren(_Row)) == 3)


def test_bluetooth_tab_collapses_unnamed_devices(qapp, monkeypatch):
    from linwas.ui.pages.network import _BtTab, _Row

    devices = [
        network.BluetoothDevice("AA:00:00:00:00:01", "Kulaklık", True, True, "audio-headset"),
        network.BluetoothDevice("AA:00:00:00:00:02", "Hoparlör", False, False),
        network.BluetoothDevice("AA:00:00:00:00:03", "AA-00-00-00-00-03", False, False),
        network.BluetoothDevice("AA:00:00:00:00:04", "", False, False),
    ]
    monkeypatch.setattr(network, "bluetooth_state", lambda: "on")
    monkeypatch.setattr(network, "bluetooth_list_devices", lambda: devices)
    tab = _BtTab()
    tab.show()
    assert _wait(lambda: len(tab._nearby.findChildren(_Row)) > 0)
    assert len(tab._mine.findChildren(_Row)) == 1  # eşleşmiş her zaman görünür
    assert len(tab._nearby.findChildren(_Row)) == 1  # yalnızca adlı yeni cihaz
    assert tab._unnamed_btn.isVisible() and "2" in tab._unnamed_btn.text()
    tab._unnamed_btn.click()
    assert _wait(lambda: len(tab._nearby.findChildren(_Row)) == 3)
    assert tab._unnamed_btn.text() == "Hide unnamed devices"
