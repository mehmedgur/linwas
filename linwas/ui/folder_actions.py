# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Masaüstü sağ tık eylemleri (`linwas --folder-action <eylem> <dosyalar>`).

group: seçilen programlardan yeni klasör (ad sorulur) · add: var olan klasöre ekle ·
ungroup: klasörü çöz (programlar masaüstüne döner). Menü kaydı: backend/folder_menu.py.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from linwas.backend import app_folders, folder_menu
from linwas.backend.folder_menu import MenuLabel
from linwas.ui.app_folder_popup import save_and_refresh


def tr(text: str) -> str:
    return QCoreApplication.translate("FolderActions", text)


def menu_labels() -> dict[str, MenuLabel]:
    return {
        "group": MenuLabel(
            tr("Group in a folder (Linwas)"),
            tr("Puts the selected programs into a new program folder"),
        ),
        "add": MenuLabel(
            tr("Add to a folder (Linwas)"),
            tr("Adds the selected programs to a program folder"),
        ),
        "ungroup": MenuLabel(
            tr("Ungroup folder (Linwas)"),
            tr("Removes the folder; its programs return to the desktop"),
        ),
    }


def install_menu_actions() -> bool:
    """Sağ tık eylemlerini geçerli dilde yazar (Linwas açılışında ve klasör sayfasında)."""
    return folder_menu.install(menu_labels())


def _not_programs() -> None:
    QMessageBox.information(
        None,
        tr("Program folder"),
        tr("Select program shortcuts on the desktop to put them in a folder."),
    )


def _group(paths: list[str]) -> int:
    name, ok = QInputDialog.getText(None, tr("New folder"), tr("Folder name:"), text=tr("Folder"))
    name = " ".join(name.split())
    if not ok or not name:
        return 0
    folder = app_folders.group_paths(name[: app_folders.MAX_NAME_LEN], paths)
    if folder is None:
        _not_programs()
        return 1
    save_and_refresh(folder)
    return 0


def _add(paths: list[str]) -> int:
    folders = app_folders.load_folders()
    if not folders:
        QMessageBox.information(
            None,
            tr("Program folder"),
            tr('There are no folders yet. Use "Group in a folder" to create one.'),
        )
        return 0
    names = [f.name for f in folders]
    name, ok = QInputDialog.getItem(
        None, tr("Add to a folder"), tr("Folder:"), names, 0, editable=False
    )
    if not ok:
        return 0
    folder = folders[names.index(name)]
    if not app_folders.add_dropped(folder, paths):
        _not_programs()
        return 1
    save_and_refresh(folder)
    return 0


def _ungroup(paths: list[str]) -> int:
    folders = [f for f in (app_folders.folder_of_launcher(p) for p in paths) if f]
    if not folders:
        QMessageBox.information(
            None, tr("Program folder"), tr("Select a Linwas program folder to ungroup it.")
        )
        return 1
    for folder in folders:
        answer = QMessageBox.question(
            None,
            tr("Ungroup folder"),
            tr('Ungroup "{name}"? Its programs return to the desktop.').format(name=folder.name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            app_folders.delete_folder(folder.id)
    return 0


def run(action: str, paths: list[str]) -> int:
    """`linwas --folder-action` giriş noktası; ana pencereden bağımsız, kısa süreli süreç."""
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Linwas")
    app.setDesktopFileName("linwas")
    from linwas.core import app_settings
    from linwas.translations import install_translator

    install_translator(app, app_settings.load().language)
    handler = {"group": _group, "add": _add, "ungroup": _ungroup}.get(action)
    if handler is None:
        return 2
    return handler(paths)
