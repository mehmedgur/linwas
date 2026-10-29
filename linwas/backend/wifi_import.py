# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Windows Wi-Fi profillerini NetworkManager'a aktarma.

Windows'ta `netsh wlan export profile key=clear folder=<klasör>` ile alınan XML
dosyaları (WLAN_profile şeması) okunur ve `nmcli connection add` ile eklenir.
Kullanıcı yetkisiyle çalışır (NetworkManager kendi izinlerini yönetir).
"""

from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# Windows kimlik doğrulama → NetworkManager key-mgmt (nm-settings-nmcli(5))
_KEY_MGMT = {
    "open": "",
    "WPAPSK": "wpa-psk",
    "WPA2PSK": "wpa-psk",
    "WPA3SAE": "sae",
}


@dataclass
class WifiProfile:
    file: str
    ssid: str
    authentication: str
    key: str  # düz metin anahtar (export key=clear); yoksa ""

    @property
    def supported(self) -> bool:
        if self.authentication not in _KEY_MGMT:
            return False
        return self.authentication == "open" or bool(self.key)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_profile(path: Path) -> WifiProfile | None:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    if _local(root.tag) != "WLANProfile":
        return None
    ssid = auth = key = ""
    protected = "false"
    for el in root.iter():
        name = _local(el.tag)
        text = (el.text or "").strip()
        if name == "SSID":
            for child in el:
                if _local(child.tag) == "name" and child.text:
                    ssid = child.text.strip()
        elif name == "authentication":
            auth = text
        elif name == "keyMaterial":
            key = text
        elif name == "protected":
            protected = text.lower()
    if not ssid:
        return None
    # Şifreli (protected=true) anahtar Windows dışında çözülemez
    return WifiProfile(str(path), ssid, auth, key if protected == "false" else "")


def import_profile(profile: WifiProfile) -> tuple[bool, str]:
    if not profile.supported:
        return False, "unsupported"
    cmd = [
        "nmcli",
        "connection",
        "add",
        "type",
        "wifi",
        "con-name",
        profile.ssid,
        "ssid",
        profile.ssid,
    ]
    mgmt = _KEY_MGMT[profile.authentication]
    if mgmt:
        cmd += ["wifi-sec.key-mgmt", mgmt, "wifi-sec.psk", profile.key]
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=False, env=env)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return r.returncode == 0, (r.stderr or r.stdout).strip()
