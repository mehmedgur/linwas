"""Şifre satırı: gizli başlar, "Göster"e basılınca okunur, 30 saniye sonra yeniden gizlenir."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from linwas.ui.widgets.jobs import Jobs

PASSWORD_SECONDS = 30  # gösterilen şifre bu süre sonra yeniden gizlenir


def tr(text: str) -> str:
    return QCoreApplication.translate("PasswordRow", text)


class PasswordRow(QWidget):
    """Şifre yalnızca istenince `fetch` ile (arka planda) okunur; hiçbir yere kaydedilmez.

    Satır gizlenirken (pencere kapanır, sekme değişir) şifre de ekrandan silinir.
    """

    def __init__(self, fetch: Callable[[], str | None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fetch = fetch
        self._jobs = Jobs()
        self._revealed = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(self)
        self._edit.setReadOnly(True)
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("••••••••")
        self._show = QPushButton(tr("Show"), self)
        self._show.clicked.connect(self._toggle)
        self._copy = QPushButton(tr("Copy"), self)
        self._copy.setEnabled(False)
        self._copy.clicked.connect(self._copy_password)
        row.addWidget(self._edit, 1)
        row.addWidget(self._show)
        row.addWidget(self._copy)
        outer.addLayout(row)
        self._note = QLabel("", self)
        self._note.setObjectName("Secondary")
        self._note.setWordWrap(True)
        self._note.setVisible(False)
        outer.addWidget(self._note)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PASSWORD_SECONDS * 1000)
        self._timer.timeout.connect(self.hide_password)

    @property
    def revealed(self) -> bool:
        return self._revealed

    def _toggle(self) -> None:
        if self._revealed:
            self.hide_password()
            return
        self._show.setEnabled(False)
        self._jobs.run(self._fetch, self._on_password)

    def _on_password(self, result: object) -> None:
        self._show.setEnabled(True)
        if not isinstance(result, str) or not result:
            self._note.setText(
                tr(
                    "The password could not be read. It may be locked in the system keyring "
                    "or kept by another account."
                )
            )
            self._note.setVisible(True)
            return
        self._edit.setText(result)
        self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
        self._revealed = True
        self._show.setText(tr("Hide"))
        self._copy.setEnabled(True)
        self._note.setText(tr("The password is hidden again after 30 seconds."))
        self._note.setVisible(True)
        self._timer.start()

    def hide_password(self) -> None:
        self._timer.stop()
        self._edit.clear()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._revealed = False
        self._show.setText(tr("Show"))
        self._copy.setText(tr("Copy"))
        self._copy.setEnabled(False)
        self._note.setVisible(False)

    def _copy_password(self) -> None:
        if self._revealed:
            QGuiApplication.clipboard().setText(self._edit.text())
            self._copy.setText(tr("Copied"))

    def hideEvent(self, event: object) -> None:  # type: ignore[override]
        self.hide_password()
        super().hideEvent(event)  # type: ignore[misc]
