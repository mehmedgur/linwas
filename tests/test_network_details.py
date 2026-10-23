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


def test_detail_rows_skip_empty_values(qapp):
    from linwas.ui.pages.network import detail_rows

    full = network.build_wifi_details("Ev Ağı", "wlan0", SHOW, LIST)
    labels = [label for label, _ in detail_rows(full)]
    assert labels[0] == "IP address" and "Link speed" in labels
    assert dict(detail_rows(full))["Band"] == "5 GHz · channel 36"
    assert dict(detail_rows(full))["Link speed"] == "866 Mbit/s"
    sparse = network.build_wifi_details("Ev", "wlan0", "", "")
    assert [label for label, _ in detail_rows(sparse)] == ["Security"]
    assert dict(detail_rows(sparse))["Security"] == "Open network, not secured"


def test_details_card_rebuilds_only_on_change_and_copies(qapp):
    from PySide6.QtGui import QGuiApplication

    from linwas.ui.pages.network import _DetailsCard

    card = _DetailsCard()
    details = network.build_wifi_details("Ev Ağı", "wlan0", SHOW, LIST)
    card.show_details(details)
    first = card.rows
    assert ("IP address", "192.168.1.5") in first
    grid_widgets = card._grid.count()
    card.show_details(details)  # aynı veri: yeniden kurulmaz
    assert card._grid.count() == grid_widgets and card.rows == first

    card._copy_ip.click()
    assert QGuiApplication.clipboard().text() == "192.168.1.5"
    assert card._copy_ip.text() == "Copied"
    card._copy_all.click()
    text = QGuiApplication.clipboard().text()
    assert "IP address: 192.168.1.5" in text and "Gateway: 192.168.1.1" in text
