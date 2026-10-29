# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sorun giderme, yedek listesi, Flatpak araması ve ağ/Bluetooth ayrıştırıcı testleri."""

from collections import namedtuple

import pytest

from linwas.backend import backups, flatpak, network, troubleshoot

# --- troubleshoot ---


@pytest.fixture
def fake_cmd(monkeypatch):
    """troubleshoot._run yerine: komutun ilk iki öğesine göre (kod, çıktı)."""
    table: dict[tuple[str, ...], tuple[int, str]] = {}
    monkeypatch.setattr(troubleshoot, "_run", lambda cmd, timeout=15: table[tuple(cmd[:2])])
    return table


def test_disk_check(monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(
        troubleshoot.shutil, "disk_usage", lambda p: usage(100 * 1024**3, 0, 1024**3)
    )
    assert troubleshoot.check_disk().ok is False  # 1 GB < 2 GB
    monkeypatch.setattr(
        troubleshoot.shutil, "disk_usage", lambda p: usage(100 * 1024**3, 0, 50 * 1024**3)
    )
    assert troubleshoot.check_disk().ok is True


def test_internet_and_sound_missing_tools_are_ok(fake_cmd):
    fake_cmd[("nmcli", "networking")] = (127, "")
    fake_cmd[("pactl", "info")] = (127, "")
    assert troubleshoot.check_internet().ok and troubleshoot.check_sound().ok
    fake_cmd[("nmcli", "networking")] = (0, "limited")
    assert troubleshoot.check_internet().ok is False


def test_services_and_packages(fake_cmd):
    fake_cmd[("systemctl", "--failed")] = (0, "a.service loaded failed\nb.service x\n")
    r = troubleshoot.check_services()
    assert not r.ok and r.detail == "a.service, b.service"
    fake_cmd[("dpkg", "--audit")] = (0, "")
    assert troubleshoot.check_packages().ok


@pytest.mark.parametrize(
    ("code", "out", "ok"), [(0, "active", True), (3, "inactive", True), (3, "failed", False)]
)
def test_printing(fake_cmd, code, out, ok):
    fake_cmd[("systemctl", "is-active")] = (code, out)
    assert troubleshoot.check_printing().ok is ok


def test_run_all_survives_exceptions(monkeypatch):
    def boom():
        raise RuntimeError("x")

    boom.__name__ = "check_boom"
    monkeypatch.setattr(troubleshoot, "CHECKS", (boom,))
    assert troubleshoot.run_all() == [troubleshoot.CheckResult("boom", True, "x")]


# --- backups ---


def test_parse_size():
    assert backups._parse_size("1.5 GB") == 1536
    assert backups._parse_size("500 MB") == 500
    assert backups._parse_size("?") == 0.0


def test_timeshift_list_parsing(monkeypatch):
    out = (
        "Device : /dev/sda2\n"
        "Num     Name                 Tags  Description\n"
        "------------------------------------------------\n"
        "0  |  2026-10-06_12-00-01  |  O  |  Before update  |  /dev/sda2  |  1 GB\n"
    )
    monkeypatch.setattr(backups, "_run", lambda cmd, timeout=15: out)
    monkeypatch.setattr(backups, "list_linwas_records", lambda: [])
    snaps = backups.list_timeshift_snapshots()
    assert [(s.name, s.tag, s.size_mb) for s in snaps] == [("2026-10-06_12-00-01", "O", 1024)]
    entries = backups.combined_backups()
    assert entries[0].id == "timeshift:2026-10-06_12-00-01" and entries[0].source == "timeshift"


# --- flatpak ---


def test_flatpak_search_parsing(monkeypatch):
    outputs = {
        "which": "/usr/bin/flatpak\n",
        "search": "Application ID\tName\tDescription\tVersion\n"
        "org.videolan.VLC\tVLC\tMedia player\t3.0\n"
        "org.gimp.GIMP\tGIMP\tImage editor\t2.10\n",
        "list": "org.gimp.GIMP\n",
    }
    monkeypatch.setattr(
        flatpak, "_run", lambda cmd, timeout=20: outputs[cmd[1] if cmd[0] == "flatpak" else "which"]
    )
    result = flatpak.search_flatpak("vlc")
    assert [(p.app_id, p.installed) for p in result] == [
        ("org.videolan.VLC", False),
        ("org.gimp.GIMP", True),
    ]
    assert flatpak.search_flatpak("vlc", max_results=1)[0].name == "VLC"
    assert flatpak.search_flatpak("  ") == []


# --- network ---


def test_split_terse_escapes():
    assert network.split_terse(r"yes:AA\:BB\:CC:Ev\\Ağı:80") == ["yes", "AA:BB:CC", "Ev\\Ağı", "80"]


def test_parse_wifi_list_dedup_and_order():
    out = "\n".join(
        [
            r"no:AA\:01:Ev:40:WPA2",
            r"no:AA\:02:Ev:70:WPA2",
            r"yes:BB\:01:İş:30:WPA2",
            r"no:CC\:01::90:",  # gizli ağ atlanır
            "bozuk",
        ]
    )
    nets = network.parse_wifi_list(out)
    assert [(n.ssid, n.signal, n.active) for n in nets] == [("İş", 30, True), ("Ev", 70, False)]
    assert nets[1].quality == "good" and nets[0].quality == "fair"


def test_bluetooth_parsers():
    devices = network.parse_devices(
        "Device AA:BB:CC:DD:EE:FF Kulaklık\nDevice bad Name\nController x\n"
    )
    assert devices == [("AA:BB:CC:DD:EE:FF", "Kulaklık")]
    info = network.parse_info(
        "AA:BB:CC:DD:EE:FF",
        "Kulaklık",
        "\tAlias: Benim Kulaklık\n\tPaired: yes\n\tConnected: no\n\tIcon: audio-headset\n"
        "\tRSSI: -60\n\tBattery Percentage: 0x50 (80)\n",
    )
    assert (info.name, info.paired, info.connected, info.icon) == (
        "Benim Kulaklık",
        True,
        False,
        "audio-headset",
    )
    assert (info.rssi, info.battery, info.quality) == (-60, 80, "excellent")
    assert network._valid_mac("aa:bb:cc:dd:ee:ff") is False
