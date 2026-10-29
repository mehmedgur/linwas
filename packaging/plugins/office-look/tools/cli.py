# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""linwas-office-look: LibreOffice Office görünümünün ayar aracı.

Linwas'ın "Office görünümü" sayfası bu aracı çağırır; Linwas yoksa `dialog` komutu
zenity ile basit bir pencere açar. Kullanıcı komutları parola istemez, LibreOffice
kapalıyken çalışır. `generate-ribbons` ve `remove-ribbons` paket betiklerine aittir (root).

Komutlar:
  status [--json]          durum
  set <anahtar> <değer>    ribbon simple|full|classic|default, file_menu on|off,
                           autosave 0|1|2|5|10, save_format ooxml|odf, font carlito|liberation,
                           office_names on|off (menüde "LibreOffice Writer (Word)")
  refresh-names            menü adı kopyalarını ayara göre yenile (LibreOffice güncellenince)
  disable | enable         yalnız bu kullanıcı için kapat / yeniden aç
  dialog                   zenity penceresi
  settings-window          Linwas'ın "Office görünümü" sayfası; Linwas yoksa zenity penceresi
  generate-ribbons         (root) sade şeritleri kurulu LibreOffice'ten üret
  remove-ribbons           (root) üretilen dosyaları sil

Çıkış kodları: 0 tamam, 1 hata, 2 yanlış kullanım, 3 LibreOffice açık.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lo_profile  # noqa: E402
import office_names  # noqa: E402
import ribbon  # noqa: E402

PACKAGE = "linwas-office-look"
LO_SHARE = "/usr/lib/libreoffice/share"
UI_DIR = LO_SHARE + "/config/soffice.cfg/modules/{module}/ui"
RIBBON_XCD = LO_SHARE + "/registry/linwas-office-look-ribbon.xcd"
APPS = {"swriter": "Writer", "scalc": "Calc", "simpress": "Impress"}
SERVICES = {
    "Writer": "com.sun.star.text.TextDocument",
    "Calc": "com.sun.star.sheet.SpreadsheetDocument",
    "Impress": "com.sun.star.presentation.PresentationDocument",
}
ODF_FILTERS = {"Writer": "writer8", "Calc": "calc8", "Impress": "impress8"}
TOOLBAR_MODE = "/org.openoffice.Office.UI.ToolbarMode"
FONT_PATH = "/org.openoffice.Office.Writer/DefaultFont"
LIBERATION_FONTS = {
    "Standard": "Liberation Serif",
    "StandardHeight": "423",  # 12 pt, 1/100 mm
    "Heading": "Liberation Sans",
    "List": "Liberation Serif",
    "Caption": "Liberation Serif",
    "Index": "Liberation Serif",
}

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "linwas-office-look")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
DISABLED_FLAG = os.path.join(CONFIG_DIR, "disabled")
BACKUP_FILE = os.path.join(CONFIG_DIR, "backup.json")
DEFAULT_SETTINGS = {"file_menu": True, "autosave_minutes": 2, "office_names": True}
AUTOSAVE_CHOICES = (0, 1, 2, 5, 10)

EXIT_ERROR, EXIT_USAGE, EXIT_LO_RUNNING = 1, 2, 3


class ToolError(Exception):
    def __init__(self, message: str, code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.code = code


# --- Yardımcılar ---


def _dpkg_version(package: str) -> str | None:
    try:
        r = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}|${Version}", package],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    status, _, version = r.stdout.partition("|")
    return version if "install ok installed" in status else None


def libreoffice_running() -> bool:
    r = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", "soffice.bin"], capture_output=True)
    return r.returncode == 0


def _require_closed() -> None:
    if libreoffice_running():
        raise ToolError("LibreOffice is running; close it first.", EXIT_LO_RUNNING)


def _read_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return settings
    if isinstance(data.get("file_menu"), bool):
        settings["file_menu"] = data["file_menu"]
    if isinstance(data.get("office_names"), bool):
        settings["office_names"] = data["office_names"]
    if data.get("autosave_minutes") in AUTOSAVE_CHOICES:
        settings["autosave_minutes"] = data["autosave_minutes"]
    return settings


def _write_settings(settings: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=1)
    os.replace(tmp, SETTINGS_FILE)


def simple_ribbon_apps() -> list[str]:
    """Sade şeridi üretilmiş uygulamalar."""
    return [
        app
        for module, app in APPS.items()
        if os.path.isfile(os.path.join(UI_DIR.format(module=module), ribbon.OUTPUT_NAME))
    ]


def _ribbon_state(prof: lo_profile.Profile) -> str:
    value = prof.get(lo_profile.app_path("Writer"), "Active")
    return {
        None: "default",
        ribbon.OUTPUT_NAME: "simple",
        "notebookbar.ui": "full",
        "Default": "classic",
    }.get(value, "default")


# --- Kullanıcı komutları ---


def status() -> dict:
    prof = lo_profile.Profile()
    settings = _read_settings()
    writer_filter = prof.get(
        lo_profile.factory_path(SERVICES["Writer"]), "ooSetupFactoryDefaultFilter"
    )
    font = prof.get(FONT_PATH, "Standard")
    return {
        "package_version": _dpkg_version(PACKAGE),
        "libreoffice_version": _dpkg_version("libreoffice-core"),
        "libreoffice_running": libreoffice_running(),
        "disabled": os.path.exists(DISABLED_FLAG),
        "simple_ribbon_apps": simple_ribbon_apps(),
        "settings": {
            "ribbon": _ribbon_state(prof),
            "file_menu": settings["file_menu"],
            "office_names": settings["office_names"],
            "autosave_minutes": settings["autosave_minutes"],
            "save_format": "odf" if writer_filter == ODF_FILTERS["Writer"] else "ooxml",
            "font": "liberation" if font == LIBERATION_FONTS["Standard"] else "carlito",
        },
    }


def _set_ribbon(prof: lo_profile.Profile, value: str) -> None:
    if value == "simple" and not simple_ribbon_apps():
        raise ToolError("The simple ribbon is not available for this LibreOffice version.")
    for app in APPS.values():
        prop = f"Active{app}"
        if value == "default":
            prof.unset(lo_profile.app_path(app), "Active")
            prof.unset(TOOLBAR_MODE, prop)
            continue
        if value == "simple" and app not in simple_ribbon_apps():
            ui, mode = "notebookbar.ui", "notebookbar.ui"
        else:
            ui = ribbon.OUTPUT_NAME if value == "simple" else "notebookbar.ui"
            mode = {"simple": ribbon.OUTPUT_NAME, "full": "notebookbar.ui", "classic": "Default"}[
                value
            ]
        # Active her zaman var olan bir modun CommandArg'ı, Active<Uyg> var olan bir .ui olmalı;
        # yoksa şerit görünmez ya da LibreOffice askıda kalır.
        prof.set(lo_profile.app_path(app), "Active", mode)
        prof.set(TOOLBAR_MODE, prop, ui)


def refresh_names() -> None:
    """Menü adı kopyalarını ayara göre yazar ya da siler (kapalıyken hep siler)."""
    on = _read_settings()["office_names"] and not os.path.exists(DISABLED_FLAG)
    office_names.apply(on)


def set_option(key: str, value: str) -> None:
    if key == "office_names":
        if value not in ("on", "off"):
            raise ToolError("office_names: on|off", EXIT_USAGE)
        settings = _read_settings()
        settings["office_names"] = value == "on"
        _write_settings(settings)
        refresh_names()
        return
    if key in ("file_menu", "autosave"):
        settings = _read_settings()
        if key == "file_menu":
            if value not in ("on", "off"):
                raise ToolError("file_menu: on|off", EXIT_USAGE)
            settings["file_menu"] = value == "on"
        else:
            if not value.isdigit() or int(value) not in AUTOSAVE_CHOICES:
                raise ToolError("autosave: " + "|".join(map(str, AUTOSAVE_CHOICES)), EXIT_USAGE)
            settings["autosave_minutes"] = int(value)
        _write_settings(settings)
        return

    choices = {
        "ribbon": ("simple", "full", "classic", "default"),
        "save_format": ("ooxml", "odf"),
        "font": ("carlito", "liberation"),
    }
    if key not in choices or value not in choices[key]:
        raise ToolError(f"unknown option {key}={value}", EXIT_USAGE)
    _require_closed()
    prof = lo_profile.Profile()
    if key == "ribbon":
        _set_ribbon(prof, value)
    elif key == "save_format":
        for app, service in SERVICES.items():
            path = lo_profile.factory_path(service)
            if value == "odf":
                prof.set(path, "ooSetupFactoryDefaultFilter", ODF_FILTERS[app])
            else:
                prof.unset(path, "ooSetupFactoryDefaultFilter")
        if value == "odf":
            prof.set("/org.openoffice.Office.Common/Save/Document", "WarnAlienFormat", "true")
        else:
            prof.unset("/org.openoffice.Office.Common/Save/Document", "WarnAlienFormat")
    else:
        for prop, font in LIBERATION_FONTS.items():
            if value == "liberation":
                prof.set(FONT_PATH, prop, font)
            else:
                prof.unset(FONT_PATH, prop)
    prof.save()


# "Yalnız benim için kapat": paketin değiştirdiği her şey LibreOffice'in özgün değerine döner.
ORIGINAL_VALUES = (
    [(lo_profile.app_path(app), "Active", "Default") for app in APPS.values()]
    + [(TOOLBAR_MODE, f"Active{app}", "notebookbar.ui") for app in APPS.values()]
    + [
        (lo_profile.factory_path(SERVICES[app]), "ooSetupFactoryDefaultFilter", f)
        for app, f in ODF_FILTERS.items()
    ]
    + [("/org.openoffice.Office.Common/Save/Document", "WarnAlienFormat", "true")]
    + [(FONT_PATH, prop, font) for prop, font in LIBERATION_FONTS.items()]
    + [("/org.openoffice.Office.Impress/Misc/NewDoc", "AutoPilot", "true")]
)


def disable() -> None:
    _require_closed()
    prof = lo_profile.Profile()
    backup = []
    for path, prop, value in ORIGINAL_VALUES:
        backup.append([path, prop, prof.get(path, prop)])
        prof.set(path, prop, value)
    prof.save()
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=1)
    open(DISABLED_FLAG, "w").close()


def enable() -> None:
    _require_closed()
    prof = lo_profile.Profile()
    try:
        with open(BACKUP_FILE, encoding="utf-8") as f:
            backup = json.load(f)
    except (OSError, ValueError):
        backup = [[path, prop, None] for path, prop, _ in ORIGINAL_VALUES]
    for path, prop, old in backup:
        if old is None:
            prof.unset(path, prop)
        else:
            prof.set(path, prop, old)
    prof.save()
    for path in (DISABLED_FLAG, BACKUP_FILE):
        if os.path.exists(path):
            os.remove(path)


# --- Linwas yokken: zenity penceresi ---


def _zenity(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["zenity", *args], capture_output=True, text=True)


def dialog() -> int:
    title = "Office görünümü"
    disabled = os.path.exists(DISABLED_FLAG)
    rows = (
        [
            "TRUE",
            "enable",
            "Benim için yeniden aç",
            "Sade şerit, Dosya menüsü ve varsayılanlar geri gelir.",
        ]
        if disabled
        else [
            "TRUE",
            "disable",
            "Yalnız benim için kapat",
            "Parola istemez. Diğer kullanıcılar etkilenmez, istediğinde geri açabilirsin.",
        ]
    )
    rows += [
        "FALSE",
        "remove",
        "Tümüyle kaldır",
        "Bütün kullanıcılar için kaldırır. Yönetici parolası ister.",
    ]
    r = _zenity(
        "--list",
        "--radiolist",
        f"--title={title}",
        "--width=780",
        "--height=260",
        "--text=LibreOffice'in özgün görünümüne ve ayarlarına dönmek için birini seç. "
        "Belgelerine dokunulmaz.",
        "--column=",
        "--column=code",
        "--column=Ne yapılsın?",
        "--column=Açıklama",
        "--hide-column=2",
        "--print-column=2",
        "--ok-label=Uygula",
        "--cancel-label=Vazgeç",
        *rows,
    )
    choice = r.stdout.strip()
    if r.returncode != 0 or not choice:
        return 0
    if choice == "remove":
        ok = subprocess.run(["pkexec", "apt-get", "remove", "-y", PACKAGE]).returncode == 0
        _zenity(
            "--info" if ok else "--error",
            f"--title={title}",
            "--text=" + ("Kaldırıldı." if ok else "Kaldırılamadı. Yetki verilmemiş olabilir."),
        )
        return 0 if ok else 1
    while libreoffice_running():
        r = _zenity(
            "--question",
            f"--title={title}",
            "--ok-label=Yeniden dene",
            "--cancel-label=Vazgeç",
            "--text=Önce bütün LibreOffice pencerelerini kapat.",
        )
        if r.returncode != 0:
            return 0
    (enable if choice == "enable" else disable)()
    _zenity("--info", f"--title={title}", "--text=Tamam. LibreOffice'i açtığında göreceksin.")
    return 0


# --- Paket betikleri (root) ---


def _ribbon_xcd(apps: list[str]) -> str:
    def mode(app: str) -> str:
        return f"""      <node oor:name="{app}">
        <prop oor:name="Active" oor:op="fuse"><value>{ribbon.OUTPUT_NAME}</value></prop>
        <node oor:name="Modes">
          <!-- Eksik alan olursa LibreOffice girdiyi sessizce siler; tüm alanlar zorunlu. -->
          <node oor:name="LinwasSimple" oor:op="replace">
            <prop oor:name="Label">
              <value xml:lang="en-US">Simple (Linwas)</value>
              <value xml:lang="tr">Sade (Linwas)</value>
            </prop>
            <prop oor:name="CommandArg"><value>{ribbon.OUTPUT_NAME}</value></prop>
            <prop oor:name="MenuPosition"><value>10</value></prop>
            <prop oor:name="HasNotebookbar"><value>true</value></prop>
            <prop oor:name="IsExperimental"><value>false</value></prop>
            <prop oor:name="HasMenubar"><value>false</value></prop>
            <prop oor:name="Toolbars"><value/></prop>
            <prop oor:name="UserToolbars"><value/></prop>
            <prop oor:name="UIItemProperties"><value/></prop>
            <prop oor:name="Sidebar"><value>Arrow</value></prop>
          </node>
        </node>
      </node>
"""

    ui = ribbon.OUTPUT_NAME
    actives = "".join(
        f'    <prop oor:name="Active{app}" oor:op="fuse"><value>{ui}</value></prop>\n'
        for app in apps
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- linwas-office-look tarafından kurulumda üretildi; elle değiştirmeyin. -->
<oor:data xmlns:xs="http://www.w3.org/2001/XMLSchema"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xmlns:oor="http://openoffice.org/2001/registry">
  <dependency file="main"/>
  <oor:component-data oor:name="ToolbarMode" oor:package="org.openoffice.Office.UI">
{actives}    <node oor:name="Applications">
{"".join(mode(app) for app in apps)}    </node>
  </oor:component-data>
</oor:data>
"""


def remove_ribbons() -> None:
    for module in APPS:
        path = os.path.join(UI_DIR.format(module=module), ribbon.OUTPUT_NAME)
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(RIBBON_XCD):
        os.remove(RIBBON_XCD)


def generate_ribbons() -> list[str]:
    """Üretilebilen uygulamaların sade şeridini kurar; başarısız olan uygulama tam şeritte kalır."""
    if os.geteuid() != 0:
        raise ToolError("generate-ribbons must run as root")
    remove_ribbons()
    done = []
    for module, app in APPS.items():
        folder = UI_DIR.format(module=module)
        source = os.path.join(folder, "notebookbar.ui")
        target = os.path.join(folder, ribbon.OUTPUT_NAME)
        if not os.path.isfile(source):
            continue
        try:
            ribbon.build(module, source, target)
            if ribbon.dangling_size_groups(target):
                raise ribbon.RibbonError("dangling size groups")
            os.chmod(target, 0o644)
            done.append(app)
        except (ribbon.RibbonError, OSError) as e:
            print(f"linwas-office-look: {app}: simple ribbon skipped: {e}", file=sys.stderr)
            if os.path.exists(target):
                os.remove(target)
    if done:
        with open(RIBBON_XCD, "w", encoding="utf-8") as f:
            f.write(_ribbon_xcd(done))
        os.chmod(RIBBON_XCD, 0o644)
    return done


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return EXIT_USAGE
    command, args = argv[0], argv[1:]
    try:
        if command == "status":
            data = status()
            print(
                json.dumps(data, ensure_ascii=False)
                if "--json" in args
                else json.dumps(data, indent=1)
            )
        elif command == "set" and len(args) == 2:
            set_option(*args)
        elif command == "disable":
            disable()
            refresh_names()
        elif command == "enable":
            enable()
            refresh_names()
        elif command == "refresh-names":
            refresh_names()
        elif command == "dialog":
            return dialog()
        elif command == "settings-window":
            try:
                os.execvp("linwas", ["linwas", "--page", "office_look"])
            except OSError:
                return dialog()
        elif command == "generate-ribbons":
            print("simple ribbon: " + (", ".join(generate_ribbons()) or "none"))
        elif command == "remove-ribbons":
            remove_ribbons()
        else:
            print(__doc__, file=sys.stderr)
            return EXIT_USAGE
    except ToolError as e:
        print(f"linwas-office-look: {e}", file=sys.stderr)
        return e.code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
