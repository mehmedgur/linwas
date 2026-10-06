"""Görünüm ayarları (kullanıcı yetkisiyle, `gsettings` ile).

Yalnızca aşağıdaki şema/anahtarlar okunur ve yazılır. GNOME anahtarları Pardus 23'te
`gsettings` ile doğrulandı; Cinnamon şeması Cinnamon kurulu sistemde vardır.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# masaüstü → ayar adı → (şema, anahtar)
KEYS: dict[str, dict[str, tuple[str, str]]] = {
    "gnome": {
        "color_scheme": ("org.gnome.desktop.interface", "color-scheme"),
        "gtk_theme": ("org.gnome.desktop.interface", "gtk-theme"),
        "text_scale": ("org.gnome.desktop.interface", "text-scaling-factor"),
        "wallpaper": ("org.gnome.desktop.background", "picture-uri"),
        "wallpaper_dark": ("org.gnome.desktop.background", "picture-uri-dark"),
        "buttons": ("org.gnome.desktop.wm.preferences", "button-layout"),
        "input_sources": ("org.gnome.desktop.input-sources", "sources"),
        "region": ("org.gnome.system.locale", "region"),
        "left_handed": ("org.gnome.desktop.peripherals.mouse", "left-handed"),
    },
    "cinnamon": {
        "gtk_theme": ("org.cinnamon.desktop.interface", "gtk-theme"),
        "text_scale": ("org.cinnamon.desktop.interface", "text-scaling-factor"),
        "wallpaper": ("org.cinnamon.desktop.background", "picture-uri"),
    },
}

# Windows gibi: simge solda yok, sağda küçült/büyüt/kapat
WINDOWS_BUTTON_LAYOUT = "appmenu:minimize,maximize,close"

# GNOME için Windows tarzı görev çubuğu (Debian/Pardus paketi ve eklenti kimliği doğrulandı)
DASH_TO_PANEL_PACKAGE = "gnome-shell-extension-dash-to-panel"
DASH_TO_PANEL_UUID = "dash-to-panel@jderose9.github.com"

# Windows yazı tiplerine ölçü olarak uyumlu açık fontlar
COMPAT_FONT_PACKAGES = ("fonts-crosextra-carlito", "fonts-crosextra-caladea", "fonts-liberation")

_RE_GVARIANT_STRING = re.compile(r"^'(.*)'$", re.DOTALL)


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.returncode, r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1, ""


def supported(desktop: str) -> bool:
    return desktop in KEYS


def get(desktop: str, name: str) -> str | None:
    """Ayarın değeri (dize olarak; GVariant tırnakları atılır). Yoksa None."""
    key = KEYS.get(desktop, {}).get(name)
    if not key:
        return None
    code, out = _run(["gsettings", "get", *key])
    if code != 0:
        return None
    m = _RE_GVARIANT_STRING.match(out)
    return m.group(1) if m else out


def set_value(desktop: str, name: str, value: str | float) -> bool:
    key = KEYS.get(desktop, {}).get(name)
    if not key:
        return False
    text = str(value)
    if "\n" in text or "\x00" in text:
        return False
    return _run(["gsettings", "set", *key, text])[0] == 0


def set_dark(desktop: str, dark: bool) -> bool:
    """Koyu/açık tema. GNOME: color-scheme + uygun Adwaita GTK teması."""
    if desktop == "gnome":
        ok = set_value("gnome", "color_scheme", "prefer-dark" if dark else "default")
        return set_value("gnome", "gtk_theme", "Adwaita-dark" if dark else "Adwaita") and ok
    if desktop == "cinnamon":
        current = get("cinnamon", "gtk_theme") or "Mint-Y"
        base = current.removesuffix("-Dark")
        return set_value("cinnamon", "gtk_theme", f"{base}-Dark" if dark else base)
    return False


def is_dark(desktop: str) -> bool:
    if desktop == "gnome" and get("gnome", "color_scheme") == "prefer-dark":
        return True
    theme = get(desktop, "gtk_theme") or ""
    return theme.lower().endswith("-dark")


def set_wallpaper(desktop: str, image: Path) -> bool:
    if not image.is_file():
        return False
    uri = image.resolve().as_uri()
    ok = set_value(desktop, "wallpaper", uri)
    if desktop == "gnome":
        ok = set_value(desktop, "wallpaper_dark", uri) and ok
    return ok


# --- GNOME eklentisi ---


def extension_state(uuid: str = DASH_TO_PANEL_UUID) -> str:
    """ "missing" | "disabled" | "enabled".

    `info` kurulu olup olmadığını söyler; etkinlik `list --enabled` ile okunur
    (GNOME 43'te `info` etkin eklentiyi "INITIALIZED" gösterebiliyor).
    """
    if _run(["gnome-extensions", "info", uuid])[0] != 0:
        return "missing"
    enabled = _run(["gnome-extensions", "list", "--enabled"])[1].split()
    return "enabled" if uuid in enabled else "disabled"


def set_extension(enabled: bool, uuid: str = DASH_TO_PANEL_UUID) -> bool:
    return _run(["gnome-extensions", "enable" if enabled else "disable", uuid])[0] == 0
