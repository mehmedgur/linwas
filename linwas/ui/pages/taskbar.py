"""Arayüz › Görev çubuğu: hazır düzen, pencere düğmeleri, görünüm, yerleşim ve medya widget'ı.

Eski "Windows görünümü" sayfası buraya katıldı (Windows tarzı görev çubuğu = "Windows gibi" düzeni).
Görünüm ve medya Linwas görev çubuğu eklentisi ister (GNOME, Dash to Panel üstüne); hazır düzen,
pencere düğmeleri ve yerleşim eklentisiz de çalışır. Değişiklikler anında uygulanır
(kararlar.md › Yeni özellikler › 9 › F).
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import appearance, taskbar, window_groups, workgroups
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card


def tr(text: str) -> str:
    return QCoreApplication.translate("TaskbarPage", text)


def extension_strings() -> dict[str, str]:
    """Eklentinin göstereceği çevrilmiş metinler."""
    return {
        "play": tr("Play"),
        "pause": tr("Pause"),
        "nothing_playing": tr("Nothing is playing"),
        "last_played": tr("Last played:"),
        "open_player": tr("Open %1"),
        "switch_player": tr("Switch player"),
        "unknown_title": tr("Unknown title"),
        "unknown_artist": tr("Unknown artist"),
    }


class _Status(QThread):
    done = Signal(dict)

    def __init__(self, action: object = None) -> None:
        super().__init__()
        self._action = action

    def run(self) -> None:
        version = window_groups.shell_version()
        if callable(self._action):
            self._action(version)
        elif taskbar.is_installed() and not taskbar.is_current(version):
            taskbar.install(version)  # Linwas güncellenince eklenti dosyaları yenilenir
        self.done.emit(
            {
                "desktop": workgroups.desktop_kind(),
                "state": taskbar.state(version),
                "dtp": taskbar.dtp_installed(),
                "dock": bool(taskbar.dock_uuid()),
                "preset": taskbar.current_preset(),
                "layout": taskbar.read_layout(),
                "previous": taskbar.has_previous(),
            }
        )


def _segmented(parent: QWidget, options: list[tuple[str, str]], current: str, slot) -> QWidget:  # noqa: ANN001
    box = QWidget(parent)
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    group = QButtonGroup(box)
    for key, label in options:
        b = QPushButton(label, box)
        b.setObjectName("Chip")
        b.setCheckable(True)
        b.setChecked(key == current)
        b.clicked.connect(lambda _=False, k=key: slot(k))
        group.addButton(b)
        row.addWidget(b)
    row.addStretch(1)
    return box


def _row(card: Card, title: str, desc: str, widget: QWidget) -> None:
    row = QHBoxLayout()
    texts = QVBoxLayout()
    texts.setSpacing(2)
    texts.addWidget(QLabel(title, card))
    if desc:
        d = QLabel(desc, card)
        d.setObjectName("Secondary")
        d.setWordWrap(True)
        texts.addWidget(d)
    row.addLayout(texts, 1)
    row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
    card.layout.addLayout(row)


class TaskbarPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: _Status | None = None
        self._status: dict = {}
        self._cfg = taskbar.load_config()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self._outer = QVBoxLayout(content)
        self._outer.setContentsMargins(36, 28, 36, 28)
        self._outer.setSpacing(12)
        title = QLabel(tr("Taskbar"), content)
        title.setObjectName("H1")
        self._outer.addWidget(title)
        intro = QLabel(
            tr(
                "Choose how the taskbar looks and add a media control. Changes appear on the "
                "desktop right away. (Windows: Taskbar settings · macOS: Dock & Menu Bar)"
            ),
            content,
        )
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        self._outer.addWidget(intro)
        self._body = QVBoxLayout()
        self._body.setSpacing(12)
        self._outer.addLayout(self._body)
        self._outer.addStretch(1)
        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        self._refresh()

    def on_tasks_finished(self) -> None:
        if self.isVisible():
            self._refresh()

    def _refresh(self, action: object = None) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = _Status(action)
        self._worker.done.connect(self._on_status)
        self._worker.start()

    def _clear(self, layout) -> None:  # noqa: ANN001
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                self._clear(item.layout())

    def _save(self) -> None:
        self._cfg.strings = extension_strings()
        taskbar.save_config(self._cfg)

    # --- Sayfa ---

    def _on_status(self, s: dict) -> None:
        self._status = s
        self._clear(self._body)
        if s["desktop"] in ("cinnamon", "xfce"):
            card = Card()
            t = QLabel(tr("Your desktop already looks like Windows"), card)
            t.setStyleSheet("font-weight: 600;")
            card.layout.addWidget(t)
            d = QLabel(
                tr(
                    "It has a taskbar at the bottom, a start menu and minimize/maximize buttons. "
                    "You can fine-tune it in the system settings."
                ),
                card,
            )
            d.setObjectName("Secondary")
            d.setWordWrap(True)
            card.layout.addWidget(d)
            self._body.addWidget(card)
            return
        if s["state"] == "unsupported":
            self._build_setup(s)
            return
        # Eklentisiz çalışanlar
        self._build_presets(s)
        self._build_window_buttons()
        if s["dtp"] and s["preset"] == "windows":
            self._build_layout(s["layout"])
        # Linwas eklentisi gerekenler
        self._section(tr("Look and media (Linwas taskbar extension)"))
        self._build_setup(s)
        if s["state"] in ("active", "restart"):
            self._build_look()
            self._build_media()

    def _section(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("Secondary")
        self._body.addWidget(lbl)

    def _build_setup(self, s: dict) -> None:
        card = Card()
        state = s["state"]
        install = lambda: self._refresh(self._install)  # noqa: E731
        texts = {
            "active": (True, tr("The Linwas taskbar extension is on."), "", None),
            "missing": (
                False,
                tr("Install the Linwas taskbar extension to use these settings."),
                tr("Install"),
                install,
            ),
            "off": (
                False,
                tr("The Linwas taskbar extension is turned off."),
                tr("Turn on"),
                install,
            ),
            "restart": (
                False,
                tr(
                    "Installed. GNOME starts new extensions after a restart: log out and back in "
                    "once. (On X11 you can also press Alt+F2, type r and press Enter; open windows "
                    "stay open.)"
                ),
                "",
                None,
            ),
            "error": (
                False,
                tr("The extension could not start. Reinstall it, then log out and back in."),
                tr("Reinstall"),
                install,
            ),
            "unsupported": (
                False,
                tr("The Linwas taskbar works on GNOME 42–48 for now."),
                "",
                None,
            ),
        }
        ok, text, button, slot = texts.get(state, texts["error"])
        row = QHBoxLayout()
        lbl = QLabel(("✓ " if ok else "") + text, card)
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        if button:
            b = QPushButton(button, card)
            b.setProperty("primary", True)
            b.clicked.connect(slot)
            row.addWidget(b)
        if state not in ("missing", "unsupported"):
            remove = QPushButton(tr("Remove"), card)
            remove.clicked.connect(self._remove)
            row.addWidget(remove)
        card.layout.addLayout(row)
        self._body.addWidget(card)

    def _build_window_buttons(self) -> None:
        self._section(tr("Window buttons"))
        card = Card()
        d = QLabel(tr("Show minimize and maximize buttons on every window, like Windows."), card)
        d.setObjectName("Secondary")
        d.setWordWrap(True)
        card.layout.addWidget(d)
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
        self._body.addWidget(card)

    def _install(self, version: int) -> None:
        self._cfg.strings = extension_strings()
        taskbar.save_config(self._cfg)
        taskbar.install(version)

    def _remove(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Remove the Linwas taskbar"),
            tr("The taskbar returns to its normal look. Remove the extension?"),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._refresh(lambda _v: taskbar.uninstall())

    def _build_presets(self, s: dict) -> None:
        self._section(tr("Ready-made layout"))
        row = QHBoxLayout()
        row.setSpacing(12)
        presets = (
            ("windows", tr("Like Windows"), tr("One panel at the bottom with the app menu")),
            ("macos", tr("Like macOS"), tr("Thin bar at the top, centred dock at the bottom")),
            ("gnome", tr("GNOME default"), tr("Top bar and the Activities overview")),
        )
        for key, name, desc in presets:
            card = Card()
            t = QLabel(name, card)
            t.setStyleSheet("font-weight: 600;")
            card.layout.addWidget(t)
            d = QLabel(desc, card)
            d.setObjectName("Secondary")
            d.setWordWrap(True)
            card.layout.addWidget(d)
            if s["preset"] == key:
                cur = QLabel(tr("In use"), card)
                cur.setObjectName("Success")
                card.layout.addWidget(cur)
            else:
                b = QPushButton(tr("Use"), card)
                b.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
                card.layout.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
            row.addWidget(card, 1)
        self._body.addLayout(row)
        if s["previous"]:
            back = QPushButton(tr("Return to the previous layout"))
            back.clicked.connect(lambda: self._refresh(lambda _v: taskbar.restore_previous()))
            self._body.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)

    def _apply_preset(self, key: str) -> None:
        result = taskbar.apply_preset(key)
        if result == "need_dock":
            self.task_run_now.emit(
                Task(
                    label=tr("Install the dock (Dash to Dock)"),
                    steps=[
                        TaskStep(op_id="package.install", params={"name": taskbar.DOCK_PACKAGE})
                    ],
                )
            )
            return
        if result == "restart":
            QMessageBox.information(
                self,
                tr("Log out and back in first"),
                tr(
                    "The newly installed taskbar starts after you log out and back in once. "
                    "Nothing was changed; choose this layout again afterwards."
                ),
            )
            self._refresh()
            return
        if result == "need_dtp":
            self.task_run_now.emit(
                Task(
                    label=tr("Install the Windows-style taskbar (Dash to Panel)"),
                    steps=[
                        TaskStep(
                            op_id="package.install",
                            params={"name": "gnome-shell-extension-dash-to-panel"},
                        )
                    ],
                )
            )
            return
        self._refresh()

    def _build_look(self) -> None:
        self._section(tr("Appearance"))
        card = Card()
        styles = [
            ("transparent", tr("Transparent")),
            ("matte", tr("Matte")),
            ("blur", tr("Blurred")),
        ]
        _row(
            card,
            tr("Background"),
            tr("Blurred: the window and wallpaper behind show through softly."),
            _segmented(card, styles, self._cfg.panel_style, self._set_style),
        )
        slider_box = QWidget(card)
        sl = QHBoxLayout(slider_box)
        sl.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal, slider_box)
        slider.setRange(0, 90)
        slider.setValue(self._cfg.transparency)
        slider.setFixedWidth(240)
        slider.setAccessibleName(tr("Transparency"))
        value = QLabel(f"%{self._cfg.transparency}", slider_box)
        value.setMinimumWidth(44)
        slider.valueChanged.connect(lambda v: value.setText(f"%{v}"))
        slider.sliderReleased.connect(lambda: self._set("transparency", slider.value()))
        sl.addWidget(slider)
        sl.addWidget(value)
        _row(card, tr("Transparency"), tr("Not used with Matte."), slider_box)
        color = QComboBox(card)
        for key, label in (
            ("theme", tr("Follow the theme")),
            ("accent", tr("Accent color")),
            ("cover", tr("Cover of the playing song")),
        ):
            color.addItem(label, key)
        color.setCurrentIndex(max(0, color.findData(self._cfg.panel_color)))
        color.currentIndexChanged.connect(lambda: self._set("panel_color", color.currentData()))
        _row(
            card,
            tr("Color"),
            tr("Uses the light or dark theme and the Linwas accent color."),
            color,
        )
        self._body.addWidget(card)

    def _set_style(self, style: str) -> None:
        self._set("panel_style", style)

    def _set(self, name: str, value: object) -> None:
        setattr(self._cfg, name, value)
        self._save()

    def _build_layout(self, lay: taskbar.Layout) -> None:
        self._section(tr("Placement"))
        card = Card()
        pos = QComboBox(card)
        for key, label in (
            ("BOTTOM", tr("Bottom")),
            ("TOP", tr("Top")),
            ("LEFT", tr("Left")),
            ("RIGHT", tr("Right")),
        ):
            pos.addItem(label, key)
        pos.setCurrentIndex(max(0, pos.findData(lay.position)))
        pos.currentIndexChanged.connect(lambda: taskbar.set_position(pos.currentData()))
        _row(card, tr("Position"), "", pos)
        size_box = QWidget(card)
        sl = QHBoxLayout(size_box)
        sl.setContentsMargins(0, 0, 0, 0)
        size = QSlider(Qt.Orientation.Horizontal, size_box)
        size.setRange(*taskbar.SIZE_RANGE)
        size.setValue(lay.size)
        size.setFixedWidth(240)
        size.setAccessibleName(tr("Size"))
        value = QLabel(f"{lay.size} px", size_box)
        value.setMinimumWidth(56)
        size.valueChanged.connect(lambda v: value.setText(f"{v} px"))
        size.sliderReleased.connect(lambda: taskbar.set_size(size.value()))
        sl.addWidget(size)
        sl.addWidget(value)
        _row(card, tr("Size"), "", size_box)
        for title, desc, checked, fn in (
            (
                tr("Hide automatically"),
                tr("Hides when a window covers it."),
                lay.autohide,
                taskbar.set_autohide,
            ),
            (tr("Window preview on hover"), "", lay.previews, taskbar.set_previews),
        ):
            cb = QCheckBox(card)
            cb.setChecked(checked)
            cb.setAccessibleName(title)
            cb.toggled.connect(fn)
            _row(card, title, desc, cb)
        self._body.addWidget(card)

    def _build_media(self) -> None:
        self._section(tr("Media"))
        card = Card()
        for name, title, desc in (
            (
                "media_panel",
                tr("Small media control on the taskbar"),
                tr("Song name and play/pause; click it for the large card."),
            ),
            (
                "media_calendar",
                tr("Linwas media card in the calendar menu"),
                tr("Replaces GNOME's media card with a modern card with cover art."),
            ),
            (
                "cover_color",
                tr("Use the color of the cover art"),
                tr("When off, the theme color is used."),
            ),
        ):
            cb = QCheckBox(card)
            cb.setChecked(bool(getattr(self._cfg, name)))
            cb.setAccessibleName(title)
            cb.toggled.connect(lambda on, n=name: self._set(n, on))
            _row(card, title, desc, cb)
        styles = [
            ("transparent", tr("Transparent")),
            ("matte", tr("Matte")),
            ("blur", tr("Blurred")),
        ]
        _row(
            card,
            tr("Card background"),
            "",
            _segmented(card, styles, self._cfg.card_style, lambda k: self._set("card_style", k)),
        )
        note = QLabel(
            tr(
                "Works with Spotify, YouTube Music and YouTube in the browser, Rhythmbox, VLC and "
                "every player that supports MPRIS. When nothing is playing, the last played song "
                "is shown."
            ),
            card,
        )
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        card.layout.addWidget(note)
        self._body.addWidget(card)
