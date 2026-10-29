# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Bluetooth dosya gönderme: araç seçimi ve komut üretimi (Qt'siz)."""

import subprocess

import pytest

from linwas.backend import btfile

MAC = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
def files(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b b.jpg"
    a.write_text("a")
    b.write_text("b")
    return [str(a), str(b)]


def test_tool_is_the_first_installed_one(monkeypatch):
    installed = {"blueman-sendto"}
    monkeypatch.setattr(
        btfile.shutil, "which", lambda name: f"/usr/bin/{name}" if name in installed else None
    )
    assert btfile.available_tool() == "blueman-sendto"
    installed.add("bluetooth-sendto")
    assert btfile.available_tool() == "bluetooth-sendto"  # GNOME aracı önce
    installed.clear()
    assert btfile.available_tool() is None


def test_commands_match_each_tools_documented_options():
    assert btfile.send_command("bluetooth-sendto", MAC, ["/a", "/b"]) == [
        "bluetooth-sendto", f"--device={MAC}", "--", "/a", "/b",
    ]  # fmt: skip
    assert btfile.send_command("blueman-sendto", MAC, ["/a"]) == [
        "blueman-sendto", "--device", MAC, "--", "/a",
    ]  # fmt: skip


def test_only_existing_absolute_files_are_kept(tmp_path, files):
    folder = tmp_path / "klasor"
    folder.mkdir()
    chosen = [files[0], files[0], str(folder), str(tmp_path / "yok"), "goreli.txt", files[1]]
    assert btfile.valid_files(chosen) == files  # yinelenen, klasör, olmayan ve göreli atılır


def test_only_phones_and_computers_get_the_send_button():
    assert btfile.can_receive("phone") and btfile.can_receive("computer")
    for icon in ("audio-headset", "input-mouse", "input-keyboard", ""):
        assert not btfile.can_receive(icon)


class FakeProc:
    def __init__(self):
        self.waited = False

    def wait(self):
        self.waited = True


def test_send_starts_the_tool_detached_and_without_a_shell(monkeypatch, files):
    monkeypatch.setattr(btfile.shutil, "which", lambda name: "/usr/bin/" + name)
    started = {}

    def popen(cmd, **kwargs):
        started["cmd"], started["kwargs"] = cmd, kwargs
        started["proc"] = FakeProc()
        return started["proc"]

    assert btfile.send(MAC, files, popen=popen) == (True, "")
    assert started["cmd"] == ["bluetooth-sendto", f"--device={MAC}", "--", *files]
    kwargs = started["kwargs"]
    assert kwargs["shell"] is False and kwargs["start_new_session"] is True
    assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == subprocess.DEVNULL


def test_send_refuses_bad_input_without_starting_anything(monkeypatch, files):
    monkeypatch.setattr(btfile.shutil, "which", lambda name: "/usr/bin/" + name)

    def popen(*a, **k):
        pytest.fail("başlatılmamalı")

    assert btfile.send("--help", files, popen=popen) == (False, "invalid address")
    assert btfile.send("aa:bb:cc:dd:ee:ff", files, popen=popen) == (False, "invalid address")
    assert btfile.send(MAC, [], popen=popen) == (False, "no files")
    assert btfile.send(MAC, ["goreli.txt"], popen=popen) == (False, "no files")
    monkeypatch.setattr(btfile.shutil, "which", lambda name: None)
    assert btfile.send(MAC, files, popen=popen) == (False, "no tool")


def test_send_reports_a_tool_that_cannot_start(monkeypatch, files):
    monkeypatch.setattr(btfile.shutil, "which", lambda name: "/usr/bin/" + name)

    def popen(*a, **k):
        raise PermissionError("izin yok")

    assert btfile.send(MAC, files, popen=popen) == (False, "izin yok")
