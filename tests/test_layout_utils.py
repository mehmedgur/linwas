# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""clear_layout: sahibi hemen yok edilse de çökmemeli (bekleyen deleteLater olayı kalmaz)."""

import gc
import os

import pytest


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # sistem kütüphanesi (ör. libEGL) eksik
        pytest.skip(f"Qt Widgets yüklenemedi: {exc}")
    return QApplication.instance() or QApplication([])


def test_clear_layout_then_destroy_owner_does_not_crash(qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton, QWidget

    from linwas.ui.widgets.layout_utils import clear_layout

    for _ in range(5):
        owner = QWidget()
        owner.show()
        grid = QGridLayout(owner)
        for i in range(6):
            grid.addWidget(QLabel(f"satır {i}", owner), i, 0)
        grid.addWidget(QToolButton(owner), 6, 0)
        assert grid.count() == 7
        clear_layout(grid)
        assert grid.count() == 0
        del grid, owner  # sahibi hemen yok et
        gc.collect()
        for _ in range(5):
            QTest.qWait(10)  # bekleyen olaylar işlenir


def test_clear_layout_on_empty_layout(qapp):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from linwas.ui.widgets.layout_utils import clear_layout

    owner = QWidget()
    layout = QVBoxLayout(owner)
    clear_layout(layout)
    layout.addStretch(1)  # yaylar (bileşen olmayan öğeler) da kalkar
    clear_layout(layout)
    assert layout.count() == 0
