"""Küçük yardımcı modüllerin testleri: ayar açıcı, rehber, hata raporu, uygulama ayarları,
Wi-Fi aktarımı, görünüm ayarları."""

import json
import subprocess
import urllib.parse
from pathlib import Path

import pytest

from linwas.backend import appearance, settings_launcher, wifi_import, windows_guide
from linwas.core import app_settings, error_report

# --- settings_launcher ---


def test_settings_map_loads_and_skips_comments(tmp_path: Path):
    f = tmp_path / "map.json"
    f.write_text(json.dumps({"_comment": "x", "wifi": {"gnome": ["true"]}, "bad": 1}))
    assert settings_launcher.load_map(f) == {"wifi": {"gnome": ["true"]}}
    assert settings_launcher.load_map(tmp_path / "yok.json") == {}


def test_real_settings_map_is_valid():
    mapping = settings_launcher.load_map()
    assert mapping
    for desktops in mapping.values():
        for cmd in desktops.values():
            assert isinstance(cmd, list) and cmd and all(isinstance(a, str) for a in cmd)


def test_command_for_falls_back_to_all(monkeypatch):
    monkeypatch.setattr(settings_launcher.shutil, "which", lambda c: c != "missing")
    mapping = {"wifi": {"gnome": ["missing", "wifi"]}, "all": {"gnome": ["gnome-control-center"]}}
    assert settings_launcher.command_for("wifi", "gnome", mapping) == ["gnome-control-center"]
    assert settings_launcher.command_for("wifi", "kde", mapping) is None


# --- windows_guide ---


def test_guide_data_loads():
    entries = windows_guide.load()
    assert len(entries) >= 50
    assert all(e.kind in windows_guide.KINDS for e in entries)
    assert all(e.text["tr"] and e.text["en"] for e in entries)


def test_guide_search_turkish_fold_and_order():
    e1 = windows_guide.GuideEntry("program", ["Görev Yöneticisi"], {"tr": "x", "en": "x"})
    e2 = windows_guide.GuideEntry("concept", ["Başka"], {"tr": "görev yöneticisi gibi", "en": ""})
    assert windows_guide.search("GÖREV", [e2, e1]) == [e1, e2]
    assert windows_guide.search("İ", [e1]) == [e1]  # İ → i
    assert windows_guide.search("", [e1, e2], kind="concept") == [e2]


# --- error_report ---


def test_report_is_sanitized_and_url_truncated():
    report = error_report.build_report(
        "failed at /home/ali/x", ["Install vlc"], "2.0", "Pardus 23", "gnome"
    )
    assert "## Error" in report and "- Install vlc" in report
    url = error_report.issue_url("Hata", "a" * 10000)
    body = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["body"][0]
    assert len(body) < 6100 and body.endswith("attach the saved report)")


def test_empty_error_message():
    assert "(no message)" in error_report.build_report("  ", [], "2.0", "s", "d")


# --- app_settings ---


def test_app_settings_roundtrip_and_validation(tmp_path: Path):
    f = tmp_path / "linwas" / "settings.json"
    assert app_settings.load(f) == app_settings.AppSettings()
    s = app_settings.AppSettings(theme="dark", language="en", onboarding_done=True)
    app_settings.save(s, f)
    assert app_settings.load(f) == s
    f.write_text(json.dumps({"theme": "pink", "language": "de", "onboarding_done": "yes"}))
    assert app_settings.load(f) == app_settings.AppSettings()


def test_app_settings_default_path_uses_xdg(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert app_settings.default_path() == tmp_path / "linwas" / "settings.json"


# --- wifi_import ---

_PROFILE = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>Ev</name>
  <SSIDConfig><SSID><name>Ev Ağı</name></SSID></SSIDConfig>
  <MSM><security>
    <authEncryption><authentication>{auth}</authentication></authEncryption>
    <sharedKey><protected>{protected}</protected><keyMaterial>gizli123</keyMaterial></sharedKey>
  </security></MSM>
</WLANProfile>"""


@pytest.mark.parametrize(
    ("auth", "protected", "key", "supported"),
    [
        ("WPA2PSK", "false", "gizli123", True),
        ("WPA2PSK", "true", "", False),
        ("WPA2", "false", "gizli123", False),  # kurumsal (802.1X) desteklenmiyor
    ],
)
def test_parse_wifi_profile(tmp_path: Path, auth, protected, key, supported):
    f = tmp_path / "p.xml"
    f.write_text(_PROFILE.format(auth=auth, protected=protected), encoding="utf-8")
    p = wifi_import.parse_profile(f)
    assert p is not None and p.ssid == "Ev Ağı" and p.key == key
    assert p.supported is supported


def test_parse_wifi_profile_rejects_other_xml(tmp_path: Path):
    f = tmp_path / "x.xml"
    f.write_text("<root/>")
    assert wifi_import.parse_profile(f) is None
    f.write_text("bozuk")
    assert wifi_import.parse_profile(f) is None


def test_import_profile_command(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(wifi_import.subprocess, "run", fake_run)
    p = wifi_import.WifiProfile("f", "Ev; rm -rf", "WPA2PSK", "k")
    assert wifi_import.import_profile(p) == (True, "ok")
    cmd, kw = calls[0]
    assert kw["shell"] is False
    assert cmd[cmd.index("ssid") + 1] == "Ev; rm -rf"  # tek argüman, kabuk yok
    assert cmd[-4:] == ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", "k"]
    unsupported = wifi_import.WifiProfile("f", "x", "WPA2", "")
    assert wifi_import.import_profile(unsupported) == (False, "unsupported")


# --- appearance ---


@pytest.fixture
def gsettings(monkeypatch):
    """gsettings/gnome-extensions yerine sahte depo."""
    store: dict[tuple[str, str], str] = {}
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=10):
        calls.append(cmd)
        if cmd[:2] == ["gsettings", "get"]:
            v = store.get((cmd[2], cmd[3]))
            return (0, v) if v is not None else (1, "")
        if cmd[:2] == ["gsettings", "set"]:
            store[(cmd[2], cmd[3])] = f"'{cmd[4]}'"
            return 0, ""
        return 1, ""

    monkeypatch.setattr(appearance, "_run", fake_run)
    return store, calls


def test_appearance_get_strips_quotes_and_unknown_key(gsettings):
    store, _ = gsettings
    store[("org.gnome.desktop.interface", "gtk-theme")] = "'Adwaita'"
    assert appearance.get("gnome", "gtk_theme") == "Adwaita"
    assert appearance.get("gnome", "nope") is None
    assert appearance.get("xfce", "gtk_theme") is None
    assert appearance.set_value("gnome", "gtk_theme", "a\nb") is False


def test_appearance_dark_mode(gsettings):
    store, _ = gsettings
    assert appearance.set_dark("gnome", True)
    assert appearance.is_dark("gnome")
    store[("org.cinnamon.desktop.interface", "gtk-theme")] = "'Mint-Y-Dark'"
    assert appearance.set_dark("cinnamon", False)
    assert store[("org.cinnamon.desktop.interface", "gtk-theme")] == "'Mint-Y'"
    assert appearance.set_dark("kde", True) is False


def test_appearance_wallpaper(gsettings, tmp_path: Path):
    store, _ = gsettings
    img = tmp_path / "w.png"
    assert appearance.set_wallpaper("gnome", img) is False
    img.write_bytes(b"x")
    assert appearance.set_wallpaper("gnome", img)
    assert store[("org.gnome.desktop.background", "picture-uri-dark")] == f"'{img.as_uri()}'"


def test_extension_state(monkeypatch):
    responses = {"info": (0, ""), "list": (0, "a@b dash-to-panel@jderose9.github.com")}
    monkeypatch.setattr(appearance, "_run", lambda cmd, timeout=10: responses[cmd[1]])
    assert appearance.extension_state() == "enabled"
    responses["list"] = (0, "")
    assert appearance.extension_state() == "disabled"
    responses["info"] = (1, "")
    assert appearance.extension_state() == "missing"
