"""Ağ ayarları penceresi ve Wi-Fi sekmesindeki "Ayarlar" düğmesi (PySide6 gerektirir)."""

import os

import pytest

from linwas.backend import network
from linwas.backend.network import ProfileChange, WifiProfile

AUTO = WifiProfile("Ev Ağı")
MANUAL = WifiProfile(
    "Ev Ağı",
    autoconnect=False,
    metered="yes",
    ipv4_method="manual",
    address="192.168.1.50",
    prefix=24,
    gateway="192.168.1.1",
    dns=["1.1.1.1", "1.0.0.1"],
    ignore_auto_dns=True,
)


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


def _dialog(profile, active=False):
    from linwas.ui.pages.network_profile_dialog import NetworkSettingsDialog

    dlg = NetworkSettingsDialog(profile, active)
    dlg.show()
    return dlg


def test_auto_profile_shows_only_the_basics(qapp):
    dlg = _dialog(AUTO)
    assert dlg._auto.isChecked() and dlg._metered.currentData() == "unknown"
    assert dlg._dns.currentData() == "auto"
    # Süzülmüş görünüm: özel DNS alanları ve elle IP alanları varsayılan gizli
    assert not dlg._dns_custom.isVisible()
    assert not dlg._advanced.isVisible() and not dlg._address.isVisible()
    change = dlg.change()
    assert (change.autoconnect, change.metered, change.ipv4_method) == (True, "unknown", "auto")
    assert change.dns_choice == "auto"
    network.build_modify_args("Ev Ağı", change)  # geçerli


def test_manual_profile_opens_advanced_and_prefills(qapp):
    dlg = _dialog(MANUAL, active=True)
    assert dlg._advanced.isVisible() and dlg._toggle.isChecked()
    assert dlg._ip_mode.currentData() == "manual" and dlg._address.isVisible()
    assert (dlg._address.text(), dlg._mask.text(), dlg._gateway.text()) == (
        "192.168.1.50",
        "255.255.255.0",
        "192.168.1.1",
    )
    assert dlg._dns.currentData() == "cloudflare" and not dlg._dns_custom.isVisible()
    assert not dlg._auto.isChecked() and dlg._metered.currentData() == "yes"
    from PySide6.QtWidgets import QLabel

    assert any("reconnect" in label.text() for label in dlg.findChildren(QLabel))  # etkin ağ notu


def test_custom_dns_fields_and_validation_messages(qapp):
    dlg = _dialog(AUTO)
    dlg._dns.setCurrentIndex(dlg._dns.findData("custom"))
    assert dlg._dns_custom.isVisible()
    dlg._dns1.setText("abc")
    dlg.accept()
    assert dlg.result() == 0 and dlg._error.isVisible()  # kapanmadı
    assert "valid DNS" in dlg._error.text()
    dlg._dns1.setText("9.9.9.9")
    dlg._dns2.setText("149.112.112.112")
    dlg.accept()
    assert dlg.result() == 1  # kabul edildi
    assert dlg.change().dns == ["9.9.9.9", "149.112.112.112"]


def test_manual_ip_errors_open_advanced_section(qapp):
    dlg = _dialog(AUTO)
    dlg._ip_mode.setCurrentIndex(dlg._ip_mode.findData("manual"))
    assert not dlg._advanced.isVisible()  # henüz açılmadı
    dlg._address.setText("kötü")
    dlg.accept()
    assert dlg.result() == 0 and "IP address" in dlg._error.text()
    assert dlg._advanced.isVisible()  # hatalı alan gizli kalmaz
    dlg._address.setText("192.168.1.60")
    dlg._gateway.setText("192.168.1.1")
    dlg.accept()  # DNS hâlâ otomatik: elle IP ile çalışmaz
    assert dlg.result() == 0 and "choose a DNS server" in dlg._error.text()
    dlg._dns.setCurrentIndex(dlg._dns.findData("google"))
    dlg.accept()
    assert dlg.result() == 1
    change = dlg.change()
    assert (change.ipv4_method, change.address, change.dns_choice) == (
        "manual",
        "192.168.1.60",
        "google",
    )


def test_special_ip_mode_is_left_untouched(qapp):
    shared = WifiProfile("Hotspot", ipv4_method="shared")
    dlg = _dialog(shared)
    assert not shared.ip_editable
    assert not dlg._ip_mode.isVisible() and dlg._special.isVisible()
    assert dlg._advanced.isVisible()  # açıklama görünsün diye açık
    assert dlg.change().ipv4_method is None  # IP'ye dokunulmaz


def test_wifi_tab_settings_button_saves_through_backend(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QDialog, QPushButton

    from linwas.ui.pages import network as page
    from linwas.ui.pages import network_profile_dialog as dialog_module

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    status = network.WifiStatus(True, True, "Ev Ağı", "wlan0", 72, "192.168.1.50")
    nets = [
        network.WifiNetwork("Ev Ağı", 72, "WPA2", True, "A", saved=True),
        network.WifiNetwork("Kafe", 60, "WPA2", False, "B"),
    ]
    monkeypatch.setattr(network, "wifi_status", lambda: status)
    monkeypatch.setattr(network, "wifi_list", lambda rescan=True: nets)
    monkeypatch.setattr(network, "wifi_details", lambda s: None)
    monkeypatch.setattr(network, "wifi_profile", lambda name: MANUAL if name == "Ev Ağı" else None)
    saved = []
    monkeypatch.setattr(
        network,
        "wifi_profile_save",
        lambda name, change, reconnect=False: saved.append((name, change, reconnect)) or (True, ""),
    )

    class FakeDialog:
        def __init__(self, profile, active, parent=None, secured=False):
            assert profile is MANUAL and active is True and secured is True

        def exec(self):
            return QDialog.DialogCode.Accepted

        def change(self):
            return ProfileChange(
                autoconnect=True, ipv4_method="manual", address="192.168.1.51",
                netmask="255.255.255.0", gateway="192.168.1.1", dns_choice="cloudflare",
            )  # fmt: skip

    monkeypatch.setattr(page, "NetworkSettingsDialog", FakeDialog)
    assert dialog_module.NetworkSettingsDialog is not FakeDialog  # yalnızca sayfadaki ad değişti
    tab = page._WifiTab()
    tab.show()
    assert _wait(lambda: any(b.text() == "Settings" for b in tab.findChildren(QPushButton)))
    buttons = [b for b in tab.findChildren(QPushButton) if b.text() == "Settings"]
    assert len(buttons) == 1  # yalnızca kayıtlı ağda
    buttons[0].click()
    assert _wait(lambda: len(saved) == 1)
    name, change, reconnect = saved[0]
    assert name == "Ev Ağı" and change.address == "192.168.1.51"
    assert reconnect is True  # etkin ağda IP değişti: yeniden bağlanır
    assert _wait(lambda: tab._profile_job is None and not tab._busy)


def test_password_row_only_for_secured_networks(qapp):
    from linwas.ui.pages.network_profile_dialog import NetworkSettingsDialog

    open_net = NetworkSettingsDialog(AUTO, False, secured=False)
    assert not hasattr(open_net, "_password")
    dlg = NetworkSettingsDialog(AUTO, False, secured=True)
    dlg.show()
    row = dlg._password
    assert row._edit.isVisible() and row._edit.text() == ""  # varsayılan gizli, okunmaz
    assert not row._copy.isEnabled()


def test_dialog_reads_the_password_of_its_own_network_on_demand(qapp, monkeypatch):
    from linwas.ui.pages.network_profile_dialog import NetworkSettingsDialog

    reads = []
    monkeypatch.setattr(network, "wifi_password", lambda name: reads.append(name) or "gizli şifre")
    dlg = NetworkSettingsDialog(AUTO, False, secured=True)
    dlg.show()
    assert reads == []  # açılışta okunmaz
    dlg._password._show.click()
    assert _wait(lambda: dlg._password.revealed)
    assert reads == ["Ev Ağı"] and dlg._password._edit.text() == "gizli şifre"
    dlg.hide()  # pencere kapanınca şifre ekrandan silinir
    assert not dlg._password.revealed and dlg._password._edit.text() == ""
