# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Ayrıntılı günlük (Gelişmiş › Günlük): açıksa ~/.local/state/linwas/linwas.log dosyasına yazılır.

Dosya 1 MB'ı geçince döndürülür (3 eski kopya). Kapalıyken yalnızca uyarılar konsola gider.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from linwas.core.user_data import log_dir

LOG_FILE_NAME = "linwas.log"
_handler: RotatingFileHandler | None = None


def setup(debug: bool) -> None:
    global _handler
    root = logging.getLogger("linwas")
    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
        _handler = None
    root.setLevel(logging.DEBUG if debug else logging.WARNING)
    if not debug:
        return
    try:
        log_dir().mkdir(parents=True, exist_ok=True)
        _handler = RotatingFileHandler(
            log_dir() / LOG_FILE_NAME, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(_handler)
