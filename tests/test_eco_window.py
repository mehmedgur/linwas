"""Eco ayarlar penceresi (ekransız 'offscreen' platformunda; Qt yoksa atlanır)."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    return QApplication.instance() or QApplication([])


def test_format_uptime(qapp):
    from linwas.ui.eco.about_page import format_uptime

    assert format_uptime(3 * 86400 + 7 * 3600) == "3 days 7 hours"
    assert format_uptime(2 * 3600 + 5 * 60) == "2 hours 5 minutes"
    assert format_uptime(125) == "2 minutes"


def test_window_pages_and_navigation(qapp):
    from linwas.ui.eco.settings_window import EcoSettingsWindow, nav_groups
    from linwas.ui.theme.manager import PREFERENCE_DARK, ThemeManager

    themes = ThemeManager(qapp, "eco")
    themes.apply()
    window = EcoSettingsWindow(themes)
    keys = [entry.key for _group, entries in nav_groups() for entry in entries]
    assert keys == [
        "appearance", "display", "network", "sound", "storage",
        "users", "security", "apps", "accessibility", "about",
    ]  # fmt: skip
    assert window._stack.count() == len(keys)
    assert window._nav.currentItem().text() == "About"  # açılışta Hakkında

    window.show_page("sound")
    assert window._stack.currentIndex() == keys.index("sound")

    themes.set_preference(PREFERENCE_DARK)  # simgeler yeniden boyanır, hata vermemeli
    assert not window._nav.item(1).icon().isNull()
