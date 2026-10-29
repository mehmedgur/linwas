# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Bluetooth: ses modu, dosya gönderme ve "Bu bilgisayar" kartı (PySide6 gerektirir)."""

import os

import pytest

from linwas.backend import btaudio, btfile, netquality, network
from linwas.backend.btaudio import CALLS, MUSIC, AudioCard, AudioProfile, BtAudio
from linwas.backend.network import BluetoothAdapter, BluetoothDevice
from linwas.core.netlog import BluetoothSummary

HEADSET = BluetoothDevice(
    "AA:00:00:00:00:01", "Kulaklık", True, True, "audio-headset", trusted=True
)
PHONE = BluetoothDevice("AA:00:00:00:00:04", "Telefon", True, True, "phone", trusted=True)
IDLE_PHONE = BluetoothDevice(
    "AA:00:00:00:00:05", "Eski Telefon", True, False, "phone", trusted=True
)
MOUSE = BluetoothDevice("AA:00:00:00:00:02", "Fare", True, True, "input-mouse", trusted=True)


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


def _audio(mode=CALLS, is_output=False, modes=(MUSIC, CALLS)):
    card = AudioCard(
        "bluez_card.AA_00_00_00_00_01",
        "AA:00:00:00:00:01",
        [AudioProfile("a2dp-sink", "Music", 40), AudioProfile("headset-head-unit", "Calls", 30)],
        "headset-head-unit" if mode == CALLS else "a2dp-sink",
    )
    return BtAudio(card=card, modes=list(modes), mode=mode, is_output=is_output)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from linwas.ui.pages import network_bluetooth as module

    monkeypatch.setattr(module, "device_history", lambda mac: BluetoothSummary(0, 0, None, None))
    monkeypatch.setattr(module.btaudio, "audio_info", lambda mac: None)


# --- Ses bölümü ---


def _dialog(device):
    from linwas.ui.pages.network_bluetooth import BluetoothDeviceDialog

    dlg = BluetoothDeviceDialog(device)
    dlg.show()
    return dlg


def test_sound_section_shows_two_plain_modes(qapp, monkeypatch):
    monkeypatch.setattr(btaudio, "audio_info", lambda mac: _audio(CALLS))
    dlg = _dialog(HEADSET)
    assert _wait(lambda: dlg._sound.isVisible())
    texts = [dlg._mode.itemText(i) for i in range(dlg._mode.count())]
    assert texts == [
        "Music (best sound quality)",
        "Calls (uses the microphone)",
    ]  # ham profil adı yok
    assert dlg._mode.currentData() == CALLS  # şimdiki mod seçili
    assert not dlg._output.isChecked() and dlg._output.isEnabled()
    assert dlg.change().audio_mode is None and dlg.change().make_output is False  # dokunulmadı


def test_sound_changes_are_reported(qapp, monkeypatch):
    monkeypatch.setattr(btaudio, "audio_info", lambda mac: _audio(CALLS))
    dlg = _dialog(HEADSET)
    assert _wait(lambda: dlg._sound.isVisible())
    dlg._mode.setCurrentIndex(dlg._mode.findData(MUSIC))
    dlg._output.setChecked(True)
    change = dlg.change()
    assert (change.audio_mode, change.make_output) == (MUSIC, True)


def test_device_that_is_already_the_output_has_nothing_to_turn_on(qapp, monkeypatch):
    monkeypatch.setattr(btaudio, "audio_info", lambda mac: _audio(MUSIC, is_output=True))
    dlg = _dialog(HEADSET)
    assert _wait(lambda: dlg._sound.isVisible())
    assert dlg._output.isChecked() and not dlg._output.isEnabled()
    assert dlg.change().make_output is False


def test_single_mode_device_and_unknown_active_mode(qapp, monkeypatch):
    monkeypatch.setattr(btaudio, "audio_info", lambda mac: _audio("", modes=(MUSIC,)))
    dlg = _dialog(HEADSET)
    assert _wait(lambda: dlg._sound.isVisible())
    assert dlg._mode.count() == 1 and dlg._mode.currentIndex() == -1  # şimdiki mod bilinmiyor
    assert dlg.change().audio_mode is None  # seçim yapılmadan değişiklik yok
    dlg._mode.setCurrentIndex(0)
    assert dlg.change().audio_mode == MUSIC


def test_sound_section_is_hidden_without_a_sound_card(qapp, monkeypatch):
    asked = []
    monkeypatch.setattr(btaudio, "audio_info", lambda mac: asked.append(mac) or None)
    dlg = _dialog(HEADSET)
    assert _wait(lambda: not dlg._jobs._jobs)
    assert asked == [HEADSET.mac] and not dlg._sound.isVisible()
    # bağlı olmayan cihazda ses sunucusuna hiç sorulmaz
    asked.clear()
    offline = _dialog(BluetoothDevice("AA:00:00:00:00:09", "Kapalı", True, False, "audio-headset"))
    assert _wait(lambda: not offline._jobs._jobs)
    assert asked == [] and not offline._sound.isVisible()


# --- Sekme: ses, dosya gönderme, bu bilgisayar ---


@pytest.fixture
def bt_state():
    return {
        "devices": [HEADSET, PHONE, IDLE_PHONE, MOUSE],
        "adapter": BluetoothAdapter("virci", False, 180, True),
    }


@pytest.fixture
def bt_env(qapp, monkeypatch, tmp_path, bt_state):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "d"))
    calls: list[tuple] = []
    monkeypatch.setattr(network, "bluetooth_state", lambda: "on")
    monkeypatch.setattr(network, "bluetooth_list_devices", lambda: bt_state["devices"])
    monkeypatch.setattr(network, "bluetooth_adapter_info", lambda: bt_state["adapter"])
    monkeypatch.setattr(netquality, "note_user_action", lambda *a, **k: None)
    return calls


def _tab(paired=4):
    from linwas.ui.pages.network import _BtTab, _Row

    tab = _BtTab()
    tab.show()
    assert _wait(lambda: len(tab._mine.findChildren(_Row)) == paired)
    return tab


def _button(tab, device_name, label):
    from PySide6.QtWidgets import QLabel, QPushButton

    from linwas.ui.pages.network import _Row

    for row in tab._mine.findChildren(_Row):
        if any(lbl.text() == device_name for lbl in row.findChildren(QLabel)):
            return next((b for b in row.findChildren(QPushButton) if b.text() == label), None)
    raise AssertionError(f"{device_name} satırı yok")


def test_send_file_button_only_for_connected_phones_and_computers(bt_env):
    tab = _tab()
    assert _button(tab, "Telefon", "Send file…") is not None
    assert _button(tab, "Eski Telefon", "Send file…") is None  # bağlı değil
    assert _button(tab, "Kulaklık", "Send file…") is None  # ses cihazı dosya almaz
    assert _button(tab, "Fare", "Send file…") is None


def _fake_files(monkeypatch, paths):
    from PySide6.QtWidgets import QFileDialog

    asked = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda parent, title: asked.append(title) or (paths, "")
    )
    return asked


def test_send_file_starts_the_desktop_tool_with_the_chosen_files(bt_env, monkeypatch):
    sent = []
    monkeypatch.setattr(btfile, "available_tool", lambda: "bluetooth-sendto")
    monkeypatch.setattr(
        btfile, "send", lambda mac, paths: sent.append((mac, list(paths))) or (True, "")
    )
    asked = _fake_files(monkeypatch, ["/tmp/a.txt", "/tmp/b.jpg"])
    tab = _tab()
    _button(tab, "Telefon", "Send file…").click()
    assert sent == [(PHONE.mac, ["/tmp/a.txt", "/tmp/b.jpg"])]
    assert "Telefon" in asked[0]


def test_send_file_without_a_tool_explains_what_is_needed(bt_env, monkeypatch):
    from linwas.ui.pages import network as page

    errors = []
    monkeypatch.setattr(btfile, "available_tool", lambda: None)
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(text)
    )
    asked = _fake_files(monkeypatch, ["/tmp/a.txt"])
    tab = _tab()
    _button(tab, "Telefon", "Send file…").click()
    assert len(errors) == 1 and "bluetooth-sendto" in errors[0] and "blueman-sendto" in errors[0]
    assert asked == []  # dosya seçtirmeden önce söylenir


def test_cancelled_file_dialog_sends_nothing(bt_env, monkeypatch):
    monkeypatch.setattr(btfile, "available_tool", lambda: "bluetooth-sendto")
    monkeypatch.setattr(btfile, "send", lambda *a: pytest.fail("gönderilmemeli"))
    _fake_files(monkeypatch, [])
    tab = _tab()
    _button(tab, "Telefon", "Send file…").click()


def test_a_tool_that_fails_to_start_shows_its_message(bt_env, monkeypatch):
    from linwas.ui.pages import network as page

    errors = []
    monkeypatch.setattr(btfile, "available_tool", lambda: "bluetooth-sendto")
    monkeypatch.setattr(btfile, "send", lambda mac, paths: (False, "izin yok"))
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(details)
    )
    _fake_files(monkeypatch, ["/tmp/a.txt"])
    tab = _tab()
    _button(tab, "Telefon", "Send file…").click()
    assert errors == ["izin yok"]


def test_settings_applies_the_sound_choices_through_the_audio_backend(bt_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page
    from linwas.ui.pages.network_bluetooth import BluetoothChange

    class FakeDialog:
        def __init__(self, device, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def change(self):
            return BluetoothChange(audio_mode=MUSIC, make_output=True)

    applied = []
    monkeypatch.setattr(page, "BluetoothDeviceDialog", FakeDialog)
    monkeypatch.setattr(
        btaudio, "apply", lambda mac, mode, out: applied.append((mac, mode, out)) or []
    )
    tab = _tab()
    _button(tab, "Kulaklık", "Settings").click()
    assert _wait(lambda: applied == [(HEADSET.mac, MUSIC, True)])  # yalnızca ses değişse de çalışır
    assert _wait(lambda: not tab._busy)


def test_failed_sound_change_is_reported(bt_env, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from linwas.ui.pages import network as page
    from linwas.ui.pages.network_bluetooth import BluetoothChange

    class FakeDialog:
        def __init__(self, device, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def change(self):
            return BluetoothChange(audio_mode=CALLS)

    errors = []
    monkeypatch.setattr(page, "BluetoothDeviceDialog", FakeDialog)
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(details)
    )
    monkeypatch.setattr(btaudio, "apply", lambda mac, mode, out: ["no such profile"])
    tab = _tab()
    _button(tab, "Kulaklık", "Settings").click()
    assert _wait(lambda: errors == ["no such profile"])


# --- "Bu bilgisayar" kartı ---


def test_computer_card_states(qapp):
    from linwas.ui.pages.network_bluetooth import ComputerCard

    card = ComputerCard()
    card.show()
    requested = []
    card.visibility_requested.connect(requested.append)
    card.show_adapter(BluetoothAdapter("virci", False, 180, True))
    assert "“virci”" in card._name.text() and "hidden" in card._state.text()
    assert card._toggle.text() == "Make visible" and card._toggle.property("primary") is True
    card._toggle.click()
    card.show_adapter(BluetoothAdapter("virci", True, 180, True))
    assert "visible to nearby" in card._state.text() and card._toggle.text() == "Hide now"
    assert card._toggle.property("primary") is False
    card._toggle.click()
    assert requested == [True, False]
    card.set_busy()
    assert not card._toggle.isEnabled() and not card._rename.isEnabled()
    card.show_adapter(BluetoothAdapter("virci", True, 180, True))
    assert card._toggle.isEnabled() and card._rename.isEnabled()  # yenilenince yeniden açılır


def test_computer_card_is_shown_only_when_there_is_an_adapter(bt_env, bt_state):
    tab = _tab()
    assert _wait(lambda: tab._computer.isVisible())
    assert tab._computer.info.alias == "virci"
    bt_state["adapter"] = None  # denetleyici bilgisi alınamadı
    tab._load()
    assert _wait(lambda: not tab._computer.isVisible())


def test_visibility_button_changes_the_adapter_and_failures_are_reported(
    bt_env, bt_state, monkeypatch
):
    from linwas.ui.pages import network as page

    changes, errors = [], []

    def set_visible(visible, seconds=180):
        changes.append(visible)
        bt_state["adapter"] = BluetoothAdapter("virci", visible, 180, True)
        return True

    monkeypatch.setattr(network, "bluetooth_set_visible", set_visible)
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(text)
    )
    tab = _tab()
    assert _wait(lambda: tab._computer.isVisible())
    tab._computer._toggle.click()
    assert _wait(lambda: changes == [True] and tab._computer._toggle.text() == "Hide now")
    tab._computer._toggle.click()
    assert _wait(
        lambda: changes == [True, False] and tab._computer._toggle.text() == "Make visible"
    )
    assert errors == []
    monkeypatch.setattr(network, "bluetooth_set_visible", lambda visible, seconds=180: False)
    tab._computer._toggle.click()
    assert _wait(lambda: len(errors) == 1 and "visibility" in errors[0])


def test_computer_rename_asks_validates_and_writes(bt_env, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from linwas.ui.pages import network as page

    written, errors = [], []
    monkeypatch.setattr(
        network, "bluetooth_set_computer_name", lambda name: written.append(name) or (True, "")
    )
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(text)
    )
    answers = iter([("  Salon   PC ", True), ("", False), ("kötü\x07", True)])
    prompts = []

    def get_text(parent, title, label, mode, text):
        prompts.append(text)
        return next(answers)

    monkeypatch.setattr(QInputDialog, "getText", get_text)
    tab = _tab()
    assert _wait(lambda: tab._computer.isVisible())
    tab._computer._rename.click()
    assert _wait(lambda: written == ["Salon PC"])  # boşluklar sadeleşir
    assert prompts == ["virci"]  # mevcut ad önerilir
    assert _wait(lambda: not tab._busy and tab._computer._rename.isEnabled())  # yenileme bitti
    tab._computer._rename.click()  # vazgeçildi
    assert written == ["Salon PC"]
    assert _wait(lambda: tab._computer._rename.isEnabled())
    tab._computer._rename.click()  # geçersiz ad hiçbir şey yazmaz
    assert written == ["Salon PC"] and errors == ["This name is not valid."]


def test_failed_computer_rename_is_reported(bt_env, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from linwas.ui.pages import network as page

    errors = []
    monkeypatch.setattr(
        network, "bluetooth_set_computer_name", lambda name: (False, "Access denied")
    )
    monkeypatch.setattr(
        page, "_show_error", lambda parent, title, text, details: errors.append(details)
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *a: ("Yeni", True))
    tab = _tab()
    assert _wait(lambda: tab._computer.isVisible())
    tab._computer._rename.click()
    assert _wait(lambda: errors == ["Access denied"])
