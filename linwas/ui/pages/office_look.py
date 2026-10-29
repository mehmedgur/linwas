# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Office görünümü sayfası: LibreOffice'i Microsoft Office benzeri yapan paketi kurar ve
her kullanıcının kendi ayarlarını değiştirir (bkz. backend/office_look).

Kurma ve kaldırma kuyruk üzerinden root işlemiyle (`package.install`/`package.remove`);
ayarlar kullanıcı yetkisiyle `linwas-office-look` aracıyla yazılır.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import office_look
from linwas.core.tasks import Task, TaskStep
from linwas.ui.pages.base import BasePage
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.option_tile import OptionTile


def tr(text: str) -> str:
    return QCoreApplication.translate("OfficeLookPage", text)


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


class OfficeLookPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workers: list[_Worker] = []
        self._status = office_look.OfficeLookStatus()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(36, 28, 36, 28)
        self.body.setSpacing(12)
        h = QLabel(tr("Office Look"), content)
        h.setObjectName("H1")
        self.body.addWidget(h)
        hint = QLabel(
            tr(
                "Makes LibreOffice look and work like Microsoft Office: a simple ribbon, a File "
                "menu inside the window, Word/Excel/PowerPoint formats and automatic saving. "
                "Your settings here only affect you."
            ),
            content,
        )
        hint.setObjectName("Secondary")
        hint.setWordWrap(True)
        self.body.addWidget(hint)

        self._build_status_card()
        self._build_settings_card()
        self._build_off_card()
        self.body.addStretch(1)

        scroll.setWidget(content)
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.addWidget(scroll)
        self.on_tasks_finished()

    # --- Kartlar ---

    def _card(self, title: str) -> Card:
        card = Card(self)
        h = QLabel(title, card)
        h.setObjectName("H2")
        card.layout.addWidget(h)
        self.body.addWidget(card)
        return card

    @staticmethod
    def _note(card: Card, text: str = "") -> QLabel:
        lbl = QLabel(text, card)
        lbl.setWordWrap(True)
        lbl.setObjectName("Secondary")
        card.layout.addWidget(lbl)
        return lbl

    def _build_status_card(self) -> None:
        card = self._card(tr("LibreOffice and the Office look"))
        self._lo_label = self._note(card, tr("Checking…"))
        self._look_label = self._note(card)
        row = QHBoxLayout()
        self._install_btn = QPushButton(tr("Install Office look"), card)
        self._install_btn.setProperty("primary", True)
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._install)
        row.addWidget(self._install_btn)
        row.addStretch(1)
        card.layout.addLayout(row)

    @staticmethod
    def _section(card: Card, title: str) -> None:
        lbl = QLabel(title, card)
        lbl.setObjectName("SectionTitle")
        card.layout.addSpacing(6)
        card.layout.addWidget(lbl)

    def _radios(self, card: Card, title: str, choices: list[tuple[str, str, str]]) -> QButtonGroup:
        """Seçenekler yan yana seçim kartları; (değer, başlık, açıklama)."""
        self._section(card, title)
        group = QButtonGroup(card)
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (_, heading, description) in enumerate(choices):
            tile = OptionTile(heading, description, parent=card)
            group.addButton(tile.button, i)
            grid.addWidget(tile, 0, i)
            grid.setColumnStretch(i, 1)
        card.layout.addLayout(grid)
        group.setProperty("values", [value for value, _, _ in choices])
        return group

    def _build_settings_card(self) -> None:
        card = self._settings_card = self._card(tr("Your settings"))
        self._note(card, tr("Close LibreOffice before applying; it reads these when it starts."))
        self._ribbon = self._radios(
            card,
            tr("Ribbon"),
            [
                ("simple", tr("Simple ribbon"), tr("Few tabs with named groups")),
                ("full", tr("Full ribbon"), tr("Every LibreOffice tool in tabs")),
                ("classic", tr("Classic"), tr("Menus and toolbars, no ribbon")),
            ],
        )

        self._section(card, tr("Working"))
        menu_tile = OptionTile(
            tr("File menu inside the window"),
            tr("Save, open and print without separate dialogs"),
            checkbox=True,
            parent=card,
        )
        self._file_menu = menu_tile.button
        card.layout.addWidget(menu_tile)

        names_tile = OptionTile(
            tr("Show the Office name next to each app"),
            tr(
                "LibreOffice Writer (Word), Calc (Excel) and Impress (PowerPoint) in the app menu, "
                "search and window title"
            ),
            checkbox=True,
            parent=card,
        )
        self._office_names = names_tile.button
        card.layout.addWidget(names_tile)

        # Otomatik kaydetme: başlık solda, seçim kutusu sağda (ayar satırı)
        autosave_tile = QFrame(card)
        autosave_tile.setObjectName("OptionTile")
        row = QHBoxLayout(autosave_tile)
        row.setContentsMargins(14, 10, 14, 10)
        title = QLabel(tr("Save automatically"), autosave_tile)
        title.setObjectName("OptionTitle")
        row.addWidget(title, 1)
        self._autosave = QComboBox(autosave_tile)
        self._autosave.setAccessibleName(tr("Save automatically"))
        for minutes in office_look.AUTOSAVE_CHOICES:
            self._autosave.addItem(
                tr("Off") if minutes == 0 else tr("Every {n} minutes").format(n=minutes), minutes
            )
        row.addWidget(self._autosave)
        card.layout.addWidget(autosave_tile)

        self._save_format = self._radios(
            card,
            tr("Save new documents as"),
            [
                ("ooxml", tr("Word, Excel and PowerPoint"), ".docx, .xlsx, .pptx"),
                ("odf", tr("LibreOffice formats"), ".odt, .ods, .odp"),
            ],
        )
        self._font = self._radios(
            card,
            tr("Default font in new documents"),
            [
                ("carlito", "Carlito", tr("Same size as Calibri, like Word")),
                ("liberation", "Liberation Serif", tr("LibreOffice default")),
            ],
        )
        card.layout.addSpacing(6)
        row = QHBoxLayout()
        self._apply_btn = QPushButton(tr("Apply"), card)
        self._apply_btn.setProperty("primary", True)
        self._apply_btn.clicked.connect(self._apply)
        row.addWidget(self._apply_btn)
        self._apply_status = QLabel("", card)
        self._apply_status.setWordWrap(True)
        row.addWidget(self._apply_status, 1)
        card.layout.addLayout(row)

    def _build_off_card(self) -> None:
        card = self._off_card = self._card(tr("Turn off"))
        self._off_note = self._note(card)
        row = QHBoxLayout()
        self._toggle_btn = QPushButton("", card)
        self._toggle_btn.clicked.connect(self._toggle_for_me)
        row.addWidget(self._toggle_btn)
        self._remove_btn = QPushButton(tr("Remove for all users"), card)
        self._remove_btn.clicked.connect(self._remove)
        row.addWidget(self._remove_btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        self._off_status = self._note(card)

    # --- Durum ---

    def _run_bg(self, fn, slot) -> None:  # noqa: ANN001
        worker = _Worker(fn)
        worker.done.connect(slot)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def on_tasks_finished(self) -> None:
        self._run_bg(office_look.status, self._on_status)

    def _on_status(self, status: office_look.OfficeLookStatus | None) -> None:
        status = status or office_look.OfficeLookStatus()
        self._status = status
        self._lo_label.setText(
            tr("LibreOffice {version} is installed.").format(
                version=office_look.short_version(status.libreoffice_version)
            )
            if status.libreoffice_installed
            else tr("LibreOffice is not installed. It is installed together with the Office look.")
        )
        if status.installed:
            apps = ", ".join(status.simple_ribbon_apps) or tr("none")
            self._look_label.setText(
                tr("✓ Office look {version} is installed. Simple ribbon: {apps}.").format(
                    version=office_look.short_version(status.package_version), apps=apps
                )
            )
        else:
            self._look_label.setText(tr("The Office look is not installed."))
        self._install_btn.setVisible(not status.installed)
        self._install_btn.setEnabled(not status.installed)
        self._install_btn.setText(
            tr("Install Office look")
            if status.libreoffice_installed
            else tr("Install LibreOffice and the Office look")
        )
        self._settings_card.setVisible(status.installed and not status.disabled)
        self._off_card.setVisible(status.installed)
        self._off_note.setText(
            tr("The Office look is turned off for you; LibreOffice uses its original settings.")
            if status.disabled
            else tr(
                "Turning it off for you needs no password and does not affect other users. "
                "Removing it for everyone needs an administrator password."
            )
        )
        self._toggle_btn.setText(
            tr("Turn back on for me") if status.disabled else tr("Turn off for me")
        )
        self._show_settings(status.settings)

    def _show_settings(self, settings: office_look.Settings) -> None:
        for group, value in (
            (self._ribbon, settings.ribbon),
            (self._save_format, settings.save_format),
            (self._font, settings.font),
        ):
            values = group.property("values")
            group.button(values.index(value)).setChecked(True)
        self._file_menu.setChecked(settings.file_menu)
        self._office_names.setChecked(settings.office_names)
        self._autosave.setCurrentIndex(
            office_look.AUTOSAVE_CHOICES.index(settings.autosave_minutes)
        )
        self._ribbon.button(0).setEnabled(bool(self._status.simple_ribbon_apps))

    def _chosen(self) -> office_look.Settings:
        def value(group: QButtonGroup) -> str:
            return group.property("values")[group.checkedId()]

        return office_look.Settings(
            ribbon=value(self._ribbon),
            file_menu=self._file_menu.isChecked(),
            office_names=self._office_names.isChecked(),
            autosave_minutes=self._autosave.currentData(),
            save_format=value(self._save_format),
            font=value(self._font),
        )

    # --- İşlemler ---

    def _install(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Install the Office look for LibreOffice"),
                steps=[
                    TaskStep(op_id=op, params=params)
                    for op, params in office_look.install_steps(self._status)
                ],
            )
        )

    def _remove(self) -> None:
        self.task_run_now.emit(
            Task(
                label=tr("Remove the Office look"),
                steps=[TaskStep(op_id="package.remove", params={"name": office_look.PACKAGE})],
            )
        )

    def _show_result(self, label: QLabel, result: office_look.Result | None, done: str) -> None:
        if result is None or not result.ok:
            label.setText(
                tr("Close all LibreOffice windows first, then try again.")
                if result is not None and result.libreoffice_running
                else tr("Could not apply: {error}").format(error=result.message if result else "")
            )
            return
        label.setText(done)
        self.on_tasks_finished()

    def _apply(self) -> None:
        old, new = self._status.settings, self._chosen()
        self._apply_btn.setEnabled(False)
        self._apply_status.setText(tr("Applying…"))

        def finished(result: office_look.Result | None) -> None:
            self._apply_btn.setEnabled(True)
            self._show_result(
                self._apply_status, result, tr("✓ Applied. Open LibreOffice to see the change.")
            )

        self._run_bg(lambda: office_look.apply_settings(old, new), finished)

    def _toggle_for_me(self) -> None:
        fn = office_look.enable_for_me if self._status.disabled else office_look.disable_for_me
        self._toggle_btn.setEnabled(False)

        def finished(result: office_look.Result | None) -> None:
            self._toggle_btn.setEnabled(True)
            self._show_result(self._off_status, result, tr("✓ Done."))

        self._run_bg(fn, finished)
