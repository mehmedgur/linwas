"""Ana pencere — aşama 0 iskeleti.

Şimdilik yalnızca karşılama metni ve algılanan sistem bilgisini gösterir. Bu bilgi, geliştirme
.deb'inin Pardus ve Ubuntu makinelerinde doğru çalıştığını görmek için kullanılır.
Asıl arayüz (menü, sayfalar, kuyruk) aşama 2'de gelecek.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer, qVersion
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from linwas import __version__
from linwas.backend.desktop import Desktop, detect_desktop, detect_session_type
from linwas.backend.distro import SupportStatus, detect_distro, evaluate_support

ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "linwas.svg"


def tr(text: str) -> str:
    """Bu penceredeki metinler için çeviri kısayolu."""
    return QCoreApplication.translate("MainWindow", text)


def support_message(status: SupportStatus) -> str:
    """Destek durumunu kullanıcıya gösterilecek metne çevirir."""
    messages = {
        SupportStatus.SUPPORTED: tr("Supported"),
        SupportStatus.END_OF_LIFE: tr(
            "Security updates for this system have ended. We recommend upgrading."
        ),
        SupportStatus.UNTESTED_FAMILY: tr(
            "This system is in the Debian/Ubuntu family but has not been tested."
        ),
        SupportStatus.UNSUPPORTED: tr("This system is not officially supported."),
    }
    return messages[status]


def desktop_label(desktop: Desktop) -> str:
    """Masaüstü adını kullanıcıya gösterilecek metne çevirir."""
    names = {
        Desktop.GNOME: "GNOME",
        Desktop.CINNAMON: "Cinnamon",
        Desktop.XFCE: "XFCE",
        Desktop.KDE: "KDE Plasma",
        Desktop.OTHER: tr("Other"),
        Desktop.UNKNOWN: tr("Unknown"),
    }
    label = names[desktop]
    if desktop not in (Desktop.UNKNOWN,) and not desktop.supported:
        label = f"{label} — {tr('limited support')}"
    return label


class MainWindow(QMainWindow):
    """Aşama 0 ana penceresi."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Linwas")
        self.setWindowIcon(QIcon.fromTheme("linwas", QIcon(str(ICON_PATH))))
        self.setMinimumSize(640, 440)

        distro = detect_distro()
        status = evaluate_support(distro)
        desktop = detect_desktop(os.environ)
        session = detect_session_type(os.environ) or tr("Unknown")

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel(tr("Welcome to Linwas"), central)
        title_font = title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.8)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel(tr("Development build {version}").format(version=__version__), central)
        layout.addWidget(subtitle)

        note = QLabel(
            tr("This is an empty skeleton. Features will arrive stage by stage."), central
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        line = QFrame(central)
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)

        heading = QLabel(tr("System information"), central)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)

        self._rows: list[tuple[str, str]] = [
            (tr("Distribution"), distro.display_name or tr("Unknown")),
            (tr("Linwas support"), support_message(status)),
            (tr("Desktop"), desktop_label(desktop)),
            (tr("Session"), session),
            ("Python", platform.python_version()),
            ("Qt", qVersion()),
        ]
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for label_text, value_text in self._rows:
            value = QLabel(value_text, central)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(QLabel(label_text + ":", central), value)
        layout.addLayout(form)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._copy_button = QPushButton(tr("Copy system information"), central)
        self._copy_button.clicked.connect(self._copy_info)
        buttons.addWidget(self._copy_button)
        layout.addLayout(buttons)

        self.setCentralWidget(central)

    def _copy_info(self) -> None:
        """Sistem bilgisini panoya kopyalar (hata bildirirken işe yarar)."""
        text = "\n".join(f"{label}: {value}" for label, value in self._rows)
        text = f"Linwas {__version__}\n{text}"
        QGuiApplication.clipboard().setText(text)
        self._copy_button.setText(tr("Copied"))
        QTimer.singleShot(2000, lambda: self._copy_button.setText(tr("Copy system information")))
