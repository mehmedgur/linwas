# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Görev çubuğu: öğe listesi, Windows 10/11 hizalaması, saat yeri, sabitlenmiş programlar."""

import json

from linwas.backend import taskbar


def _fake_dtp(monkeypatch, initial: dict | None = None) -> dict:
    store = {"panel-element-positions": "'" + json.dumps(initial or {}) + "'"}
    monkeypatch.setattr(taskbar, "_monitors", lambda: ["0", "1"])
    monkeypatch.setattr(taskbar, "dtp_get", lambda key: store.get(key))

    def dtp_set(key: str, value: str) -> bool:
        store[key] = value
        return True

    monkeypatch.setattr(taskbar, "dtp_set", dtp_set)
    return store


def _saved(store: dict) -> dict:
    return json.loads(store["panel-element-positions"].strip("'"))


def test_defaults_when_unset(monkeypatch):
    _fake_dtp(monkeypatch)
    names = [e["element"] for e in taskbar.read_elements()]
    assert names == list(taskbar.ELEMENTS)
    assert taskbar.alignment() == "left"


def test_alignment_moves_start_and_icons_on_every_monitor(monkeypatch):
    store = _fake_dtp(monkeypatch)
    assert taskbar.set_alignment("center")
    saved = _saved(store)
    assert set(saved) == {"0", "1"}
    by_name = {e["element"]: e["position"] for e in saved["0"]}
    assert by_name["taskbar"] == by_name["showAppsButton"] == "centerMonitor"
    assert by_name["dateMenu"] == "stackedBR"
    assert taskbar.alignment() == "center"
    assert not taskbar.set_alignment("diagonal")


def test_visibility_only_for_toggleable(monkeypatch):
    store = _fake_dtp(monkeypatch)
    assert taskbar.set_element_visible("desktopButton", False)
    assert {e["element"]: e["visible"] for e in _saved(store)["0"]}["desktopButton"] is False
    assert not taskbar.set_element_visible("taskbar", False)


def test_unknown_elements_dropped_and_missing_added(monkeypatch):
    _fake_dtp(
        monkeypatch,
        {
            "0": [
                {"element": "bogus"},
                {"element": "taskbar", "visible": True, "position": "centerMonitor"},
            ]
        },
    )
    elements = taskbar.read_elements()
    assert elements[0]["element"] == "taskbar"
    assert {e["element"] for e in elements} == set(taskbar.ELEMENTS)


def test_clock_center(monkeypatch):
    _fake_dtp(monkeypatch)
    taskbar.set_clock_centered(True)
    assert taskbar.clock_centered()


def test_save_pinned_filters(monkeypatch):
    calls = []
    monkeypatch.setattr(taskbar.workgroups, "_gs", lambda *a: calls.append(a) or (0, ""))
    taskbar.save_pinned(["a.desktop", "a.desktop", "/etc/x.desktop", "b", "c.desktop"])
    assert calls[0][-1] == "['a.desktop', 'c.desktop']"


def test_dock_visibility_modes(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(taskbar, "dock_set", lambda k, v: store.__setitem__(k, v) or True)
    assert taskbar.set_dock_visibility("always")
    assert store == {"dock-fixed": "true", "autohide": "false", "intellihide": "false"}
    taskbar.set_dock_visibility("intellihide")
    assert store == {"dock-fixed": "false", "autohide": "true", "intellihide": "true"}
    assert not taskbar.set_dock_visibility("sometimes")


def test_dock_set_only_known_keys(monkeypatch):
    monkeypatch.setattr(taskbar, "_gsettings", lambda *a: (0, ""))
    assert taskbar.dock_set("show-trash", "true")
    assert not taskbar.dock_set("some-other-key", "true")
