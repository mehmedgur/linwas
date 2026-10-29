# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Program kaldırma güvenlik denetimi testleri."""

import json

import pytest

from linwas.core import package_guard
from linwas.core.package_guard import (
    CATEGORIES,
    find_blocked,
    load_critical,
    parse_simulation,
    plan_apt_removal,
    snap_blocked,
)

SIM_OUTPUT = """\
NOTE: This is only a simulation!
Reading package lists...
The following packages will be REMOVED:
  gnome-shell gdm3
Remv gnome-shell-extension-prefs [43.9-0+deb12u2]
Remv gdm3 [43.0-3]
Remv gnome-shell [43.9-0+deb12u2]
Purg libfoo1:i386 [1.0-1]
Inst something [1.0]
"""


class TestParseSimulation:
    def test_remove_and_purge_lines(self):
        assert parse_simulation(SIM_OUTPUT) == [
            "gnome-shell-extension-prefs",
            "gdm3",
            "gnome-shell",
            "libfoo1",
        ]

    def test_empty(self):
        assert parse_simulation("") == []

    def test_no_duplicates(self):
        assert parse_simulation("Remv a1 [1]\nRemv a1 [1]\n") == ["a1"]


class TestCriticalList:
    def test_real_file_loads(self):
        data = load_critical()
        assert "apt" in data and "snap" in data
        assert "_note" not in data

    def test_categories_known(self):
        for group in load_critical().values():
            assert set(group) <= set(CATEGORIES)

    def test_linwas_protected(self):
        assert "linwas" in load_critical()["apt"]["linwas"]

    def test_unreadable_file_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            load_critical(tmp_path / "yok.json")

    def test_custom_file(self, tmp_path):
        f = tmp_path / "c.json"
        f.write_text(json.dumps({"_note": "x", "apt": {"sound": ["pipewire"]}}))
        assert load_critical(f) == {"apt": {"sound": ["pipewire"]}}


class TestFindBlocked:
    CRITICAL = {"desktop": ["gnome-shell"], "network": ["network-manager"]}

    def test_none_blocked(self):
        assert find_blocked(["gnome-calculator"], self.CRITICAL) == []

    def test_blocked_with_category(self):
        result = find_blocked(["vlc", "network-manager"], self.CRITICAL)
        assert [(b.name, b.category) for b in result] == [("network-manager", "network")]

    def test_system_priority_blocked(self):
        result = find_blocked(["bash"], self.CRITICAL, system_packages={"bash"})
        assert [(b.name, b.category) for b in result] == [("bash", "system")]


class TestPlanAptRemoval:
    def _fake(self, monkeypatch, without_auto, with_auto, system=frozenset()):
        def fake_simulate(name, autoremove):
            return (with_auto if autoremove else without_auto), ""

        monkeypatch.setattr(package_guard, "_simulate", fake_simulate)
        monkeypatch.setattr(package_guard, "_system_priority_packages", lambda n: set(system))

    def test_splits_autoremoved(self, monkeypatch):
        self._fake(monkeypatch, ["vlc", "vlc-plugin-x"], ["vlc", "vlc-plugin-x", "libvlc5"])
        plan = plan_apt_removal("vlc")
        assert plan.removed == ["vlc", "vlc-plugin-x"]
        assert plan.autoremoved == ["libvlc5"]
        assert plan.blocked == []
        assert plan.error == ""

    def test_blocks_critical_dependency(self, monkeypatch):
        self._fake(monkeypatch, ["foo", "gnome-shell"], ["foo", "gnome-shell"])
        plan = plan_apt_removal("foo")
        assert [b.name for b in plan.blocked] == ["gnome-shell"]

    def test_blocks_critical_in_autoremove(self, monkeypatch):
        self._fake(monkeypatch, ["foo"], ["foo", "pipewire"])
        assert [b.category for b in plan_apt_removal("foo").blocked] == ["sound"]

    def test_not_installed(self, monkeypatch):
        self._fake(monkeypatch, [], [])
        assert plan_apt_removal("foo").error

    def test_simulation_error(self, monkeypatch):
        monkeypatch.setattr(package_guard, "_simulate", lambda n, autoremove: ([], "E: hata"))
        assert plan_apt_removal("foo").error == "E: hata"


class TestSnapBlocked:
    def test_snapd_blocked(self):
        assert snap_blocked("snapd")

    def test_base_note_blocked(self):
        assert snap_blocked("core99", "base")

    def test_app_allowed(self):
        assert snap_blocked("firefox", "-") == []
        assert snap_blocked("code", "classic") == []
