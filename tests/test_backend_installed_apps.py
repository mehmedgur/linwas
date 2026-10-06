"""Kurulu programlar listesi ayrıştırıcı testleri."""

from datetime import date

from linwas.backend.installed_apps import (
    parse_desktop_entry,
    parse_dpkg_log_installs,
    parse_dpkg_search,
    parse_flatpak_list,
    parse_human_size,
    parse_installer_status,
    parse_snap_list,
    parse_snap_refresh_list,
)


class TestDesktopEntry:
    def test_localized_name(self):
        text = (
            "[Desktop Entry]\nType=Application\nName=Calculator\n"
            "Name[tr]=Hesap Makinesi\nIcon=calc\n"
        )
        assert parse_desktop_entry(text, ["tr_TR", "tr"]) == {
            "name": "Hesap Makinesi",
            "icon": "calc",
        }

    def test_default_name(self):
        text = "[Desktop Entry]\nType=Application\nName=Calculator\n"
        assert parse_desktop_entry(text)["name"] == "Calculator"

    def test_nodisplay_hidden(self):
        base = "[Desktop Entry]\nType=Application\nName=X\n"
        assert parse_desktop_entry(base + "NoDisplay=true\n") is None
        assert parse_desktop_entry(base + "Hidden=true\n") is None

    def test_not_application(self):
        assert parse_desktop_entry("[Desktop Entry]\nType=Link\nName=X\n") is None

    def test_action_sections_ignored(self):
        text = (
            "[Desktop Entry]\nType=Application\nName=Firefox\n"
            "[Desktop Action new-window]\nName=New Window\n"
        )
        assert parse_desktop_entry(text)["name"] == "Firefox"


def test_dpkg_search():
    out = (
        "gnome-calculator: /usr/share/applications/org.gnome.Calculator.desktop\n"
        "foo:amd64, bar: /usr/share/applications/foo.desktop\n"
        "diversion by x from: /y\n"
    )
    assert parse_dpkg_search(out) == {
        "/usr/share/applications/org.gnome.Calculator.desktop": "gnome-calculator",
        "/usr/share/applications/foo.desktop": "foo",
    }


def test_dpkg_log_last_install_wins():
    lines = [
        "2026-01-31 10:00:00 install vlc:amd64 <none> 3.0\n",
        "2026-02-01 10:00:00 upgrade vlc:amd64 3.0 3.1\n",
        "2026-03-05 09:00:00 install vlc:amd64 <none> 3.1\n",
        "2026-03-05 09:00:00 status installed vlc:amd64 3.1\n",
        "2026-01-01 00:00:00 install gimp <none> 2.10\n",
    ]
    assert parse_dpkg_log_installs(lines) == {
        "vlc": date(2026, 3, 5),
        "gimp": date(2026, 1, 1),
    }


def test_installer_status():
    text = (
        "Package: bash\nStatus: install ok installed\n\n"
        "Package: half\nStatus: install ok unpacked\n\n"
        "Package: vim\nStatus: install ok installed\n"
    )
    assert parse_installer_status(text) == {"bash", "vim"}


class TestSizes:
    def test_units(self):
        assert parse_human_size("123.4 MB") == 123_400_000
        assert parse_human_size("1,5 GB") == 1_500_000_000
        assert parse_human_size("512 bytes") is None
        assert parse_human_size("") is None


def test_flatpak_list():
    out = "org.videolan.VLC\tVLC\t95.2 MB\tsystem\norg.gimp.GIMP\tGIMP\t1.1 GB\tuser\nbroken line\n"
    apps = parse_flatpak_list(out)
    assert [(a.id, a.name, a.user_install) for a in apps] == [
        ("org.videolan.VLC", "VLC", False),
        ("org.gimp.GIMP", "GIMP", True),
    ]
    assert apps[0].size_bytes == 95_200_000
    assert all(a.source == "flatpak" for a in apps)


def test_snap_list():
    out = (
        "Name     Version   Rev   Tracking       Publisher   Notes\n"
        "bare     1.0       5     latest/stable  canonical** base\n"
        "code     110a328e  258   latest/stable  vscode**    classic\n"
    )
    assert parse_snap_list(out) == {"bare": ("5", "base"), "code": ("258", "classic")}


def test_snap_refresh_list():
    out = "Name  Version  Rev  Size  Publisher  Notes\ncode  07f8  267  543MB  vscode**  classic\n"
    assert parse_snap_refresh_list(out) == {"code"}
    assert parse_snap_refresh_list("All snaps up to date.") == set()
