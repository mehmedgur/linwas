# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Eklenti eylemlerini (core/plugins › PluginAction) düğmeye bağlanacak işlevlere çevirir.

Görev adımları burada da izin listesinden geçirilir; geçersiz adımlı eylem düğme olarak
gösterilmez (son karar yine root helper'da).
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from linwas.backend.desktop import detect_desktop
from linwas.backend.settings_launcher import command_for, open_settings
from linwas.core.plugins import PluginAction
from linwas.core.tasks import Task, TaskStep
from linwas.core.whitelist import ValidationError, validate
from linwas.ui.pages.base import BasePage


def action_callable(page: BasePage, action: PluginAction) -> Callable[[], None] | None:
    """Eylemi çalıştıran işlev; bu sistemde yapılamıyorsa None."""
    if action.kind == "page" and action.target:
        return lambda: page.page_requested.emit(action.target)
    if action.kind == "settings":
        desktop = detect_desktop(os.environ).value
        if command_for(action.target, desktop) is None:
            return None
        return lambda: open_settings(action.target, desktop)
    if action.kind == "url" and action.target.startswith("https://"):
        return lambda: QDesktopServices.openUrl(QUrl(action.target))
    if action.kind == "task" and action.steps:
        try:
            checked = [(op, validate(op, params)) for op, params in action.steps]
        except ValidationError:
            return None
        # Her tıklamada yeni görev (adımlar çalışırken durum tutar)
        return lambda: page.task_run_now.emit(
            Task(
                label=action.label,
                steps=[TaskStep(op_id=op, params=dict(params)) for op, params in checked],
            )
        )
    return None
