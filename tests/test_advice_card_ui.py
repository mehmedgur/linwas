# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Öneri kartı ve Wi-Fi/Bluetooth sekmelerindeki "Ayarlara bak" / "Şimdi değil" akışı (PySide6)."""

import os

import pytest

from linwas.backend import netquality, network
from linwas.backend.network import BluetoothDevice, WifiNetwork, WifiStatus
from linwas.core import netadvice
from linwas.core.netadvice import RULE_BT, RULE_WIFI, Advice, TrackRecord

WIFI = Advice(RULE_WIFI, "Ev Ağı", "Ev Ağı", 4, 120, avg_signal=35, avg_rtt_ms=82.4)
BT = Advice(RULE_BT, "AA:00:00:00:00:01", "Kulaklık", 3, 90)
KNOWN = TrackRecord(4, 5)


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # sistem kütüphanesi (ör. libEGL) eksik
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    return QApplication.instance() or QApplication([])


def _wait(condition, timeout=3.0):
    from PySide6.QtTest import QTest

    waited = 0
    while not condition() and waited < timeout * 1000:
        QTest.qWait(20)
        waited += 20
    return condition()


# --- Metinler ---


def test_reason_lines_show_evidence_rule_and_track_record(qapp):
    from linwas.ui.widgets.advice_card import reason_lines

    lines = reason_lines(WIFI, KNOWN)
    text = "\n".join(lines)
    assert "4 drops in 120 readings" in text
    assert "35%" in text and "82 ms" in text  # sayılar kanıt olarak
    assert "3 or more times in a week" in text  # kural
    assert "4/5" in text and "Not enough history" not in text  # geçmiş isabet
    assert "only opens the settings" in lines[-1]  # hiçbir şey değişmez


def test_reason_lines_without_signal_and_with_unknown_track_record(qapp):
    from linwas.ui.widgets.advice_card import reason_lines

    lines = reason_lines(BT, TrackRecord(1, 1))
    text = "\n".join(lines)
    assert "Average signal" not in text and "Average delay" not in text  # Bluetooth'ta yok
    assert "Not enough history yet" in text and "/" not in text.split("Track record")[0]


# --- Kart ---


def _card(items, can_review=lambda a: True):
    from linwas.ui.widgets.advice_card import AdviceCard, _AdviceRow

    card = AdviceCard()
    card.show()
    card.set_items(items, can_review)
    # Görünür kartta sonradan eklenen çocuklar olay döngüsünde gösterilir
    assert _wait(lambda: all(row.isVisible() for row in card.findChildren(_AdviceRow)))
    return card


def test_card_is_hidden_without_suggestions(qapp):
    card = _card([])
    assert not card.isVisible()
    card.set_items([(WIFI, KNOWN)])
    assert card.isVisible()
    card.set_items([])
    assert not card.isVisible()


def test_card_row_hides_the_evidence_until_asked(qapp):
    from linwas.ui.widgets.advice_card import _AdviceRow

    card = _card([(WIFI, KNOWN)])
    (row,) = card.findChildren(_AdviceRow)
    assert not row.reasons.isVisible()  # süzülmüş: kanıt varsayılan gizli
    assert row.review_button.isVisible() and row.dismiss_button.isVisible()
    row.why.click()
    assert row.reasons.isVisible()


def test_card_buttons_report_rule_and_subject(qapp):
    from linwas.ui.widgets.advice_card import _AdviceRow

    card = _card([(WIFI, KNOWN), (BT, TrackRecord())])
    reviewed, dismissed = [], []
    card.review_requested.connect(lambda rule, subject: reviewed.append((rule, subject)))
    card.dismissed.connect(lambda rule, subject: dismissed.append((rule, subject)))
    first, second = card.findChildren(_AdviceRow)
    first.review_button.click()
    second.dismiss_button.click()
    assert reviewed == [(RULE_WIFI, "Ev Ağı")] and dismissed == [(RULE_BT, BT.subject)]


def test_review_button_is_hidden_when_there_is_nothing_to_open(qapp):
    from linwas.ui.widgets.advice_card import _AdviceRow

    card = _card([(WIFI, KNOWN)], can_review=lambda a: False)
    (row,) = card.findChildren(_AdviceRow)
    assert not row.review_button.isVisible() and row.dismiss_button.isVisible()


def test_card_keeps_its_rows_when_nothing_changed(qapp):
    from linwas.ui.widgets.advice_card import _AdviceRow

    card = _card([(WIFI, KNOWN)])
    (row,) = card.findChildren(_AdviceRow)
    row.why.click()
    card.set_items([(WIFI, KNOWN)])  # otomatik yenileme: aynı öneri
    (same,) = card.findChildren(_AdviceRow)
    assert same is row and same.reasons.isVisible()  # "Neden?" açık kalır
    card.set_items([(Advice(RULE_WIFI, "Ev Ağı", "Ev Ağı", 5, 130), KNOWN)])
    assert _wait(lambda: any(r.isVisible() for r in card.findChildren(_AdviceRow)))
    (changed,) = card.findChildren(_AdviceRow)  # eski satır kaldırıldı, yenisi kuruldu
    assert changed is not row and not row.isVisible()


# --- Wi-Fi sekmesi ---


@pytest.fixture
def advice_env(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    state = {
        "wifi": [(WIFI, KNOWN)],
        "bt": [(BT, TrackRecord())],
        "dismissed": [],
        "status": WifiStatus(True, True, "Ev Ağı", "wlan0", 60, "192.168.1.5"),
        "hotspot": None,
    }
    nets = [
        WifiNetwork("Ev Ağı", 60, "WPA2", True, "A", saved=True),
        WifiNetwork("Kafe", 50, "WPA2", False, "B"),
    ]
    monkeypatch.setattr(
        netadvice, "current", lambda rule: state["wifi"] if rule == RULE_WIFI else state["bt"]
    )

    def dismiss(rule, subject, now=None, path=None):
        state["dismissed"].append((rule, subject))
        state["wifi" if rule == RULE_WIFI else "bt"] = []

    monkeypatch.setattr(netadvice, "dismiss", dismiss)
    monkeypatch.setattr(network, "wifi_status", lambda: state["status"])
    monkeypatch.setattr(network, "hotspot_info", lambda s: state["hotspot"])
    monkeypatch.setattr(network, "wifi_list", lambda rescan=True: nets)
    monkeypatch.setattr(network, "wifi_details", lambda s: None)
    monkeypatch.setattr(network, "bluetooth_state", lambda: "on")
    devices = [BluetoothDevice(BT.subject, "Kulaklık", True, True, "audio-headset", trusted=True)]
    monkeypatch.setattr(network, "bluetooth_list_devices", lambda: devices)
    monkeypatch.setattr(network, "bluetooth_adapter_info", lambda: None)
    monkeypatch.setattr(netquality, "note_user_action", lambda *a, **k: None)
    return state


def test_wifi_tab_shows_the_suggestion_and_opens_the_network_settings(advice_env, monkeypatch):
    from linwas.ui.pages import network as page

    opened = []
    tab = page._WifiTab()
    tab.show()
    assert _wait(lambda: tab._advice.isVisible())
    monkeypatch.setattr(tab, "_open_settings", lambda net: opened.append(net.ssid))
    tab._advice_review(RULE_WIFI, "Ev Ağı")
    assert opened == ["Ev Ağı"]
    tab._advice_review(RULE_WIFI, "Kafe")  # kayıtlı değil: açılacak ayar yok
    assert opened == ["Ev Ağı"]


def test_wifi_suggestion_can_be_dismissed(advice_env):
    from linwas.ui.pages import network as page
    from linwas.ui.widgets.advice_card import _AdviceRow

    tab = page._WifiTab()
    tab.show()
    assert _wait(lambda: tab._advice.isVisible())
    (row,) = tab._advice.findChildren(_AdviceRow)
    row.dismiss_button.click()
    assert _wait(lambda: advice_env["dismissed"] == [(RULE_WIFI, "Ev Ağı")])
    assert _wait(lambda: not tab._advice.isVisible())  # yenilenince kaybolur


def test_wifi_tab_without_suggestions_has_no_card(advice_env):
    from linwas.ui.pages import network as page

    advice_env["wifi"] = []
    tab = page._WifiTab()
    tab.show()
    assert _wait(lambda: tab._status is not None and tab._loading is None)
    assert not tab._advice.isVisible()


def test_hotspot_hides_the_wifi_suggestions(advice_env):
    from linwas.backend.network import HotspotInfo
    from linwas.ui.pages import network as page

    advice_env["status"] = WifiStatus(True, True, "Linwas Hotspot", "wlan0", 0, "10.42.0.1")
    advice_env["hotspot"] = HotspotInfo("Linwas Hotspot", "Linwas Evi", "wlan0")
    tab = page._WifiTab()
    tab.show()
    assert _wait(lambda: tab._hotspot is not None)
    assert not tab._advice.isVisible()


# --- Bluetooth sekmesi ---


def test_bluetooth_tab_suggestion_opens_the_device_settings_or_is_dismissed(
    advice_env, monkeypatch
):
    from linwas.ui.pages import network as page
    from linwas.ui.widgets.advice_card import _AdviceRow

    tab = page._BtTab()
    tab.show()
    assert _wait(lambda: tab._advice.isVisible())
    opened = []
    monkeypatch.setattr(tab, "_open_settings", lambda dev: opened.append(dev.name))
    tab._advice_review(RULE_BT, BT.subject)
    tab._advice_review(RULE_BT, "FF:FF:FF:FF:FF:FF")  # eşleşmiş böyle bir cihaz yok
    assert opened == ["Kulaklık"]
    (row,) = tab._advice.findChildren(_AdviceRow)
    row.dismiss_button.click()
    assert _wait(lambda: advice_env["dismissed"] == [(RULE_BT, BT.subject)])
    assert _wait(lambda: not tab._advice.isVisible())


def test_bluetooth_tab_hides_suggestions_when_bluetooth_is_off(advice_env, monkeypatch):
    from linwas.ui.pages import network as page

    monkeypatch.setattr(network, "bluetooth_state", lambda: "off")
    tab = page._BtTab()
    tab.show()
    assert _wait(lambda: tab._state == "off")
    assert not tab._advice.isVisible()
