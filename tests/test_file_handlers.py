# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
""".deb dosyaları için varsayılan uygulama (backend/file_handlers.py)."""

from pathlib import Path

from linwas.backend import file_handlers
from linwas.core import app_settings


def test_remove_user_default_only_removes_linwas(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "mimeapps.list").write_text(
        "[Default Applications]\n"
        "application/vnd.debian.binary-package=linwas.desktop\n"
        "application/x-deb=linwas.desktop;\n"
        "text/plain=org.gnome.TextEditor.desktop\n"
        "[Added Associations]\n"
        "application/vnd.debian.binary-package=linwas.desktop;\n"
    )
    assert file_handlers.restore_deb_handler("")
    text = (tmp_path / "mimeapps.list").read_text()
    assert "text/plain=org.gnome.TextEditor.desktop" in text
    assert "[Default Applications]\ntext/plain" in text
    # Diğer bölümlere dokunulmaz
    assert "[Added Associations]\napplication/vnd.debian.binary-package=linwas.desktop;" in text


def test_restore_rejects_bad_desktop_id(monkeypatch):
    calls = []
    monkeypatch.setattr(file_handlers, "_xdg_mime", lambda *a: calls.append(a) or (0, ""))
    monkeypatch.setattr(file_handlers, "_remove_user_default", lambda mimes: True)
    assert file_handlers.restore_deb_handler("bad; rm -rf") is True
    assert calls == []
    assert file_handlers.restore_deb_handler("org.gnome.FileRoller.desktop")
    assert calls[0][:2] == ("default", "org.gnome.FileRoller.desktop")


def test_make_handler_needs_installed_package(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(file_handlers, "INSTALLED_DESKTOP_FILE", tmp_path / "missing.desktop")
    assert file_handlers.make_linwas_deb_handler() == (False, "")


def test_previous_handler_setting_is_validated():
    s = app_settings.from_dict({"deb_handler_previous": "org.gnome.FileRoller.desktop"})
    assert s.deb_handler_previous == "org.gnome.FileRoller.desktop"
    assert app_settings.from_dict({"deb_handler_previous": "../x"}).deb_handler_previous == ""
