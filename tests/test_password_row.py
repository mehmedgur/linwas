"""Şifre satırı: gizli başlar, istenince okunur, süre dolunca ya da gizlenince silinir."""

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


def _wait(condition, timeout=3.0):
    from PySide6.QtTest import QTest

    waited = 0
    while not condition() and waited < timeout * 1000:
        QTest.qWait(20)
        waited += 20
    return condition()


def _row(fetch):
    from linwas.ui.widgets.password_row import PasswordRow

    row = PasswordRow(fetch)
    row.show()
    return row


def test_starts_hidden_and_does_not_read(qapp):
    reads = []
    row = _row(lambda: reads.append(1) or "x")
    assert reads == [] and not row.revealed
    assert row._edit.text() == "" and not row._copy.isEnabled()


def test_reveal_copy_and_manual_hide(qapp):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QLineEdit

    row = _row(lambda: "gizli şifre")
    row._show.click()
    assert _wait(lambda: row.revealed)
    assert row._edit.text() == "gizli şifre"
    assert row._edit.echoMode() == QLineEdit.EchoMode.Normal
    assert row._show.text() == "Hide" and row._copy.isEnabled()
    assert "30 seconds" in row._note.text()
    row._copy.click()
    assert QGuiApplication.clipboard().text() == "gizli şifre" and row._copy.text() == "Copied"

    row._show.click()  # elle gizle
    assert not row.revealed and row._edit.text() == ""
    assert row._edit.echoMode() == QLineEdit.EchoMode.Password
    assert not row._copy.isEnabled() and row._show.text() == "Show" and row._copy.text() == "Copy"


def test_hides_after_the_time_is_up(qapp):
    row = _row(lambda: "gizli")
    row._show.click()
    assert _wait(lambda: row.revealed)
    assert row._timer.isActive() and row._timer.interval() == 30_000
    row._timer.timeout.emit()  # süre doldu
    assert not row.revealed and row._edit.text() == ""
    assert not row._timer.isActive()


def test_hides_when_the_row_is_hidden(qapp):
    row = _row(lambda: "gizli")
    row._show.click()
    assert _wait(lambda: row.revealed)
    row.hide()  # pencere kapandı / sekme değişti
    assert not row.revealed and row._edit.text() == ""


@pytest.mark.parametrize("value", [None, ""])
def test_unreadable_password_shows_a_message(qapp, value):
    row = _row(lambda: value)
    row._show.click()
    assert _wait(lambda: row._note.isVisible())
    assert "could not be read" in row._note.text()
    assert not row.revealed and row._show.isEnabled() and row._edit.text() == ""
