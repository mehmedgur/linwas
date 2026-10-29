# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Hotspot penceresi, kartı ve Wi-Fi sekmesindeki akış (PySide6 gerektirir)."""

import os

import pytest

from linwas.backend import netquality, network
from linwas.backend.network import HotspotInfo, WifiNetwork, WifiStatus

AP = HotspotInfo(name="Linwas Hotspot", ssid="Linwas Evi", device="wlan0")


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


# --- Pencere ---


def test_dialog_validates_before_closing(qapp):
    from linwas.ui.pages.network_hotspot import HotspotDialog

    dlg = HotspotDialog("Linwas Evi", "gizli-sifre-1")
    dlg.show()
    assert dlg.values() == ("Linwas Evi", "gizli-sifre-1")
    assert not dlg._error.isVisible()

    dlg._password.setText("kısa")
    dlg.accept()
    assert dlg.result() == 0 and dlg._error.isVisible()  # kapanmadı
    assert "8 to 63" in dlg._error.text()

    dlg._password.setText("gizli-sifre-1")
    dlg._ssid.setText("")
    dlg.accept()
    assert dlg.result() == 0 and "network name" in dlg._error.text()

    dlg._ssid.setText("  Yeni Ad  ")
    dlg.accept()
    assert dlg.result() == 1 and dlg.values() == (
        "Yeni Ad",
        "gizli-sifre-1",
    )  # kenar boşluğu atılır


def test_dialog_new_password_button_generates_a_valid_one(qapp):
    from PySide6.QtWidgets import QPushButton

    from linwas.ui.pages.network_hotspot import HotspotDialog

    dlg = HotspotDialog("Ev", "ilk-sifre-123")
    button = next(b for b in dlg.findChildren(QPushButton) if b.text() == "New password")
    button.click()
    _ssid, password = dlg.values()
    assert password != "ilk-sifre-123"
    network.validate_hotspot("Ev", password)


def test_dialog_explains_the_wifi_disconnect(qapp):
    from PySide6.QtWidgets import QLabel

    from linwas.ui.pages.network_hotspot import HotspotDialog

    dlg = HotspotDialog("Ev", "gizli-sifre-1")
    texts = " ".join(label.text() for label in dlg.findChildren(QLabel))
    assert "disconnects this computer" in texts and "network cable" in texts


# --- Kart ---


def test_card_off_and_on_states(qapp):
    from linwas.ui.pages.network_hotspot import HotspotCard

    card = HotspotCard()
    card.show()
    started, stopped = [], []
    card.start_requested.connect(lambda: started.append(1))
    card.stop_requested.connect(lambda: stopped.append(1))

    assert card._button.text() == "Turn on…" and not card._password.isVisible()
    card._button.click()
    assert started == [1] and stopped == []

    card.show_info(AP)
    assert "password below" in card._text.text() and card._button.text() == "Turn off"
    assert card._password.isVisible() and not card._password.revealed  # şifre varsayılan gizli
    card._button.click()
    assert stopped == [1]

    card.show_info(None)
    assert card._button.text() == "Turn on…" and not card._password.isVisible()


def test_card_password_reads_the_hotspot_profile_on_demand(qapp, monkeypatch):
    from linwas.ui.pages.network_hotspot import HotspotCard

    reads = []
    monkeypatch.setattr(network, "wifi_password", lambda name: reads.append(name) or "sifre-123")
    card = HotspotCard()
    card.show()
    card.show_info(AP)
    assert reads == []  # kart açıkken de şifre kendiliğinden okunmaz
    card._password._show.click()
    assert _wait(lambda: card._password.revealed)
    assert reads == ["Linwas Hotspot"] and card._password._edit.text() == "sifre-123"

    card.show_info(AP)  # otomatik yenileme: aynı bilgi, şifre ekranda kalır
    assert card._password.revealed
    card.show_info(HotspotInfo("Başka", "Başka", "wlan0"))  # farklı hotspot: eski şifre silinir
    assert not card._password.revealed and card._password._edit.text() == ""


# --- Wi-Fi sekmesi ---


@pytest.fixture
def tab_env(qapp, monkeypatch, tmp_path):
    """Sekmeyi arka uç çağrıları taklit edilerek kurar; çağrılar `calls` listesine düşer."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    env = {"status": WifiStatus(True, True, "Ev Ağı", "wlan0", 72, "192.168.1.50"), "hotspot": None}
    nets = [WifiNetwork("Ev Ağı", 72, "WPA2", True, "A", saved=True)]
    calls: list[tuple] = []
    monkeypatch.setattr(network, "wifi_status", lambda: env["status"])
    monkeypatch.setattr(network, "hotspot_info", lambda status: env["hotspot"])
    monkeypatch.setattr(network, "wifi_list", lambda rescan=True: nets)
    monkeypatch.setattr(network, "wifi_details", lambda s: None)
    monkeypatch.setattr(network, "hotspot_defaults", lambda: ("Linwas Evi", "gizli-sifre-1"))
    monkeypatch.setattr(
        netquality, "note_user_action", lambda kind, name, ident="": calls.append(("note", name))
    )

    def start(device, ssid, password):
        calls.append(("start", device, ssid, password))
        return True, ""

    def stop(name):
        calls.append(("stop", name))
        return True

    monkeypatch.setattr(network, "hotspot_start", start)
    monkeypatch.setattr(network, "hotspot_stop", stop)
    env["calls"] = calls
    return env


def _tab():
    from linwas.ui.pages import network as page

    tab = page._WifiTab()
    tab.show()
    return tab


def _idle(tab):
    return tab._loading is None and not tab._busy and tab._hotspot_job is None


def test_tab_offers_hotspot_when_wifi_is_available(tab_env):
    tab = _tab()
    assert _wait(lambda: tab._status is not None and _idle(tab))
    assert tab._hotspot_card.isVisible() and tab._hotspot_card.info is None
    assert tab._list_card.isVisible()  # normal görünüm bozulmaz


def test_tab_hides_hotspot_card_without_wifi(tab_env):
    tab_env["status"] = WifiStatus(False, False, "", "wlan0")  # Wi-Fi kapalı
    tab = _tab()
    assert _wait(lambda: tab._status is not None and _idle(tab))
    assert not tab._hotspot_card.isVisible()


def test_turning_on_the_hotspot_goes_through_dialog_and_backend(tab_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page

    shown = []

    class FakeDialog:
        def __init__(self, ssid, password, parent=None):
            shown.append((ssid, password))

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return "Benim Ağım", "yeni-sifre-77"

    monkeypatch.setattr(page, "HotspotDialog", FakeDialog)
    tab = _tab()
    assert _wait(lambda: tab._status is not None and _idle(tab))
    tab._hotspot_card._button.click()
    assert _wait(lambda: ("start", "wlan0", "Benim Ağım", "yeni-sifre-77") in tab_env["calls"])
    assert shown == [("Linwas Evi", "gizli-sifre-1")]  # önerilen değerlerle açıldı
    assert ("note", "Ev Ağı") in tab_env["calls"]  # ağdan ayrılma kopma sayılmaz
    assert _wait(lambda: _idle(tab))


def test_cancelled_dialog_starts_nothing(tab_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page

    class FakeDialog:
        def __init__(self, ssid, password, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(page, "HotspotDialog", FakeDialog)
    tab = _tab()
    assert _wait(lambda: tab._status is not None and _idle(tab))
    tab._hotspot_card._button.click()
    assert _wait(lambda: tab._hotspot_job is None and tab._hotspot_card._button.isEnabled())
    assert not any(call[0] in ("start", "note") for call in tab_env["calls"])


def test_failed_start_shows_the_error(tab_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page

    class FakeDialog:
        def __init__(self, ssid, password, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return "Ağ", "gizli-sifre-1"

    errors = []
    monkeypatch.setattr(page, "HotspotDialog", FakeDialog)
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(details)
    )
    monkeypatch.setattr(network, "hotspot_start", lambda d, s, p: (False, "Error: yok"))
    tab = _tab()
    assert _wait(lambda: tab._status is not None and _idle(tab))
    tab._hotspot_card._button.click()
    assert _wait(lambda: errors == ["Error: yok"])


def test_active_hotspot_replaces_the_network_views(tab_env):
    tab_env["status"] = WifiStatus(True, True, "Linwas Hotspot", "wlan0", 0, "10.42.0.1")
    tab_env["hotspot"] = AP
    tab = _tab()
    assert _wait(lambda: tab._hotspot is not None)
    assert tab._status_card._title.text() == "Hotspot is on"
    assert "Linwas Evi" in tab._status_card._subtitle.text()
    assert (
        not tab._status_card._toggle.isVisible()
    )  # Wi-Fi aç/kapat yok: hotspot kartından kapatılır
    assert not tab._list_card.isVisible() and not tab._details_card.isVisible()
    assert not tab._quality.isVisible()
    assert tab._hotspot_card.isVisible() and tab._hotspot_card._button.text() == "Turn off"


def test_turning_off_the_hotspot_stops_the_profile(tab_env):
    tab_env["status"] = WifiStatus(True, True, "Linwas Hotspot", "wlan0", 0, "10.42.0.1")
    tab_env["hotspot"] = AP
    tab = _tab()
    assert _wait(lambda: tab._hotspot is not None)
    tab._hotspot_card._button.click()
    assert _wait(lambda: ("stop", "Linwas Hotspot") in tab_env["calls"])
    assert _wait(lambda: _idle(tab))
