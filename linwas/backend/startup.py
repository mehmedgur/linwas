"""Başlangıç uygulamaları: .desktop dosyalarını okur ve yönetir."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StartupApp:
    name: str
    comment: str
    desktop_file: Path  # kaynak .desktop dosyası
    user_override: Path  # ~/.config/autostart/ kopyası
    enabled: bool  # False: Hidden=true veya X-GNOME-Autostart-enabled=false
    system: bool  # True: /etc/xdg/autostart kaynaklı


_SYSTEM_DIRS = [Path("/etc/xdg/autostart")]
_USER_DIR = Path.home() / ".config" / "autostart"


def _parse_desktop(path: Path) -> dict[str, str]:
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(str(path), encoding="utf-8")
        if cp.has_section("Desktop Entry"):
            return dict(cp["Desktop Entry"])
    except Exception:
        pass
    return {}


def _is_enabled(fields: dict[str, str]) -> bool:
    return (
        fields.get("hidden", "false").lower() != "true"
        and fields.get("x-gnome-autostart-enabled", "true").lower() != "false"
    )


def _localized(fields: dict[str, str], key: str, lang: str) -> str:
    """Desktop Entry yerelleştirilmiş değeri (ör. Name[tr]); yoksa varsayılan."""
    return fields.get(f"{key}[{lang}]") or fields.get(key, "")


def _shown_in(fields: dict[str, str], desktops: set[str]) -> bool:
    """OnlyShowIn / NotShowIn (Desktop Entry belirtimi) bu masaüstüne göre süzülür."""
    if not desktops:
        return True
    only = {d for d in fields.get("onlyshowin", "").lower().split(";") if d}
    never = {d for d in fields.get("notshowin", "").lower().split(";") if d}
    return (not only or bool(only & desktops)) and not (never & desktops)


def list_startup_apps(lang: str = "en", desktop: str | None = None) -> list[StartupApp]:
    """Sistem ve kullanıcı başlangıç uygulamalarını döner.

    `desktop`: XDG_CURRENT_DESKTOP biçiminde (ör. "GNOME" ya da "ubuntu:GNOME"); verilmezse
    ortamdan okunur. Bu masaüstünde başlamayan girdiler listelenmez.
    """
    if desktop is None:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    desktops = {d for d in desktop.lower().split(":") if d}
    _USER_DIR.mkdir(parents=True, exist_ok=True)
    user_overrides = {p.name: p for p in _USER_DIR.glob("*.desktop")}

    apps: list[StartupApp] = []
    seen: set[str] = set()

    for src_dir in _SYSTEM_DIRS:
        if not src_dir.is_dir():
            continue
        for desktop in src_dir.glob("*.desktop"):
            if desktop.name in seen:
                continue
            seen.add(desktop.name)
            fields = _parse_desktop(desktop)
            if not fields.get("name") or not _shown_in(fields, desktops):
                continue
            override = user_overrides.get(desktop.name, _USER_DIR / desktop.name)
            # Kullanıcı override'ı varsa ondan oku
            effective = _parse_desktop(override) if override.exists() else fields
            apps.append(
                StartupApp(
                    name=_localized(fields, "name", lang) or desktop.stem,
                    comment=_localized(fields, "comment", lang),
                    desktop_file=desktop,
                    user_override=override,
                    enabled=_is_enabled(effective),
                    system=True,
                )
            )

    # Yalnızca kullanıcıya ait başlangıç uygulamaları
    for desktop in _USER_DIR.glob("*.desktop"):
        if desktop.name in seen:
            continue
        fields = _parse_desktop(desktop)
        if not fields.get("name") or not _shown_in(fields, desktops):
            continue
        apps.append(
            StartupApp(
                name=_localized(fields, "name", lang) or desktop.stem,
                comment=_localized(fields, "comment", lang),
                desktop_file=desktop,
                user_override=desktop,
                enabled=_is_enabled(fields),
                system=False,
            )
        )

    return sorted(apps, key=lambda a: a.name.lower())


def set_enabled(app: StartupApp, enabled: bool) -> bool:
    """Başlangıç uygulamasını etkinleştirir/devre dışı bırakır.

    Sistem dosyalarına dokunmaz; kullanıcı dizininde override oluşturur.
    """
    try:
        _USER_DIR.mkdir(parents=True, exist_ok=True)
        cp = configparser.ConfigParser(interpolation=None)

        # Kaynak dosyayı oku
        cp.read(str(app.desktop_file), encoding="utf-8")
        if not cp.has_section("Desktop Entry"):
            cp.add_section("Desktop Entry")

        if enabled:
            cp.set("Desktop Entry", "Hidden", "false")
            cp.set("Desktop Entry", "X-GNOME-Autostart-Enabled", "true")
        else:
            cp.set("Desktop Entry", "Hidden", "true")
            cp.set("Desktop Entry", "X-GNOME-Autostart-Enabled", "false")

        with open(app.user_override, "w", encoding="utf-8") as f:
            cp.write(f)
        return True
    except OSError:
        return False
