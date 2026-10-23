"""Bluetooth cihaz ayarları penceresi ve sekmedeki "Ayarlar" düğmesi (PySide6 gerektirir)."""

import os

import pytest

from linwas.backend import netquality, network
from linwas.backend.network import BluetoothDevice
from linwas.core.netlog import BluetoothSummary

HEADSET = BluetoothDevice(
    "AA:00:00:00:00:01", "Kulaklık", True, False, "audio-headset", trusted=True
)
MOUSE = BluetoothDevice("AA:00:00:00:00:02", "Fare", True, True, "input-mouse", trusted=False)
NEW = BluetoothDevice("AA:00:00:00:00:03", "Hoparlör", False, False)


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


@pytest.fixture(autouse=True)
def _no_history(monkeypatch):
    """Pencere geçmişi diskten okumasın; testler kendi özetini verir."""
    from linwas.ui.pages import network_bluetooth as module

    monkeypatch.setattr(module, "device_history", lambda mac: BluetoothSummary(0, 0, None, None))
    monkeypatch.setattr(module.btaudio, "audio_info", lambda mac: None)  # gerçek pactl çağrılmasın


# --- Geçmiş metni ---


@pytest.mark.parametrize(
    ("drops", "icon", "shown"),
    [
        (0, "audio-headset", False),
        (2, "audio-headset", False),  # az kopma gürültü sayılır
        (3, "audio-headset", True),
        (9, "phone", True),
        (9, "input-mouse", False),  # fare/klavye uyur: kopma arıza değil
        (9, "input-keyboard", False),
    ],
)
def test_history_text_only_when_meaningful(qapp, drops, icon, shown):
    from linwas.ui.pages.network_bluetooth import history_text

    text = history_text(BluetoothSummary(100, drops, None, None), icon)
    assert bool(text) is shown
    if shown:
        assert str(drops) in text and "7 days" in text


# --- Pencere ---


def _dialog(device):
    from linwas.ui.pages.network_bluetooth import BluetoothDeviceDialog

    dlg = BluetoothDeviceDialog(device)
    dlg.show()
    return dlg


def test_dialog_prefills_and_reports_only_changes(qapp):
    dlg = _dialog(HEADSET)
    assert dlg._name.text() == "Kulaklık" and dlg._auto.isChecked()
    change = dlg.change()
    assert (change.name, change.trusted) == (None, None)  # dokunulmadı

    dlg._name.setText("  Oturma   Odası  ")
    assert dlg.change().name == "Oturma Odası" and dlg.change().trusted is None
    dlg._auto.setChecked(False)
    assert dlg.change().trusted is False
    dlg._name.setText("")  # boş: cihazın kendi adına dön
    assert dlg.change().name == ""
    dlg._name.setText("Kulaklık  ")  # boşluk farkı değişiklik sayılmaz
    assert dlg.change().name is None


def test_dialog_untrusted_device_starts_unchecked(qapp):
    dlg = _dialog(MOUSE)
    assert not dlg._auto.isChecked()
    dlg._auto.setChecked(True)
    assert dlg.change().trusted is True


def test_dialog_limits_the_name_length(qapp):
    dlg = _dialog(HEADSET)
    dlg._name.setText("a" * 100)
    assert len(dlg._name.text()) == network.ALIAS_MAX


def test_dialog_rejects_control_characters_pasted_into_the_name(qapp):
    dlg = _dialog(HEADSET)
    dlg._name.setText("bir\x07ad")
    dlg.accept()
    assert dlg.result() == 0 and dlg._error.isVisible()  # kapanmadı
    dlg._name.setText("Temiz Ad")
    dlg.accept()
    assert dlg.result() == 1


def test_dialog_shows_history_only_when_it_has_something_to_say(qapp, monkeypatch):
    from linwas.ui.pages import network_bluetooth as module

    quiet = _dialog(HEADSET)
    assert _wait(lambda: not quiet._jobs._jobs)
    assert not quiet._history.isVisible()

    monkeypatch.setattr(module, "device_history", lambda mac: BluetoothSummary(500, 5, 40, 20))
    noisy = _dialog(HEADSET)
    assert _wait(lambda: noisy._history.isVisible())
    assert "5 times" in noisy._history.text()
    sleepy = _dialog(MOUSE)  # fare: kopma sayılmaz
    assert _wait(lambda: not sleepy._jobs._jobs)
    assert not sleepy._history.isVisible()


# --- Sekme ---


@pytest.fixture
def bt_env(qapp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    calls: list[tuple] = []
    monkeypatch.setattr(network, "bluetooth_state", lambda: "on")
    monkeypatch.setattr(network, "bluetooth_list_devices", lambda: [HEADSET, MOUSE, NEW])
    monkeypatch.setattr(
        netquality, "note_user_action", lambda kind, name, ident="": calls.append(("note", name))
    )
    monkeypatch.setattr(
        network,
        "bluetooth_rename",
        lambda mac, name: calls.append(("rename", mac, name)) or (True, ""),
    )
    monkeypatch.setattr(
        network,
        "bluetooth_set_trusted",
        lambda mac, trusted: calls.append(("trust", mac, trusted)) or True,
    )
    monkeypatch.setattr(
        network, "bluetooth_disconnect", lambda mac: calls.append(("disconnect", mac)) or (True, "")
    )
    monkeypatch.setattr(
        network, "bluetooth_forget", lambda mac: calls.append(("forget", mac)) or True
    )
    return calls


def _tab():
    from linwas.ui.pages.network import _BtTab, _Row

    tab = _BtTab()
    tab.show()
    assert _wait(lambda: len(tab._mine.findChildren(_Row)) == 2)
    return tab


def _button(tab, device_name, label):
    """`device_name` satırındaki `label` düğmesi (eşleşmiş cihazlar kartında)."""
    from PySide6.QtWidgets import QLabel, QPushButton

    from linwas.ui.pages.network import _Row

    for row in tab._mine.findChildren(_Row):
        if any(lbl.text() == device_name for lbl in row.findChildren(QLabel)):
            return next(b for b in row.findChildren(QPushButton) if b.text() == label)
    raise AssertionError(f"{device_name} satırı yok")


def _fake_dialog(monkeypatch, outcome, change=None):
    """Sayfadaki cihaz ayarları penceresini taklit eder; açılan cihazları döndürür."""
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page
    from linwas.ui.pages.network_bluetooth import BluetoothChange

    opened = []

    class FakeDialog:
        def __init__(self, device, parent=None):
            opened.append(device)

        def exec(self):
            return outcome

        def change(self):
            return change or BluetoothChange()

    monkeypatch.setattr(page, "BluetoothDeviceDialog", FakeDialog)
    assert outcome in (QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected)
    return opened


def test_rows_mark_only_the_exception_and_offer_settings_for_paired(bt_env):
    from PySide6.QtWidgets import QLabel, QPushButton

    tab = _tab()
    texts = [label.text() for label in tab._mine.findChildren(QLabel)]
    assert "Paired, not connected" in texts  # güvenilir kulaklık: ek not yok
    assert any(t.startswith("Connected") and "won't connect by itself" in t for t in texts)
    assert _button(tab, "Kulaklık", "Settings") and _button(tab, "Fare", "Settings")
    assert not [b for b in tab._nearby.findChildren(QPushButton) if b.text() == "Settings"]


def test_settings_dialog_applies_rename_and_trust(bt_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages.network_bluetooth import BluetoothChange

    opened = _fake_dialog(
        monkeypatch, QDialog.DialogCode.Accepted, BluetoothChange(name="Salon", trusted=False)
    )
    tab = _tab()
    _button(tab, "Fare", "Settings").click()
    assert _wait(lambda: ("trust", MOUSE.mac, False) in bt_env)
    assert opened == [MOUSE] and ("rename", MOUSE.mac, "Salon") in bt_env
    assert _wait(lambda: not tab._busy)


def test_only_the_changed_field_is_written(bt_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages.network_bluetooth import BluetoothChange

    _fake_dialog(monkeypatch, QDialog.DialogCode.Accepted, BluetoothChange(trusted=True))
    tab = _tab()
    _button(tab, "Fare", "Settings").click()
    assert _wait(lambda: ("trust", MOUSE.mac, True) in bt_env and not tab._busy)
    assert not [c for c in bt_env if c[0] == "rename"]


def test_unchanged_or_cancelled_dialog_runs_nothing(bt_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    tab = _tab()
    _fake_dialog(monkeypatch, QDialog.DialogCode.Accepted)  # değişiklik yok
    _button(tab, "Fare", "Settings").click()
    _fake_dialog(monkeypatch, QDialog.DialogCode.Rejected)
    _button(tab, "Kulaklık", "Settings").click()
    assert not tab._busy and bt_env == []


def test_failed_settings_show_an_error(bt_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page
    from linwas.ui.pages.network_bluetooth import BluetoothChange

    _fake_dialog(
        monkeypatch, QDialog.DialogCode.Accepted, BluetoothChange(name="Salon", trusted=True)
    )
    errors = []
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(details)
    )
    monkeypatch.setattr(network, "bluetooth_rename", lambda mac, name: (False, "Access denied"))
    monkeypatch.setattr(network, "bluetooth_set_trusted", lambda mac, trusted: False)
    tab = _tab()
    _button(tab, "Fare", "Settings").click()
    assert _wait(lambda: len(errors) == 1)
    assert "Access denied" in errors[0] and "trust" in errors[0]


def test_disconnect_and_forget_are_marked_as_user_actions(bt_env, monkeypatch):
    from linwas.ui.pages import network as page

    monkeypatch.setattr(page, "_confirm_forget", lambda parent, name, text: True)
    tab = _tab()
    _button(tab, "Fare", "Disconnect").click()
    assert _wait(lambda: ("disconnect", MOUSE.mac) in bt_env)
    assert bt_env.index(("note", "Fare")) < bt_env.index(("disconnect", MOUSE.mac))  # önce işaret
    assert _wait(lambda: not tab._busy)
    _button(tab, "Kulaklık", "Forget").click()
    assert _wait(lambda: ("forget", HEADSET.mac) in bt_env)
    assert ("note", "Kulaklık") in bt_env


def test_turning_bluetooth_off_marks_connected_devices(bt_env, monkeypatch):
    toggled = []
    monkeypatch.setattr(network, "bluetooth_set_enabled", lambda on: toggled.append(on) or True)
    tab = _tab()
    tab._toggle_bt()
    assert _wait(lambda: toggled == [False])
    assert ("note", "Fare") in bt_env  # yalnızca bağlı olan
    assert ("note", "Kulaklık") not in bt_env
