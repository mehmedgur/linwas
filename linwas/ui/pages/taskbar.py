# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kişiselleştirme › Görev çubuğu.

Hazır düzen, pencere düğmeleri, görünüm, yerleşim ve medya widget'ı.

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
from linwas.translations import percent
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
                "elements": taskbar.read_elements() if taskbar.dtp_installed() else [],
                "behaviour": taskbar.read_behaviour(),
                "clock": taskbar.read_clock(),
                "pinned": taskbar.read_pinned(),
                "dock_settings": taskbar.read_dock() if taskbar.dock_uuid() else None,
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
            self._build_behaviour(s)
            self._build_items(s)
        if s["preset"] == "macos" and s["dock_settings"] is not None:
            self._build_dock(s["dock_settings"])
        self._build_clock(s)
        self._build_pinned(s)
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
        off.clicked.connect(
            lambda: appearance.set_value("gnome", "buttons", appearance.GNOME_BUTTON_LAYOUT)
        )
        row.addWidget(off)
        mac = QPushButton(tr("On the left, like macOS"), card)
        mac.setToolTip(tr("Close, minimize and maximize at the top left of every window."))
        mac.clicked.connect(
            lambda: appearance.set_value("gnome", "buttons", appearance.MACOS_BUTTON_LAYOUT)
        )
        row.addWidget(mac)
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
        value = QLabel(percent(self._cfg.transparency), slider_box)
        value.setMinimumWidth(44)
        slider.valueChanged.connect(lambda v: value.setText(percent(v)))
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
        _row(
            card,
            tr("Menus and cards"),
            tr(
                "Every menu opened from the taskbar: quick settings, calendar, sound, network, "
                "media and the icons of other programs."
            ),
            _segmented(card, styles, self._cfg.card_style, lambda k: self._set("card_style", k)),
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

    def _build_dock(self, d: taskbar.Dock) -> None:
        """macOS düzeninin dock'u (Dash to Dock)."""
        self._section(tr("Dock"))
        card = Card()
        _row(
            card,
            tr("Position"),
            "",
            _segmented(
                card,
                [("BOTTOM", tr("Bottom")), ("LEFT", tr("Left")), ("RIGHT", tr("Right"))],
                d.position,
                taskbar.set_dock_position,
            ),
        )
        size_box = QWidget(card)
        sl = QHBoxLayout(size_box)
        sl.setContentsMargins(0, 0, 0, 0)
        size = QSlider(Qt.Orientation.Horizontal, size_box)
        size.setRange(*taskbar.DOCK_ICON_RANGE)
        size.setValue(d.icon_size)
        size.setFixedWidth(240)
        size.setAccessibleName(tr("Icon size"))
        value = QLabel(f"{d.icon_size} px", size_box)
        value.setMinimumWidth(56)
        size.valueChanged.connect(lambda v: value.setText(f"{v} px"))
        size.sliderReleased.connect(lambda: taskbar.set_dock_icon_size(size.value()))
        sl.addWidget(size)
        sl.addWidget(value)
        _row(card, tr("Icon size"), "", size_box)
        vis = QComboBox(card)
        for key, label in (
            ("always", tr("Always visible")),
            ("intellihide", tr("Hide when a window covers it")),
            ("autohide", tr("Always hidden, show at the screen edge")),
        ):
            vis.addItem(label, key)
        vis.setCurrentIndex(max(0, vis.findData(d.visibility)))
        vis.currentIndexChanged.connect(lambda: taskbar.set_dock_visibility(vis.currentData()))
        _row(card, tr("Visibility"), "", vis)
        for attr, title, desc in (
            ("trash", tr("Trash in the dock"), ""),
            ("mounts", tr("USB drives and disks in the dock"), tr("Easy to open and eject.")),
            ("dots", tr("Dot under open programs"), ""),
            ("counter", tr("Show counts on app icons"), ""),
            (
                "apps_at_top",
                tr("All programs button at the start"),
                tr("Like Launchpad: the first icon opens the list of all programs."),
            ),
            ("all_monitors", tr("Dock on every screen"), ""),
        ):
            self._check(
                card,
                title,
                desc,
                getattr(d, attr),
                lambda on, a=attr: taskbar.set_dock_option(a, on),
            )
        self._body.addWidget(card)

    @staticmethod
    def _check(card: Card, title: str, desc: str, checked: bool, slot) -> None:  # noqa: ANN001
        cb = QCheckBox(card)
        cb.setChecked(checked)
        cb.setAccessibleName(title)
        cb.toggled.connect(slot)
        _row(card, title, desc, cb)

    def _build_behaviour(self, s: dict) -> None:
        """Windows 10 / 11 gibi hizalama, pencere birleştirme, ekranlar, sayı ve ilerleme."""
        self._section(tr("Behaviour"))
        card = Card()
        align = taskbar.alignment(s["elements"])
        _row(
            card,
            tr("Icon alignment"),
            tr("Start button and app icons together in the middle or on the left."),
            _segmented(
                card,
                [
                    ("center", tr("Like Windows 11 (centre)")),
                    ("left", tr("Like Windows 10 (left)")),
                ],
                align,
                taskbar.set_alignment,
            ),
        )
        b: taskbar.Behaviour = s["behaviour"]
        combine = QComboBox(card)
        combine.addItem(tr("Always combine, hide names"), True)
        combine.addItem(tr("Never combine, show names"), False)
        combine.setCurrentIndex(0 if b.combine else 1)
        combine.currentIndexChanged.connect(
            lambda: taskbar.set_behaviour("combine", combine.currentData())
        )
        _row(
            card,
            tr("Combine taskbar buttons"),
            tr("Windows of the same program in one button, or each window with its title."),
            combine,
        )
        for attr, title, desc in (
            ("all_monitors", tr("Show the taskbar on all screens"), ""),
            (
                "badge_count",
                tr("Show counts on app icons"),
                tr("For example the number of unread e-mails."),
            ),
            (
                "progress_bar",
                tr("Show progress on app icons"),
                tr("For example a download or file copy."),
            ),
        ):
            self._check(
                card, title, desc, getattr(b, attr), lambda on, a=attr: taskbar.set_behaviour(a, on)
            )
        self._body.addWidget(card)

    def _build_items(self, s: dict) -> None:
        """Çubukta hangi öğeler görünsün."""
        self._section(tr("Items on the taskbar"))
        card = Card()
        visible = {e["element"]: e["visible"] for e in s["elements"]}
        for name, title, desc in (
            ("showAppsButton", tr("Start button"), tr("Opens the list of all programs.")),
            ("activitiesButton", tr("Activities"), tr("Shows all open windows and desktops.")),
            ("dateMenu", tr("Clock and calendar"), ""),
            ("systemMenu", tr("System icons"), tr("Network, sound, battery and power.")),
            (
                "desktopButton",
                tr("Show desktop corner"),
                tr("A thin button at the end; click it to minimise all windows."),
            ),
        ):
            self._check(
                card,
                title,
                desc,
                visible.get(name, True),
                lambda on, n=name: taskbar.set_element_visible(n, on),
            )
        self._check(
            card,
            tr("Peek at the desktop"),
            tr("Pointing at the show desktop corner shows the desktop for a moment."),
            s["behaviour"].desktop_hover,
            lambda on: taskbar.set_behaviour("desktop_hover", on),
        )
        self._body.addWidget(card)

    def _build_clock(self, s: dict) -> None:
        self._section(tr("Clock and date"))
        card = Card()
        c: taskbar.Clock = s["clock"]
        for attr, title in (
            ("date", tr("Show the date")),
            ("weekday", tr("Show the day of the week")),
            ("seconds", tr("Show seconds")),
            ("format24", tr("24-hour clock")),
        ):
            self._check(
                card, title, "", getattr(c, attr), lambda on, a=attr: taskbar.set_clock(a, on)
            )
        if s["dtp"] and s["preset"] == "windows" and s["elements"]:
            _row(
                card,
                tr("Clock position"),
                "",
                _segmented(
                    card,
                    [("right", tr("Right")), ("center", tr("Centre"))],
                    "center" if taskbar.clock_centered(s["elements"]) else "right",
                    lambda k: taskbar.set_clock_centered(k == "center"),
                ),
            )
        self._body.addWidget(card)

    def _build_pinned(self, s: dict) -> None:
        """Görev çubuğuna sabitlenmiş programlar: sırala, çıkar, ekle."""
        from linwas.backend import app_folders
        from linwas.ui.app_folder_popup import AppPicker, app_icon

        self._section(tr("Pinned programs"))
        card = Card()
        pinned: list[str] = list(s["pinned"])
        if not pinned:
            empty = QLabel(tr("No programs are pinned."), card)
            empty.setObjectName("Secondary")
            card.layout.addWidget(empty)
        for i, ref in enumerate(pinned):
            entry = app_folders.app_entry(ref)
            row = QHBoxLayout()
            icon = QLabel(card)
            icon.setPixmap(app_icon(entry).pixmap(28, 28))
            row.addWidget(icon)
            name = QLabel(entry.name if entry else ref, card)
            row.addWidget(name, 1)
            for text, tip, delta, enabled in (
                ("↑", tr("Move left"), -1, i > 0),
                ("↓", tr("Move right"), 1, i < len(pinned) - 1),
            ):
                btn = QPushButton(text, card)
                btn.setToolTip(tip)
                btn.setAccessibleName(tip)
                btn.setEnabled(enabled)
                btn.clicked.connect(lambda _=False, i=i, d=delta: self._move_pinned(pinned, i, d))
                row.addWidget(btn)
            remove = QPushButton(tr("Unpin"), card)
            remove.clicked.connect(
                lambda _=False, r=ref: self._save_pinned([p for p in pinned if p != r])
            )
            row.addWidget(remove)
            card.layout.addLayout(row)
        add = QPushButton(tr("Pin programs…"), card)

        def pick() -> None:
            picker = AppPicker(set(pinned), self)
            picker.setWindowTitle(tr("Pin programs"))
            if picker.exec():
                self._save_pinned(pinned + picker.selected())

        add.clicked.connect(pick)
        actions = QHBoxLayout()
        actions.addWidget(add)
        actions.addStretch(1)
        card.layout.addLayout(actions)
        self._body.addWidget(card)

    def _move_pinned(self, pinned: list[str], i: int, delta: int) -> None:
        j = i + delta
        if 0 <= j < len(pinned):
            pinned = list(pinned)
            pinned[i], pinned[j] = pinned[j], pinned[i]
            self._save_pinned(pinned)

    def _save_pinned(self, apps: list[str]) -> None:
        taskbar.save_pinned(apps)
        self._refresh()

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
