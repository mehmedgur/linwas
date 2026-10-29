# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Kullanıcının LibreOffice ayar dosyasını (registrymodifications.xcu) okur ve yazar.

LibreOffice açıkken yazılmamalı: kapanırken kendi bellekteki değerleriyle üzerine yazar.
Yalnız standart kütüphane kullanır.
"""

from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET

OOR = "http://openoffice.org/2001/registry"
DEFAULT_PATH = os.path.join(
    os.path.expanduser("~"), ".config", "libreoffice", "4", "user", "registrymodifications.xcu"
)

ET.register_namespace("oor", OOR)


def app_path(app: str) -> str:
    return (
        "/org.openoffice.Office.UI.ToolbarMode/Applications/"
        f"org.openoffice.Office.UI.ToolbarMode:Application['{app}']"
    )


def factory_path(service: str) -> str:
    return f"/org.openoffice.Setup/Office/Factories/org.openoffice.Setup:Factory['{service}']"


class Profile:
    """registrymodifications.xcu içindeki doğrudan <item><prop> girdileri."""

    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self.path = path
        if os.path.exists(path):
            self.tree = ET.parse(path)
        else:
            self.tree = ET.ElementTree(ET.Element(f"{{{OOR}}}items"))
        self.root = self.tree.getroot()

    def _find(self, path: str, prop: str) -> tuple[ET.Element | None, ET.Element | None]:
        for item in self.root.findall("item"):
            if item.get(f"{{{OOR}}}path") != path:
                continue
            for p in item.findall("prop"):
                if p.get(f"{{{OOR}}}name") == prop:
                    return item, p
        return None, None

    def get(self, path: str, prop: str) -> str | None:
        _, p = self._find(path, prop)
        if p is None:
            return None
        value = p.find("value")
        return value.text if value is not None else None

    def set(self, path: str, prop: str, value: str) -> None:
        self.unset(path, prop)
        item = ET.SubElement(self.root, "item", {f"{{{OOR}}}path": path})
        p = ET.SubElement(item, "prop", {f"{{{OOR}}}name": prop, f"{{{OOR}}}op": "fuse"})
        ET.SubElement(p, "value").text = value

    def unset(self, path: str, prop: str) -> None:
        item, _ = self._find(path, prop)
        if item is not None:
            self.root.remove(item)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if os.path.exists(self.path):
            shutil.copy2(self.path, self.path + ".linwas-backup")
        # ElementTree kullanılmayan ad alanı bildirimlerini atar; LibreOffice "xs:string" gibi
        # değerler için xs ve xsi bildirimlerini bekler, kök etiketi elle yazılır.
        body = ET.tostring(self.root, encoding="unicode")
        body = body[body.index(">") + 1 :]
        tmp = self.path + ".linwas-tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<oor:items xmlns:oor="{OOR}" xmlns:xs="http://www.w3.org/2001/XMLSchema" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' + body + "\n"
            )
        os.replace(tmp, self.path)
