# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Bluetooth ses cihazları: pactl çıktısı ayrıştırma ve komut üretimi (Qt'siz)."""

import pytest

from linwas.backend import btaudio, network
from linwas.backend.btaudio import CALLS, MUSIC

MAC = "AA:BB:CC:DD:EE:FF"

# pactl.c'deki biçim dizelerinden üretilmiş örnek (PulseAudio)
CARDS_PA = (
    "Card #3\n"
    "\tName: alsa_card.pci-0000_00_1f.3\n"
    "\tDriver: module-alsa-card.c\n"
    "\tOwner Module: 7\n"
    "\tProperties:\n"
    '\t\tdevice.description = "Dahili Ses"\n'
    "\tProfiles:\n"
    "\t\toutput:analog-stereo: Analog Stereo Output (sinks: 1, sources: 0, priority: 6500, "
    "available: yes)\n"
    "\tActive Profile: output:analog-stereo\n"
    "\n"
    "Card #5\n"
    "\tName: bluez_card.AA_BB_CC_DD_EE_FF\n"
    "\tDriver: module-bluez5-device.c\n"
    "\tOwner Module: 28\n"
    "\tProperties:\n"
    '\t\tdevice.description = "Kulaklık"\n'
    '\t\tdevice.string = "AA:BB:CC:DD:EE:FF"\n'
    "\tProfiles:\n"
    "\t\theadset-head-unit: Headset Head Unit (HSP/HFP) (sinks: 1, sources: 1, priority: 30, "
    "available: yes)\n"
    "\t\ta2dp-sink: High Fidelity Playback (A2DP Sink) (sinks: 1, sources: 0, priority: 40, "
    "available: yes)\n"
    "\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)\n"
    "\tActive Profile: a2dp-sink\n"
    "\tPorts:\n"
    "\t\theadset-output: Headset (type: Headset, priority: 0, latency offset: 0 usec, "
    "availability unknown)\n"
    "\t\t\tPart of profile(s): headset-head-unit, a2dp-sink\n"
)

# PipeWire: codec'li profil adları, kullanılamayan bir profil
CARDS_PW = (
    "Card #60\n"
    "\tName: bluez_card.11_22_33_44_55_66\n"
    "\tDriver: module-bluez5-device.c\n"
    "\tOwner Module: 4294967295\n"
    "\tProperties:\n"
    '\t\tdevice.api = "bluez5"\n'
    "\tProfiles:\n"
    "\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)\n"
    "\t\ta2dp-sink: High Fidelity Playback (A2DP Sink, codec AAC) (sinks: 1, sources: 0, "
    "priority: 16, available: yes)\n"
    "\t\ta2dp-sink-sbc: High Fidelity Playback (A2DP Sink, codec SBC) (sinks: 1, sources: 0, "
    "priority: 18, available: yes)\n"
    "\t\theadset-head-unit-msbc: Headset Head Unit (HSP/HFP, codec mSBC) (sinks: 1, sources: 1, "
    "priority: 20, available: no)\n"
    "\t\theadset-head-unit-cvsd: Headset Head Unit (HSP/HFP, codec CVSD) (sinks: 1, sources: 1, "
    "priority: 10, available: yes)\n"
    "\tActive Profile: headset-head-unit-cvsd\n"
)

SINKS = (
    "1\talsa_output.pci-0000_00_1f.3.analog-stereo\tmodule-alsa-card.c\ts16le 2ch 44100Hz\t"
    "RUNNING\n"
    "7\tbluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink\tmodule-bluez5-device.c\ts16le 2ch 44100Hz\tIDLE\n"
)


def test_parse_cards_keeps_only_bluetooth_cards():
    cards = btaudio.parse_cards(CARDS_PA)
    assert [c.name for c in cards] == ["bluez_card.AA_BB_CC_DD_EE_FF"]
    card = cards[0]
    assert card.mac == MAC and card.active == "a2dp-sink"
    assert [(p.name, p.priority, p.available) for p in card.profiles] == [
        ("headset-head-unit", 30, True),
        ("a2dp-sink", 40, True),
        ("off", 0, True),
    ]  # "Ports" bölümündeki satırlar profil sayılmaz
    assert card.profiles[0].description == "Headset Head Unit (HSP/HFP)"


def test_parse_cards_pipewire_names_and_unavailable_profiles():
    (card,) = btaudio.parse_cards(CARDS_PW)
    assert card.mac == "11:22:33:44:55:66" and card.active == "headset-head-unit-cvsd"
    unavailable = [p.name for p in card.profiles if not p.available]
    assert unavailable == ["headset-head-unit-msbc"]


@pytest.mark.parametrize("out", ["", "bozuk çıktı\n", "Card #1\n\tDriver: x\n"])
def test_parse_cards_tolerates_garbage(out):
    assert btaudio.parse_cards(out) == []


def test_profile_without_available_field_counts_as_available():
    out = (
        "Card #1\n\tName: bluez_card.AA_BB_CC_DD_EE_FF\n\tProfiles:\n"
        "\t\ta2dp_sink: A2DP (sinks: 1, sources: 0, priority: 10)\n\tActive Profile: a2dp_sink\n"
    )
    (card,) = btaudio.parse_cards(out)
    assert card.profiles[0].available


@pytest.mark.parametrize(
    ("profile", "mode"),
    [
        ("a2dp-sink", MUSIC),
        ("a2dp-sink-aac", MUSIC),
        ("headset-head-unit", CALLS),
        ("headset-head-unit-msbc", CALLS),
        ("off", None),
        ("a2dp-source", None),
        ("", None),
    ],
)
def test_profile_mode(profile, mode):
    assert btaudio.profile_mode(profile) == mode


def test_available_modes_and_profile_choice():
    (card,) = btaudio.parse_cards(CARDS_PW)
    assert btaudio.available_modes(card) == [MUSIC, CALLS]  # msbc yok ama cvsd var
    assert btaudio.pick_profile(card, MUSIC) == "a2dp-sink-sbc"  # öncelik 18 > 16
    assert btaudio.pick_profile(card, CALLS) == "headset-head-unit-cvsd"  # msbc kullanılamıyor
    only_music = btaudio.AudioCard("bluez_card.X", MAC, [btaudio.AudioProfile("a2dp-sink", "", 5)])
    assert btaudio.available_modes(only_music) == [MUSIC]
    assert btaudio.pick_profile(only_music, CALLS) is None


def test_sinks_are_parsed_and_matched_by_address():
    sinks = btaudio.parse_sinks(SINKS)
    assert sinks[1] == "bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink"
    assert btaudio.sink_for(MAC, sinks) == sinks[1]
    assert btaudio.sink_for("11:22:33:44:55:66", sinks) is None
    # PipeWire adlandırması ve küçük harf
    assert btaudio.sink_for(MAC, ["bluez_output.aa_bb_cc_dd_ee_ff.1"]) == (
        "bluez_output.aa_bb_cc_dd_ee_ff.1"
    )
    # bluez olmayan çıkış adresi içerse bile seçilmez
    assert btaudio.sink_for(MAC, ["alsa_output.AA_BB_CC_DD_EE_FF"]) is None
    assert btaudio.parse_sinks("") == []


@pytest.fixture
def pactl(monkeypatch):
    """pactl çağrılarını taklit eder; çalıştırılan komutlar `calls` listesinde."""
    state = {
        "cards": CARDS_PA,
        "sinks": SINKS,
        "default": "alsa_output.pci-0000_00_1f.3.analog-stereo",
    }
    calls: list[list[str]] = []

    def run(cmd, timeout=10):
        calls.append(cmd)
        if cmd[1:3] == ["list", "cards"]:
            return state["cards"], ""
        if cmd[1:4] == ["list", "short", "sinks"]:
            return state["sinks"], ""
        if cmd[1] == "get-default-sink":
            return state["default"] + "\n", ""
        return "", ""

    def run_rc(cmd, timeout=30):
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(btaudio.shutil, "which", lambda name: "/usr/bin/pactl")
    monkeypatch.setattr(network, "_run", run)
    monkeypatch.setattr(network, "_run_rc", run_rc)
    state["calls"] = calls
    return state


def test_audio_info_reports_mode_and_output(pactl):
    info = btaudio.audio_info(MAC)
    assert info.card.name == "bluez_card.AA_BB_CC_DD_EE_FF"
    assert (info.modes, info.mode, info.is_output) == ([MUSIC, CALLS], MUSIC, False)
    pactl["default"] = "bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink"
    assert btaudio.audio_info(MAC).is_output is True


def test_audio_info_is_none_without_card_or_pactl(pactl, monkeypatch):
    assert btaudio.audio_info("11:22:33:44:55:66") is None  # bu cihazın ses kartı yok (bağlı değil)
    assert btaudio.audio_info("--help") is None
    monkeypatch.setattr(btaudio.shutil, "which", lambda name: None)
    assert btaudio.audio_info(MAC) is None  # pactl kurulu değil


def test_set_mode_switches_to_the_best_profile(pactl):
    assert btaudio.set_mode(MAC, CALLS) == (True, "")
    assert pactl["calls"][-1] == [
        "pactl", "set-card-profile", "bluez_card.AA_BB_CC_DD_EE_FF", "headset-head-unit",
    ]  # fmt: skip
    assert btaudio.set_mode(MAC, MUSIC)[0] is True
    assert pactl["calls"][-1][-1] == "a2dp-sink"
    assert btaudio.set_mode(MAC, "bilinmeyen") == (False, "no such profile")


def test_set_mode_refuses_unsafe_profile_names(pactl):
    # Profil adı kabuğa gitmez ama yine de yalnızca güvenli karakterler komuta girer
    pactl["cards"] = CARDS_PA.replace("a2dp-sink:", "a2dp-sink;evil:")
    before = len(pactl["calls"])
    assert btaudio.set_mode(MAC, MUSIC) == (False, "no such profile")
    assert all(c[:2] != ["pactl", "set-card-profile"] for c in pactl["calls"][before:])


def test_set_output_makes_the_device_default(pactl):
    assert btaudio.set_output(MAC) == (True, "")
    assert pactl["calls"][-1] == [
        "pactl", "set-default-sink", "bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink",
    ]  # fmt: skip


def test_set_output_waits_for_the_new_sink_after_a_profile_change(pactl):
    pactl["sinks"] = "1\talsa_output.x\tm\tspec\tIDLE\n"  # profil değişti, çıkış henüz yok
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 2:  # iki denemeden sonra çıkış belirir
            pactl["sinks"] = SINKS

    assert btaudio.set_output(MAC, wait=5, sleep=sleep) == (True, "")
    assert len(waits) == 2


def test_set_output_gives_up_when_no_sink_appears(pactl):
    pactl["sinks"] = "1\talsa_output.x\tm\tspec\tIDLE\n"
    assert btaudio.set_output(MAC, wait=0, sleep=lambda s: None) == (False, "no sink")


def test_apply_runs_only_the_requested_steps(pactl):
    assert btaudio.apply(MAC, None, False) == []
    assert pactl["calls"] == []
    assert btaudio.apply(MAC, CALLS, True) == []
    commands = [c[1] for c in pactl["calls"] if c[1] in ("set-card-profile", "set-default-sink")]
    assert commands == ["set-card-profile", "set-default-sink"]  # önce mod, sonra çıkış
    assert btaudio.apply("11:22:33:44:55:66", MUSIC, False) == ["no audio card"]
