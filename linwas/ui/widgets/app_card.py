"""Program kartları: simge (yoksa harfli renkli kare), ad, açıklama, kaynak, Kur düğmesi."""

from __future__ import annotations

import zlib

from PySide6.QtCore import QCoreApplication, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("AppCard", text)


# Harfli simge zeminleri (beyaz yazıyla okunur, açık/koyu temada uyumlu)
_AVATAR_COLORS = (
    "#0067c0",
    "#5c35cc",
    "#c42b1c",
    "#0e7a0e",
    "#b4009e",
    "#ca5010",
    "#038387",
    "#4f6bed",
)


def source_text(source: str) -> str:
    """Kaynağın son kullanıcıya yönelik adı."""
    return {
        "apt": tr("From your system's software sources"),
        "flatpak": tr("From Flathub"),
        "third-party": tr("From the maker's official repository"),
    }.get(source, "")


def _letter_pixmap(name: str, size: int) -> QPixmap:
    app = QGuiApplication.instance()
    dpr = app.devicePixelRatio() if isinstance(app, QGuiApplication) else 1.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    color = QColor(_AVATAR_COLORS[zlib.crc32(name.encode()) % len(_AVATAR_COLORS)])
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.25, size * 0.25)
    painter.fillPath(path, color)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(int(size * 0.45))
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    letter = next((ch for ch in name if ch.isalnum()), "?").upper()
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letter)
    painter.end()
    return pm


class AppAvatar(QLabel):
    """Kurulu simge temasında programın simgesi varsa o, yoksa harfli renkli kare."""

    def __init__(self, name: str, icon: str = "", size: int = 44, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        if icon and QIcon.hasThemeIcon(icon):
            self.setPixmap(QIcon.fromTheme(icon).pixmap(size, size))
        else:
            self.setPixmap(_letter_pixmap(name, size))


class _ActionArea(QWidget):
    """Kur düğmesi ya da "Kurulu" bilgisi (+ isteğe bağlı Kaldır)."""

    install_clicked = Signal()
    remove_clicked = Signal()

    def __init__(
        self, installed: bool, available: bool, removable: bool, parent: QWidget | None = None
    ):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        if installed:
            done = QLabel("✓ " + tr("Installed"), self)
            done.setObjectName("Success")
            row.addWidget(done)
            if removable:
                remove = QPushButton(tr("Remove"), self)
                remove.clicked.connect(self.remove_clicked)
                row.addWidget(remove)
        else:
            btn = QPushButton(tr("Install") if available else tr("Unavailable"), self)
            btn.setProperty("primary", available)
            btn.setEnabled(available)
            btn.setMinimumWidth(84)
            btn.clicked.connect(self.install_clicked)
            row.addWidget(btn)


class FeaturedCard(Card):
    """Keşfet ızgarasındaki program kartı."""

    install_clicked = Signal()

    def __init__(
        self,
        name: str,
        description: str,
        icon: str,
        source: str,
        installed: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumWidth(220)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(AppAvatar(name, icon, 44, self), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(name, self)
        title.setObjectName("AppName")
        texts.addWidget(title)
        desc = QLabel(description, self)
        desc.setObjectName("Secondary")
        desc.setWordWrap(True)
        texts.addWidget(desc)
        top.addLayout(texts, 1)
        self.layout.addLayout(top)
        self.layout.addStretch(1)

        bottom = QHBoxLayout()
        where = QLabel(source_text(source), self)
        where.setObjectName("Caption")
        where.setWordWrap(True)
        bottom.addWidget(where, 1)
        action = _ActionArea(installed, bool(source), False, self)
        action.install_clicked.connect(self.install_clicked)
        bottom.addWidget(action, 0, Qt.AlignmentFlag.AlignBottom)
        self.layout.addLayout(bottom)
        if not source and not installed:
            self.setToolTip(tr("Not available for this system (Flatpak may be needed)."))


class ResultCard(Card):
    """Arama sonucu satırı."""

    install_clicked = Signal()
    remove_clicked = Signal()

    def __init__(
        self,
        name: str,
        description: str,
        source: str,
        installed: bool,
        parent: QWidget | None = None,
        icon: str = "",
        note: str = "",
        version: str = "",
        recommended: bool = False,
    ) -> None:
        super().__init__(parent)
        self.layout.setContentsMargins(14, 10, 14, 10)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(AppAvatar(name, icon, 40, self), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        head = QHBoxLayout()
        title = QLabel(name, self)
        title.setObjectName("AppName")
        head.addWidget(title)
        if recommended:
            badge = QLabel(tr("Recommended"), self)
            badge.setObjectName("Pill")
            head.addWidget(badge)
        head.addStretch(1)
        texts.addLayout(head)
        if description:
            desc = QLabel(description, self)
            desc.setObjectName("Secondary")
            desc.setWordWrap(True)
            texts.addWidget(desc)
        if note:
            warn = QLabel(note, self)
            warn.setObjectName("Warning")
            warn.setWordWrap(True)
            texts.addWidget(warn)
        where = QLabel(source_text(source), self)
        where.setObjectName("Caption")
        if version:
            where.setToolTip(tr("Version {version}").format(version=version))
        texts.addWidget(where)
        row.addLayout(texts, 1)
        action = _ActionArea(installed, bool(source), source in ("apt", "flatpak"), self)
        action.install_clicked.connect(self.install_clicked)
        action.remove_clicked.connect(self.remove_clicked)
        row.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
        self.layout.addLayout(row)
