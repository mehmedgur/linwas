# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Masaüstünde sağ tık eylemleri: program klasörü oluşturma ve düzenleme.

- XFCE (xfdesktop): Thunar "Özel eylemler" (`~/.config/Thunar/uca.xml`); xfdesktop thunarx
  eklentilerini (thunar-uca) yüklediği için masaüstündeki dosyanın sağ tık menüsünde görünür.
  Linwas'ın eylemleri `unique-id`'si "linwas-" ile başlayanlardır; kullanıcının kendi eylemlerine
  dokunulmaz.
- GNOME (Desktop Icons NG) ve Nautilus: "Betikler" alt menüsü (`~/.local/share/nautilus/scripts`);
  seçili dosyalar betiğe argüman olarak verilir (DING fileItemMenu.js › _onScriptClicked).

Eylemler `linwas --folder-action <eylem> <dosyalar>` çalıştırır (ui/folder_actions.py).
"""

from __future__ import annotations

import os
import shlex
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from linwas.backend.app_folders import LAUNCHER_PREFIX, exec_command

ACTIONS = ("group", "add", "ungroup")
UCA_PREFIX = "linwas-folder-"
SCRIPT_MARK = "# linwas-folder-action"


@dataclass(frozen=True)
class MenuLabel:
    name: str
    description: str


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def uca_file() -> Path:
    return _config_home() / "Thunar" / "uca.xml"


def scripts_dir() -> Path:
    return _data_home() / "nautilus" / "scripts"


def command(action: str) -> list[str]:
    return [*exec_command(), "--folder-action", action]


# --- XFCE / Thunar özel eylemleri ---

_ICONS = {"group": "folder-new", "add": "list-add", "ungroup": "edit-undo"}
_PATTERNS = {"group": "*.desktop", "add": "*.desktop", "ungroup": f"{LAUNCHER_PREFIX}*.desktop"}


def _uca_action(action: str, label: MenuLabel) -> ET.Element:
    el = ET.Element("action")
    fields = (
        ("icon", _ICONS[action]),
        ("name", label.name),
        ("submenu", ""),
        ("unique-id", UCA_PREFIX + action),
        # %F: seçili dosyaların tam yolları (Thunar UCA)
        ("command", " ".join(shlex.quote(a) for a in command(action)) + " %F"),
        ("description", label.description),
        ("range", ""),
        ("patterns", _PATTERNS[action]),
    )
    for tag, text in fields:
        ET.SubElement(el, tag).text = text
    ET.SubElement(el, "other-files")  # .desktop dosyaları "diğer dosyalar" türünde
    return el


def uca_text(current: str, labels: dict[str, MenuLabel]) -> str | None:
    """uca.xml'in yeni içeriği; okunamayan (bozuk) dosyada None (dosyaya dokunulmaz)."""
    if current.strip():
        try:
            root = ET.fromstring(current)
        except ET.ParseError:
            return None
        if root.tag != "actions":
            return None
    else:
        root = ET.Element("actions")
    for el in list(root):
        uid = el.findtext("unique-id") or ""
        if el.tag == "action" and uid.startswith(UCA_PREFIX):
            root.remove(el)
    for action in ACTIONS:
        if action in labels:
            root.append(_uca_action(action, labels[action]))
    ET.indent(root, space="\t")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, "unicode") + "\n"


def _install_uca(labels: dict[str, MenuLabel]) -> bool:
    path = uca_file()
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    except (OSError, UnicodeDecodeError):
        return False
    text = uca_text(current, labels)
    if text is None:
        return False
    if text == current:
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".xml.linwas-tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return False
    return True


# --- GNOME (DING) / Nautilus betikleri ---


def script_text(action: str) -> str:
    cmd = " ".join(shlex.quote(a) for a in command(action))
    return f'#!/bin/sh\n{SCRIPT_MARK} {action}\nexec {cmd} "$@"\n'


def _install_scripts(labels: dict[str, MenuLabel]) -> bool:
    folder = scripts_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        # Eski adlı (ör. dil değişmeden önceki) Linwas betiklerini kaldır
        wanted = {f"{labels[a].name}": a for a in ACTIONS if a in labels}
        for old in folder.iterdir():
            if old.is_file() and old.name not in wanted and _is_ours(old):
                old.unlink()
        for name, action in wanted.items():
            target = folder / name.replace("/", "-")
            text = script_text(action)
            if not (target.is_file() and target.read_text(encoding="utf-8") == text):
                target.write_text(text, encoding="utf-8")
            target.chmod(0o755)  # yalnızca çalıştırılabilir betikler menüde görünür
    except (OSError, UnicodeDecodeError):
        return False
    return True


def _is_ours(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8") as f:
            f.readline()
            return f.readline().startswith(SCRIPT_MARK)
    except (OSError, UnicodeDecodeError):
        return False


def install(labels: dict[str, MenuLabel]) -> bool:
    """Sağ tık eylemlerini yazar (değişmediyse dosyalara dokunmaz). İkisi de yazıldıysa True."""
    uca = _install_uca(labels)
    scripts = _install_scripts(labels)
    return uca and scripts
