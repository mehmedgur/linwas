# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Dokunmatik yüzeyde sağ tık yöntemi (Windows'tan gelenler için).

GNOME'un varsayılanı `click-method = 'fingers'`: sağ tık için iki parmakla basılır, sağ alt köşeye
basmak sol tık sayılır. Windows'taki gibi köşeyle sağ tık için `'areas'` (GNOME 43 şemasında
doğrulandı: org.gnome.desktop.peripherals.touchpad click-method = default | none | areas | fingers).
Kullanıcı ayarıdır; root gerekmez. Şimdilik yalnız GNOME (Cinnamon/XFCE'de anahtar doğrulanmadı).
"""

from __future__ import annotations

from pathlib import Path

from linwas.backend import workgroups

SCHEMA = "org.gnome.desktop.peripherals.touchpad"
KEY = "click-method"
CORNER = "areas"  # sağ alt köşe = sağ tık (Windows gibi)
FINGERS = "fingers"  # iki parmakla basınca sağ tık (GNOME varsayılanı)
_DEVICES = Path("/proc/bus/input/devices")


def has_touchpad(devices: Path = _DEVICES) -> bool:
    """Giriş aygıtları arasında dokunmatik yüzey var mı (dizüstü)."""
    try:
        text = devices.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(line.startswith("N:") and "touchpad" in line.lower() for line in text.splitlines())


def supported() -> bool:
    return workgroups.desktop_kind() == "gnome"


def click_method() -> str:
    code, out = workgroups._gs("get", SCHEMA, KEY)
    return out.strip().strip("'") if code == 0 else ""


def corner_right_click() -> bool:
    return click_method() == CORNER


def set_corner_right_click(on: bool) -> bool:
    """on: köşeyle sağ tık; off: GNOME'un varsayılanına dön (iki parmak)."""
    if on:
        return workgroups._gs("set", SCHEMA, KEY, CORNER)[0] == 0
    return workgroups._gs("reset", SCHEMA, KEY)[0] == 0


def should_offer() -> bool:
    """İlk açılışta önerilsin mi: GNOME, dokunmatik yüzey var, köşe tıklaması kapalı."""
    return supported() and has_touchpad() and not corner_right_click()
