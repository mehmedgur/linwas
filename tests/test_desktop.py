"""Masaüstü ve oturum türü algılama testleri."""

import pytest

from linwas.backend.desktop import Desktop, detect_desktop, detect_session_type


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ubuntu:GNOME", Desktop.GNOME),
        ("GNOME", Desktop.GNOME),
        ("X-Cinnamon", Desktop.CINNAMON),
        ("XFCE", Desktop.XFCE),
        ("KDE", Desktop.KDE),
        ("Budgie:GNOME", Desktop.GNOME),
        ("LXQt", Desktop.OTHER),
        ("", Desktop.UNKNOWN),
    ],
)
def test_detect_desktop(value, expected):
    assert detect_desktop({"XDG_CURRENT_DESKTOP": value}) is expected


def test_detect_desktop_falls_back_to_desktop_session():
    assert detect_desktop({"DESKTOP_SESSION": "xfce"}) is Desktop.XFCE


def test_supported_desktops():
    assert Desktop.GNOME.supported
    assert Desktop.CINNAMON.supported
    assert Desktop.XFCE.supported
    assert not Desktop.KDE.supported
    assert not Desktop.OTHER.supported


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"XDG_SESSION_TYPE": "wayland"}, "wayland"),
        ({"XDG_SESSION_TYPE": "x11"}, "x11"),
        ({"XDG_SESSION_TYPE": "tty", "WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
        ({"DISPLAY": ":0"}, "x11"),
        ({}, ""),
    ],
)
def test_detect_session_type(env, expected):
    assert detect_session_type(env) == expected
