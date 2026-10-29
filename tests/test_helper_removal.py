# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Root helper kaldırma işlemleri testleri (komutlar çalıştırılmaz)."""

import pytest

from linwas.core import helper, package_guard
from linwas.core.package_guard import AptRemovalPlan, BlockedPackage


@pytest.fixture
def calls(monkeypatch):
    """_run çağrılarını kaydeder, gerçek komut çalıştırmaz; kayıt yazmaz."""
    recorded: list[list[str]] = []

    def fake_run(cmd, seq, env=None):
        recorded.append(cmd)
        return True

    saved = []
    monkeypatch.setattr(helper, "_run", fake_run)
    monkeypatch.setattr(helper, "_save_rollback", lambda rec, seq: saved.append(rec))
    return recorded, saved


def test_apt_removal_blocked_runs_nothing(monkeypatch, calls, capsys):
    plan = AptRemovalPlan(
        target="foo",
        removed=["foo", "gnome-shell"],
        blocked=[BlockedPackage("gnome-shell", "desktop")],
    )
    monkeypatch.setattr(package_guard, "plan_apt_removal", lambda name: plan)
    assert helper._exec_app_remove_apt(0, {"name": "foo"}) is False
    assert calls[0] == []
    assert "gnome-shell" in capsys.readouterr().out


def test_apt_removal_plan_error(monkeypatch, calls):
    monkeypatch.setattr(
        package_guard, "plan_apt_removal", lambda n: AptRemovalPlan(target=n, error="x")
    )
    assert helper._exec_app_remove_apt(0, {"name": "foo"}) is False
    assert calls[0] == []


def test_apt_purge_command_and_record(monkeypatch, calls):
    plan = AptRemovalPlan(target="vlc", removed=["vlc", "vlc-bin"], autoremoved=["libvlc5"])
    monkeypatch.setattr(package_guard, "plan_apt_removal", lambda name: plan)
    assert helper._exec_app_remove_apt_purge(0, {"name": "vlc"}) is True
    assert calls[0] == [["apt-get", "purge", "-y", "--autoremove", "--", "vlc"]]
    assert calls[1][0].packages_to_remove == ["vlc", "vlc-bin"]


def test_flatpak_removal_commands(calls):
    assert helper._exec_app_remove_flatpak(0, {"app_id": "org.videolan.VLC"}) is True
    assert calls[0][0] == [
        "flatpak",
        "uninstall",
        "-y",
        "--noninteractive",
        "--system",
        "org.videolan.VLC",
    ]
    assert "--unused" in calls[0][1]
    assert calls[1][0].flatpaks_removed == ["org.videolan.VLC"]


def test_flatpak_delete_data(monkeypatch, calls, tmp_path):
    data = tmp_path / ".var" / "app" / "org.videolan.VLC"
    data.mkdir(parents=True)
    (data / "config").write_text("x")
    other = tmp_path / ".var" / "app" / "org.gimp.GIMP"
    other.mkdir()
    monkeypatch.setattr(helper, "_invoking_user_home", lambda: tmp_path)
    assert helper._exec_app_remove_flatpak_data(0, {"app_id": "org.videolan.VLC"}) is True
    assert not data.exists()
    assert other.exists()


def test_flatpak_delete_data_skips_symlink(monkeypatch, calls, tmp_path):
    victim = tmp_path / "important"
    victim.mkdir()
    (victim / "keep").write_text("x")
    home = tmp_path / "home"
    (home / ".var" / "app").mkdir(parents=True)
    (home / ".var" / "app" / "org.videolan.VLC").symlink_to(victim)
    monkeypatch.setattr(helper, "_invoking_user_home", lambda: home)
    helper._exec_app_remove_flatpak_data(0, {"app_id": "org.videolan.VLC"})
    assert (victim / "keep").exists()


def test_snap_blocked(monkeypatch, calls):
    monkeypatch.setattr(helper, "_snap_notes", lambda name: "snapd")
    assert helper._exec_app_remove_snap(0, {"name": "snapd"}) is False
    assert calls[0] == []


def test_snap_not_installed(monkeypatch, calls):
    monkeypatch.setattr(helper, "_snap_notes", lambda name: None)
    assert helper._exec_app_remove_snap(0, {"name": "firefox"}) is False


def test_snap_purge_classic_record(monkeypatch, calls):
    monkeypatch.setattr(helper, "_snap_notes", lambda name: "classic")
    assert helper._exec_app_remove_snap_purge(0, {"name": "code"}) is True
    assert calls[0] == [["snap", "remove", "--purge", "code"]]
    rec = calls[1][0]
    assert rec.snaps_removed == ["code"] and rec.snaps_classic == ["code"]


def test_every_operation_has_executor():
    from linwas.core.whitelist import OPERATIONS

    assert set(OPERATIONS) <= set(helper._EXECUTORS)


def test_lid_action_writes_and_removes(monkeypatch, tmp_path):
    target = tmp_path / "logind.conf.d" / "90-linwas-lid.conf"
    monkeypatch.setattr(helper, "_LID_DROPIN", target)
    assert helper._exec_power_set_lid_action(0, {"action": "lock"}) is True
    assert "HandleLidSwitch=lock" in target.read_text()
    assert helper._exec_power_set_lid_action(0, {"action": "suspend"}) is True
    assert not target.exists()
