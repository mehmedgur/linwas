"""Office görünümü arka ucu: araç çıktısını çözme, hata kodları, kurulum adımları."""

import json
import subprocess

from linwas.backend import office_look


def _completed(code: int, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, out, err)


def test_parse_status_full():
    text = json.dumps(
        {
            "package_version": "0.4.0",
            "libreoffice_version": "4:7.4.7-1",
            "libreoffice_running": False,
            "disabled": False,
            "simple_ribbon_apps": ["Writer", "Calc"],
            "settings": {
                "ribbon": "full",
                "file_menu": False,
                "autosave_minutes": 5,
                "save_format": "odf",
                "font": "liberation",
            },
        }
    )
    s = office_look.parse_status(text)
    assert s.installed and s.libreoffice_installed
    assert s.simple_ribbon_apps == ["Writer", "Calc"]
    assert s.settings == office_look.Settings("full", False, 5, "odf", "liberation")


def test_parse_status_unknown_values_fall_back_to_defaults():
    text = json.dumps(
        {"settings": {"ribbon": "default", "autosave_minutes": 7, "font": "x"}, "disabled": 1}
    )
    s = office_look.parse_status(text)
    assert not s.installed and s.disabled
    assert s.settings == office_look.Settings()


def test_status_without_tool_reports_only_libreoffice(monkeypatch):
    monkeypatch.setattr(office_look, "_run", lambda args, timeout=30: None)
    monkeypatch.setattr(office_look, "_dpkg_version", lambda p: "4:7.4.7-1")
    s = office_look.status()
    assert not s.installed and s.libreoffice_installed


def test_set_option_reports_running_libreoffice(monkeypatch):
    calls = []

    def fake_run(args, timeout=30):
        calls.append(args)
        return _completed(office_look.EXIT_LO_RUNNING)

    monkeypatch.setattr(office_look, "_run", fake_run)
    r = office_look.set_option("ribbon", "full")
    assert not r.ok and r.libreoffice_running
    assert calls == [["set", "ribbon", "full"]]


def test_apply_settings_sends_only_changes_and_stops_on_error(monkeypatch):
    calls = []

    def fake_set(key, value):
        calls.append((key, value))
        return office_look.Result(key != "ribbon", libreoffice_running=key == "ribbon")

    monkeypatch.setattr(office_look, "set_option", fake_set)
    old = office_look.Settings()
    new = office_look.Settings(ribbon="classic", file_menu=False, font="liberation")
    r = office_look.apply_settings(old, new)
    assert not r.ok and r.libreoffice_running
    # kullanıcı ayarları önce (LibreOffice açıkken de yazılabilir), profil ayarları sonra
    assert calls == [("file_menu", "off"), ("ribbon", "classic")]
    assert office_look.apply_settings(old, old).ok


def test_short_version():
    assert office_look.short_version("4:7.4.7-1+deb12u14") == "7.4.7"
    assert office_look.short_version("0.4.0") == "0.4.0"
    assert office_look.short_version("2.0.0~dev12") == "2.0.0"
    assert office_look.short_version(None) == ""


def test_install_steps_add_libreoffice_when_missing():
    missing = office_look.OfficeLookStatus()
    steps = office_look.install_steps(missing)
    names = [p["name"] for _, p in steps]
    assert names[-1] == office_look.PACKAGE
    assert set(office_look.LIBREOFFICE_PACKAGES) <= set(names)
    present = office_look.OfficeLookStatus(libreoffice_version="4:7.4")
    assert office_look.install_steps(present) == [
        ("package.install", {"name": office_look.PACKAGE})
    ]
