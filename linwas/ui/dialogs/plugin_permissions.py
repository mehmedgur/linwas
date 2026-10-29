# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kodsuz eklentinin izin ekranı: kurmadan ya da güncellemeden önce ne yapacağı tek tek yazılır."""

from __future__ import annotations

import html
import json

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from linwas.core.plugins import SOURCE_DEVELOPER
from linwas.core.plugins.declarative import Permissions


def tr(text: str) -> str:
    return QCoreApplication.translate("PluginPermissionsDialog", text)


def task_text(op: str, params: dict[str, str]) -> str:
    """Eklentilere açık işlemlerin anlaşılır adı (core/plugins/declarative.PLUGIN_OPERATIONS)."""
    texts = {
        "package.install": tr("Install the program {name}"),
        "flatpak.install": tr("Install the Flatpak app {app_id}"),
        "package.update_index": tr("Refresh the list of programs"),
        "package.update_all": tr("Install all updates"),
        "package.fix_broken": tr("Repair interrupted installations"),
        "package.autoremove": tr("Remove old kernels and unneeded packages"),
        "flatpak.update_all": tr("Update all Flatpak apps"),
        "service.restart": tr("Restart the system service {name}"),
        "service.enable": tr("Turn on the system service {name}"),
        "apt.clean": tr("Delete downloaded package files"),
        "journal.vacuum": tr("Shrink the system logs"),
        "driver.rebuild_modules": tr("Rebuild driver modules for the running kernel"),
        "firmware.refresh": tr("Refresh the list of firmware updates"),
        "snapshot.timeshift_create": tr("Create a system backup (Timeshift)"),
    }
    text = texts.get(op, op)
    try:
        return text.format(**params)
    except (KeyError, IndexError):
        return text


def read_text(kind: str, target: str) -> str:
    return {
        "command_exists": tr("Whether the program {t} exists"),
        "file_exists": tr("Whether the file {t} exists"),
        "service_active": tr("Whether the system service {t} is running"),
        "package_installed": tr("Whether the package {t} is installed"),
        "kernel_module_loaded": tr("Whether the kernel module {t} is loaded"),
        "disk_free": tr("Free disk space on {t}"),
    }.get(kind, kind).format(t=target)


def _risk_text(risk: str) -> str:
    return {"low": tr("low risk"), "medium": tr("medium risk"), "high": tr("high risk")}.get(
        risk, risk
    )


class PluginPermissionsDialog(QDialog):
    """Kabul edilirse `exec()` Accepted döner."""

    def __init__(
        self,
        name: str,
        version: str,
        publisher: str,
        source: str,
        perms: Permissions,
        update: bool = False,
        new_keys: set[str] | None = None,
        parent: QWidget | None = None,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 460)
        if read_only:
            title = tr("What {name} can do").format(name=name)
        elif update:
            title = tr("Update {name}?").format(name=name)
        else:
            title = tr("Install {name}?").format(name=name)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        head = QLabel(title, self)
        head.setObjectName("H2")
        head.setWordWrap(True)
        layout.addWidget(head)
        sub = QLabel(
            tr("Version {version} · from {publisher}").format(version=version, publisher=publisher),
            self,
        )
        sub.setObjectName("Secondary")
        layout.addWidget(sub)

        if source == SOURCE_DEVELOPER:
            warn = QLabel(
                tr(
                    "This plugin is not from the Linwas catalog and was not checked by Linwas. "
                    "Install it only if you trust where it comes from."
                ),
                self,
            )
            warn.setObjectName("Warning")
            warn.setWordWrap(True)
            layout.addWidget(warn)
        if update and new_keys:
            note = QLabel(tr("This update asks for new permissions (marked ★)."), self)
            note.setObjectName("Warning")
            note.setWordWrap(True)
            layout.addWidget(note)

        body = QWidget()
        box = QVBoxLayout(body)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        new_keys = new_keys or set()

        def mark(key: str) -> str:
            return "★ " if key in new_keys else "• "

        sections: list[tuple[str, list[str]]] = [
            (
                tr("Can run these system tasks (you confirm each time, with your password):"),
                [
                    mark(f"task:{op}:{json.dumps(p, sort_keys=True)}")
                    + f"{task_text(op, p)} — {_risk_text(risk)}"
                    for op, risk, p in perms.tasks
                ],
            ),
            (
                tr("Checks (reads only, changes nothing):"),
                [mark(f"read:{k}:{t}") + read_text(k, t) for k, t in perms.reads],
            ),
            (
                tr("Opens these Linwas pages:"),
                [mark(f"page:{p}") + p for p in perms.pages],
            ),
            (
                tr("Opens these system settings:"),
                [mark(f"settings:{s}") + s for s in perms.settings],
            ),
            (
                tr("Opens these web pages in your browser:"),
                [mark(f"url:{u}") + u for u in perms.urls],
            ),
        ]
        shown = False
        for heading, lines in sections:
            if not lines:
                continue
            shown = True
            h = QLabel(f"<b>{html.escape(heading)}</b>", body)
            h.setWordWrap(True)
            box.addWidget(h)
            for line in lines:
                lbl = QLabel(line, body)
                lbl.setWordWrap(True)
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                box.addWidget(lbl)
        if not shown:
            box.addWidget(QLabel(tr("It only adds help texts."), body))
        box.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        foot = QLabel(
            tr(
                "Plugins cannot run their own code. System tasks always go through the Linwas "
                "safety list and ask for your confirmation."
            ),
            self,
        )
        foot.setObjectName("Secondary")
        foot.setWordWrap(True)
        layout.addWidget(foot)

        if read_only:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
            buttons.rejected.connect(self.reject)
        else:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
            )
            ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
            ok.setText(tr("Update") if update else tr("Install"))
            ok.setProperty("primary", True)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
