# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Uygulama menüsünde LibreOffice adlarının yanında Office karşılığı: "LibreOffice Writer (Word)".

Sistemdeki .desktop dosyasına dokunulmaz; kullanıcının ~/.local/share/applications klasörüne aynı
adla bir kopya yazılır (masaüstü ortamı kullanıcı kopyasını önce okur). Kopyada yalnız
[Desktop Entry] bölümündeki adlara "(Word)" eklenir, arama sözcüklerine "Word" girer; işaret satırı
sayesinde yalnız Linwas'ın yazdığı kopyalar güncellenir ya da silinir (kullanıcının elle düzenlediği
kopyaya dokunulmaz). LibreOffice güncellenince sistem dosyası yeni olur; `refresh` kopyayı yeniler.

Yalnız standart kütüphane (ayar aracı ve paket betikleri de kullanır).
"""

from __future__ import annotations

import os
import shutil
import subprocess

SYSTEM_DIR = "/usr/share/applications"
MARKER = "X-Linwas-OfficeName=true"
# .desktop dosyası → Office karşılığı
OFFICE_NAMES = {
    "libreoffice-writer.desktop": "Word",
    "libreoffice-calc.desktop": "Excel",
    "libreoffice-impress.desktop": "PowerPoint",
}
# Pencere başlığı için (eklenti): LibreOffice'in uygulama adı → Office karşılığı
TITLE_NAMES = {
    "LibreOffice Writer": "Word",
    "LibreOffice Calc": "Excel",
    "LibreOffice Impress": "PowerPoint",
}


def user_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    return os.path.join(base, "applications")


def renamed(text: str, office: str) -> str:
    """[Desktop Entry] bölümündeki Name ve Keywords satırlarına Office karşılığını ekler."""
    out: list[str] = []
    section = ""
    suffix = f" ({office})"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            out.append(line)
            if section == "[Desktop Entry]":
                out.append(MARKER)
            continue
        if section == "[Desktop Entry]" and "=" in line:
            key, value = line.split("=", 1)
            base = key.split("[", 1)[0]
            if base == "Name" and not value.endswith(suffix):
                line = f"{key}={value}{suffix}"
            elif base == "Keywords" and office not in value.split(";"):
                line = (
                    f"{key}={value if value.endswith(';') or not value else value + ';'}{office};"
                )
            elif line.strip() == MARKER:
                continue
        out.append(line)
    return "\n".join(out) + "\n"


def _ours(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            return any(line.strip() == MARKER for line in f)
    except OSError:
        return False


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".linwas-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def apply(on: bool) -> list[str]:
    """Kopyaları yazar (on) ya da Linwas'ın yazdıklarını siler (off). Değişen dosyaları döner."""
    changed = []
    for name, office in OFFICE_NAMES.items():
        system = os.path.join(SYSTEM_DIR, name)
        user = os.path.join(user_dir(), name)
        exists = os.path.exists(user)
        if exists and not _ours(user):
            continue  # kullanıcının kendi kopyası
        if not on or not os.path.isfile(system):
            if exists:
                os.remove(user)
                changed.append(name)
            continue
        try:
            with open(system, encoding="utf-8") as f:
                text = renamed(f.read(), office)
            current = ""
            if exists:
                with open(user, encoding="utf-8") as f:
                    current = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if text != current:
            _write(user, text)
            changed.append(name)
    if changed and shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", user_dir()],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return changed


def window_title_app(app: str) -> str:
    """Pencere başlığındaki uygulama adı: "LibreOffice Writer" → "LibreOffice Writer (Word)"."""
    office = TITLE_NAMES.get(app)
    return f"{app} ({office})" if office and not app.endswith(f"({office})") else app
