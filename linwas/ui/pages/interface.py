"""Arayüz sayfaları: Windows görünümü, tema ve duvar kâğıdı, yazı tipleri, ekran ve ölçekleme.

Ayarlar kullanıcı yetkisiyle `gsettings` üzerinden yapılır (bkz. backend/appearance).
Desteklenmeyen masaüstünde ilgili sistem ayarları açılır.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import appearance
from linwas.backend.apt_search import is_installed
from linwas.backend.desktop import detect_desktop
from linwas.backend.settings_launcher import command_for, open_settings
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("InterfacePages", text)


class _Worker(QThread):
    done = Signal(object)

    def __init__(self, fn) -> None:  # noqa: ANN001
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception:
            self.done.emit(None)


class _InterfacePage(BasePage):
    """Ortak iskelet: başlık, açıklama, kartlar, sistem ayarı düğmesi."""

    settings_item = "all"

    def __init__(self, title: str, hint: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.desktop = detect_desktop(os.environ).value
        self._workers: list[_Worker] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(36, 28, 36, 28)
        self.body.setSpacing(12)

        header = QHBoxLayout()
        h = QLabel(title, content)
        h.setObjectName("H1")
        header.addWidget(h)
        header.addStretch(1)
        sys_btn = QPushButton(tr("Open in system settings"), content)
        sys_btn.setEnabled(command_for(self.settings_item, self.desktop) is not None)
        sys_btn.clicked.connect(lambda: open_settings(self.settings_item, self.desktop))
        header.addWidget(sys_btn)
        self.body.addLayout(header)
        if hint:
            lbl = QLabel(hint, content)
            lbl.setObjectName("Secondary")
            lbl.setWordWrap(True)
            self.body.addWidget(lbl)

        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def card(self, title: str) -> Card:
        card = Card(self)
        h = QLabel(title, card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        self.body.addWidget(card)
        return card

    def note(self, card: Card, text: str, color: str = "") -> QLabel:
        lbl = QLabel(text, card)
        lbl.setWordWrap(True)
        if color:
            lbl.setStyleSheet(f"color:{color};")
        else:
            lbl.setObjectName("Secondary")
        card.layout.addWidget(lbl)
        return lbl

    def unsupported(self) -> None:
        card = self.card(tr("Not available on this desktop"))
        self.note(
            card,
            tr(
                "Linwas can change this on GNOME and Cinnamon. Use “Open in system settings” "
                "on this desktop."
            ),
        )

    def run_bg(self, fn, slot) -> None:  # noqa: ANN001
        worker = _Worker(fn)
        worker.done.connect(slot)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def finish(self) -> None:
        self.body.addStretch(1)


# --- Windows görünümü ---


class WindowsAppearancePage(_InterfacePage):
    settings_item = "themes"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            tr("Windows Appearance"),
            tr("Make the desktop look and work more like Windows."),
            parent,
        )
        if self.desktop == "gnome":
            self._build_gnome()
        elif self.desktop in ("cinnamon", "xfce"):
            card = self.card(tr("Your desktop already looks like Windows"))
            self.note(
                card,
                tr(
                    "It has a taskbar at the bottom, a start menu and minimize/maximize "
                    "buttons. You can fine-tune it in the system settings."
                ),
            )
        else:
            self.unsupported()
        self.finish()

    def _build_gnome(self) -> None:
        card = self.card(tr("Taskbar"))
        self.note(
            card,
            tr(
                "Adds a Windows-style taskbar at the bottom of the screen with your open "
                "windows, pinned apps and the clock (Dash to Panel)."
            ),
        )
        row = QHBoxLayout()
        self._panel_btn = QPushButton(tr("Checking…"), card)
        self._panel_btn.setProperty("primary", True)
        self._panel_btn.setEnabled(False)
        self._panel_btn.clicked.connect(self._on_panel_btn)
        row.addWidget(self._panel_btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        self._panel_note = self.note(card, "")
        self._panel_state = "missing"

        card = self.card(tr("Window buttons"))
        self.note(card, tr("Show minimize and maximize buttons on every window, like Windows."))
        row = QHBoxLayout()
        on = QPushButton(tr("Show minimize and maximize"), card)
        on.clicked.connect(
            lambda: appearance.set_value("gnome", "buttons", appearance.WINDOWS_BUTTON_LAYOUT)
        )
        row.addWidget(on)
        off = QPushButton(tr("Only close button (GNOME default)"), card)
        off.clicked.connect(lambda: appearance.set_value("gnome", "buttons", "appmenu:close"))
        row.addWidget(off)
        row.addStretch(1)
        card.layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        self.run_bg(appearance.extension_state, self._on_state)

    def on_tasks_finished(self) -> None:
        if self.desktop == "gnome":
            self._refresh()

    def _on_state(self, state: str | None) -> None:
        self._panel_state = state or "missing"
        self._panel_btn.setEnabled(True)
        if self._panel_state == "missing":
            if is_installed(appearance.DASH_TO_PANEL_PACKAGE):
                # Paket kurulu ama GNOME eklentiyi henüz görmüyor
                self._panel_btn.setText(tr("Turn on taskbar"))
                self._panel_note.setText(
                    tr("Installed. Log out and back in once, then turn it on here.")
                )
            else:
                self._panel_btn.setText(tr("Install taskbar"))
                self._panel_note.setText("")
        elif self._panel_state == "disabled":
            self._panel_btn.setText(tr("Turn on taskbar"))
            self._panel_note.setText("")
        else:
            self._panel_btn.setText(tr("Turn off taskbar"))
            self._panel_note.setText(tr("The taskbar is on."))

    def _on_panel_btn(self) -> None:
        if self._panel_state == "missing" and not is_installed(appearance.DASH_TO_PANEL_PACKAGE):
            self.task_run_now.emit(
                Task(
                    label=tr("Install Windows-style taskbar"),
                    steps=[
                        TaskStep(
                            op_id="package.install",
                            params={"name": appearance.DASH_TO_PANEL_PACKAGE},
                        )
                    ],
                )
            )
            return
        appearance.set_extension(self._panel_state != "enabled")
        self._refresh()


# --- Tema ve duvar kâğıdı ---


class ThemePage(_InterfacePage):
    settings_item = "background"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Theme & Wallpaper"), "", parent)
        if not appearance.supported(self.desktop):
            self.unsupported()
            self.finish()
            return
        card = self.card(tr("Light or dark"))
        self._group = QButtonGroup(self)
        self._light = QRadioButton(tr("Light"), card)
        self._dark = QRadioButton(tr("Dark"), card)
        for i, rb in enumerate((self._light, self._dark)):
            self._group.addButton(rb, i)
            card.layout.addWidget(rb)
        self._group.idClicked.connect(lambda i: appearance.set_dark(self.desktop, i == 1))

        card = self.card(tr("Wallpaper"))
        self._wall_lbl = self.note(card, "")
        row = QHBoxLayout()
        pick = QPushButton(tr("Choose a picture…"), card)
        pick.clicked.connect(self._pick_wallpaper)
        row.addWidget(pick)
        row.addStretch(1)
        card.layout.addLayout(row)
        self.finish()
        self.run_bg(self._read, self._on_read)

    def _read(self) -> tuple[bool, str]:
        return appearance.is_dark(self.desktop), appearance.get(self.desktop, "wallpaper") or ""

    def _on_read(self, result: tuple[bool, str] | None) -> None:
        if not result:
            return
        dark, wall = result
        (self._dark if dark else self._light).setChecked(True)
        name = Path(wall.removeprefix("file://")).name if wall else "—"
        self._wall_lbl.setText(tr("Current: {name}").format(name=name))

    def _pick_wallpaper(self) -> None:
        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Choose a picture"),
            start,
            tr("Images (*.png *.jpg *.jpeg *.webp *.svg)"),
        )
        if path and appearance.set_wallpaper(self.desktop, Path(path)):
            self._wall_lbl.setText(tr("Current: {name}").format(name=Path(path).name))


# --- Yazı tipleri ---


class FontsPage(_InterfacePage):
    settings_item = "fonts"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Fonts"), "", parent)
        card = self.card(tr("Fonts compatible with Microsoft Office"))
        self.note(
            card,
            tr(
                "Carlito (same size as Calibri), Caladea (Cambria) and Liberation (Arial, "
                "Times New Roman, Courier New). Documents from Windows keep their layout."
            ),
        )
        self._fonts_status = self.note(card, tr("Checking…"))
        row = QHBoxLayout()
        self._install_btn = QPushButton(tr("Install fonts"), card)
        self._install_btn.setProperty("primary", True)
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._install)
        row.addWidget(self._install_btn)
        row.addStretch(1)
        card.layout.addLayout(row)

        card = self.card(tr("Original Microsoft fonts"))
        self.note(
            card,
            tr(
                "Arial, Times New Roman, Verdana, Georgia and others. These fonts are not free "
                "software: Microsoft's licence terms apply. Installing downloads them from "
                "Microsoft; afterwards the terms are in "
                "/usr/share/doc/ttf-mscorefonts-installer/READ_ME!.gz."
            ),
        )
        self._eula = QCheckBox(tr("I accept Microsoft's licence terms for these fonts"), card)
        card.layout.addWidget(self._eula)
        row = QHBoxLayout()
        self._ms_btn = QPushButton(tr("Install Microsoft fonts"), card)
        self._ms_btn.setEnabled(False)
        self._eula.toggled.connect(self._ms_btn.setEnabled)
        self._ms_btn.clicked.connect(self._install_ms)
        row.addWidget(self._ms_btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        self.finish()
        self.on_tasks_finished()

    def on_tasks_finished(self) -> None:
        self.run_bg(self._missing, self._on_missing)

    @staticmethod
    def _missing() -> list[str]:
        return [p for p in appearance.COMPAT_FONT_PACKAGES if not is_installed(p)]

    def _on_missing(self, missing: list[str] | None) -> None:
        missing = missing or []
        self._missing_pkgs = missing
        self._install_btn.setEnabled(bool(missing))
        self._fonts_status.setText(
            tr("Not installed: {names}").format(names=", ".join(missing))
            if missing
            else tr("✓ Installed")
        )

    def _install_ms(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install Microsoft fonts"),
                steps=[TaskStep(op_id="fonts.install_microsoft", params={})],
            )
        )

    def _install(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install Office-compatible fonts"),
                steps=[
                    TaskStep(op_id="package.install", params={"name": p})
                    for p in self._missing_pkgs
                ],
            )
        )


# --- Ekran ve ölçekleme ---

_SCALES = (0.9, 1.0, 1.1, 1.25, 1.5)


class DisplayPage(_InterfacePage):
    settings_item = "display"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            tr("Display & Scaling"),
            tr("Screen resolution and multiple monitors are set in the system display settings."),
            parent,
        )
        if not appearance.supported(self.desktop):
            self.unsupported()
            self.finish()
            return
        card = self.card(tr("Text size"))
        self.note(card, tr("Makes text bigger or smaller everywhere, without blurring."))
        row = QHBoxLayout()
        small = QLabel("A", card)
        row.addWidget(small)
        self._slider = QSlider(Qt.Orientation.Horizontal, card)
        self._slider.setRange(0, len(_SCALES) - 1)
        self._slider.setPageStep(1)
        self._slider.setAccessibleName(tr("Text size"))
        row.addWidget(self._slider, 1)
        big = QLabel("<span style='font-size:18px'>A</span>", card)
        row.addWidget(big)
        card.layout.addLayout(row)
        self._value = self.note(card, "")
        self._slider.valueChanged.connect(self._on_value)
        self._slider.sliderReleased.connect(self._apply)
        self.finish()
        self.run_bg(lambda: appearance.get(self.desktop, "text_scale"), self._on_read)

    def _on_read(self, value: str | None) -> None:
        try:
            current = float(value or 1.0)
        except ValueError:
            current = 1.0
        index = min(range(len(_SCALES)), key=lambda i: abs(_SCALES[i] - current))
        self._slider.blockSignals(True)
        self._slider.setValue(index)
        self._slider.blockSignals(False)
        self._preview(index)

    def _preview(self, index: int) -> None:
        self._value.setText(f"%{round(_SCALES[index] * 100)}")

    def _on_value(self, index: int) -> None:
        self._preview(index)
        # Klavye/tıklama ile değişince hemen uygula; sürüklerken bırakınca uygulanır
        if not self._slider.isSliderDown():
            self._apply()

    def _apply(self) -> None:
        appearance.set_value(self.desktop, "text_scale", _SCALES[self._slider.value()])
