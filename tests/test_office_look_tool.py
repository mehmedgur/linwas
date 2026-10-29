# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""linwas-office-look aracı (packaging/plugins/office-look/tools): profil yazma, kapat/aç."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "packaging" / "plugins" / "office-look" / "tools"
sys.path.insert(0, str(TOOLS))

import cli  # noqa: E402
import lo_profile  # noqa: E402

PROFILE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<oor:items xmlns:oor="http://openoffice.org/2001/registry" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
    '<item oor:path="/org.openoffice.Office.Common/Misc">'
    '<prop oor:name="X" oor:op="fuse"><value>1</value></prop></item>\n'
    '<item oor:path="/org.openoffice.Office.Writer/DefaultFont">'
    '<prop oor:name="Standard" oor:op="fuse"><value>Arial</value></prop></item>\n'
    "</oor:items>\n"
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    profile = tmp_path / "registrymodifications.xcu"
    profile.write_text(PROFILE, encoding="utf-8")
    monkeypatch.setattr(lo_profile, "DEFAULT_PATH", str(profile))
    monkeypatch.setattr(lo_profile.Profile.__init__, "__defaults__", (str(profile),))
    config = tmp_path / "config"
    monkeypatch.setattr(cli, "CONFIG_DIR", str(config))
    monkeypatch.setattr(cli, "SETTINGS_FILE", str(config / "settings.json"))
    monkeypatch.setattr(cli, "DISABLED_FLAG", str(config / "disabled"))
    monkeypatch.setattr(cli, "BACKUP_FILE", str(config / "backup.json"))
    monkeypatch.setattr(cli, "libreoffice_running", lambda: False)
    monkeypatch.setattr(cli, "simple_ribbon_apps", lambda: ["Writer", "Calc", "Impress"])
    return tmp_path


def _items(path: Path) -> set[bytes]:
    items = ET.parse(path).getroot().findall("item")
    for item in items:
        item.tail = None  # satır sonları karşılaştırmaya girmesin
    return {ET.tostring(i) for i in items}


def test_profile_keeps_namespace_declarations(home):
    prof = lo_profile.Profile()
    prof.set("/a", "b", "c")
    prof.save()
    head = (home / "registrymodifications.xcu").read_text(encoding="utf-8")[:300]
    assert 'xmlns:xs="http://www.w3.org/2001/XMLSchema"' in head
    assert lo_profile.Profile().get("/a", "b") == "c"


def test_set_ribbon_and_back_to_default(home):
    cli.set_option("ribbon", "full")
    prof = lo_profile.Profile()
    assert prof.get(lo_profile.app_path("Writer"), "Active") == "notebookbar.ui"
    assert prof.get(cli.TOOLBAR_MODE, "ActiveCalc") == "notebookbar.ui"
    assert cli.status()["settings"]["ribbon"] == "full"
    cli.set_option("ribbon", "default")
    assert lo_profile.Profile().get(lo_profile.app_path("Writer"), "Active") is None


def test_user_settings_file(home):
    cli.set_option("file_menu", "off")
    cli.set_option("autosave", "5")
    data = json.loads((home / "config" / "settings.json").read_text())
    assert data == {"file_menu": False, "autosave_minutes": 5, "office_names": True}
    with pytest.raises(cli.ToolError):
        cli.set_option("autosave", "7")


def test_refuses_while_libreoffice_runs(home, monkeypatch):
    monkeypatch.setattr(cli, "libreoffice_running", lambda: True)
    with pytest.raises(cli.ToolError) as e:
        cli.set_option("font", "liberation")
    assert e.value.code == cli.EXIT_LO_RUNNING


def test_disable_then_enable_restores_profile(home):
    before = _items(home / "registrymodifications.xcu")
    cli.disable()
    assert (home / "config" / "disabled").exists()
    prof = lo_profile.Profile()
    assert prof.get(lo_profile.app_path("Writer"), "Active") == "Default"
    assert prof.get(cli.FONT_PATH, "Standard") == "Liberation Serif"
    cli.enable()
    assert not (home / "config" / "disabled").exists()
    assert _items(home / "registrymodifications.xcu") == before
