# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Oturum açılınca Linwas'ı arka planda başlatma (XDG Autostart, kullanıcı düzeyinde).

~/.config/autostart/linwas.desktop dosyası yazılır/silinir; Exec satırı `--background` ile
başlatır (pencere açılmaz, yalnızca bildirimler). Kurulu pakette `linwas` komutu kullanılır;
kaynak koddan çalışırken o anki Python yorumlayıcısı ve depo klasörü.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

FILE_NAME = "linwas.desktop"


def autostart_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / FILE_NAME


def _quote(arg: str) -> str:
    if not any(c in arg for c in " \t\"'\\`$"):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def desktop_entry() -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Linwas",
        "Comment=Linwas runs in the background and shows notifications",
        "Icon=linwas",
        "X-GNOME-Autostart-enabled=true",
        "NoDisplay=true",
    ]
    if shutil.which("linwas"):
        lines.append("Exec=linwas --background")
    else:
        # Kaynak koddan: python -m linwas, depo kökünden
        root = Path(__file__).resolve().parent.parent.parent
        lines.append(f"Exec={_quote(sys.executable)} -m linwas --background")
        lines.append(f"Path={root}")
    return "\n".join(lines) + "\n"


def set_enabled(enabled: bool) -> bool:
    """Dosyayı ayara göre yazar ya da siler; başarılıysa True."""
    path = autostart_path()
    try:
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desktop_entry(), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def is_enabled() -> bool:
    return autostart_path().is_file()
