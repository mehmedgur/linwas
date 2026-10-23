"""Linwas görev çubuğu eklentisi (GNOME): Dash to Panel üstüne görünüm, yerleşim ve medya widget'ı.

- Ayar dosyası: ~/.local/share/linwas/taskbar.json — GNOME Shell eklentisi (`linwas-taskbar@linwas`)
  izler ve hemen uygular (arka plan saydam/mat/bulanık, renk kaynağı, medya kontrolü ve kartı,
  temaya göre renkler, çevrilmiş metinler).
- Yerleşim (konum, boyut, otomatik gizleme, pencere önizlemesi) Dash to Panel'in kendi ayarlarıyla
  (`gsettings --schemadir`; anahtarlar Pardus 23'te doğrulandı).
- Hazır düzenler: Windows gibi (Dash to Panel), macOS gibi (Dash to Dock + üst çubuk), GNOME
  varsayılanı. Geçişten önce düzen saklanır; "Önceki düzene dön" geri yükler.
Kullanıcı yetkisiyle çalışır; Dash to Dock kurulumu arayüzde root görevi olarak istenir.
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from linwas.backend import app_folders, appearance, window_groups, workgroups

EXT_UUID = "linwas-taskbar@linwas"
DTP_UUID = window_groups.DTP_UUID
DTP_SCHEMA = "org.gnome.shell.extensions.dash-to-panel"
DOCK_SCHEMA = "org.gnome.shell.extensions.dash-to-dock"
DOCK_PACKAGE = "gnome-shell-extension-dashtodock"  # Pardus 23 / Debian 12 deposunda doğrulandı
SYSTEM_EXT_DIR = Path("/usr/share/gnome-shell/extensions")
_SOURCE = Path(__file__).resolve().parent.parent / "resources" / "gnome-taskbar"

PANEL_STYLES = ("transparent", "matte", "blur")
COLOR_SOURCES = ("theme", "accent", "cover")
POSITIONS = ("BOTTOM", "TOP", "LEFT", "RIGHT")
PRESETS = ("windows", "macos", "gnome")
SIZE_RANGE = (32, 72)


@dataclass
class TaskbarConfig:
    panel_style: str = "blur"
    transparency: int = 35  # % (0 = tamamen opak)
    panel_color: str = "theme"
    media_panel: bool = True  # görev çubuğunda küçük medya kontrolü
    media_calendar: bool = True  # takvim menüsünde Linwas medya kartı
    card_style: str = "matte"
    cover_color: bool = True  # kartta kapak resminin rengi
    # Linwas'ın verdiği renkler ve metinler (eklenti okur)
    palette: dict = field(default_factory=dict)
    strings: dict = field(default_factory=dict)


def config_file() -> Path:
    return app_folders._data_home() / "linwas" / "taskbar.json"


def _before_file() -> Path:
    return app_folders._data_home() / "linwas" / "taskbar-before.json"


def load_config() -> TaskbarConfig:
    cfg = TaskbarConfig()
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    for f in fields(TaskbarConfig):
        value = data.get(f.name)
        default = getattr(cfg, f.name)
        if f.name == "panel_style" and value in PANEL_STYLES:
            cfg.panel_style = value
        elif f.name == "card_style" and value in PANEL_STYLES:
            cfg.card_style = value
        elif f.name == "panel_color" and value in COLOR_SOURCES:
            cfg.panel_color = value
        elif f.name == "transparency" and isinstance(value, int) and 0 <= value <= 90:
            cfg.transparency = value
        elif (isinstance(default, bool) and isinstance(value, bool)) or (
            isinstance(default, dict) and isinstance(value, dict)
        ):
            setattr(cfg, f.name, value)
    return cfg


def save_config(cfg: TaskbarConfig) -> None:
    target = config_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)  # eklenti yarım dosya okumasın
    except OSError:
        pass


def write_palette(
    light: dict[str, str], dark: dict[str, str], accent: str, mode: str = "system"
) -> None:
    """Linwas'ın açık/koyu renklerini ve vurgu rengini eklentiye verir.

    mode: "light" / "dark" = Linwas'ın seçili teması (görev çubuğu da ona uyar);
    "system" = masaüstünün açık/koyu ayarı izlenir.
    """
    cfg = load_config()
    palette = {"light": light, "dark": dark, "accent": accent, "mode": mode}
    if cfg.palette != palette:
        cfg.palette = palette
        save_config(cfg)


def sync_palette(
    light: dict[str, str], dark: dict[str, str], accent: str, mode: str = "system"
) -> None:
    """Renkleri günceller (değişmediyse dosyaya yazılmaz)."""
    write_palette(light, dark, accent, mode)


# --- Dash to Panel / Dash to Dock ayarları ---


def _schema_dir(uuid_prefix: str) -> Path | None:
    for base in (app_folders._data_home() / "gnome-shell" / "extensions", SYSTEM_EXT_DIR):
        try:
            for d in base.iterdir():
                if d.name.startswith(uuid_prefix) and (d / "schemas").is_dir():
                    return d / "schemas"
        except OSError:
            continue
    return None


def dock_uuid() -> str:
    """Kurulu Dash to Dock'un kimliği (kurulu değilse "")."""
    for base in (app_folders._data_home() / "gnome-shell" / "extensions", SYSTEM_EXT_DIR):
        try:
            for d in base.iterdir():
                if d.name.startswith("dash-to-dock@") and (d / "metadata.json").is_file():
                    return d.name
        except OSError:
            continue
    return ""


def _gsettings(schema_dir: Path | None, *args: str) -> tuple[int, str]:
    cmd = ["gsettings"]
    if schema_dir is not None:
        cmd += ["--schemadir", str(schema_dir)]
    return workgroups._run([*cmd, *args])


def dtp_installed() -> bool:
    return _schema_dir("dash-to-panel@") is not None


def dtp_get(key: str) -> str | None:
    code, out = _gsettings(_schema_dir("dash-to-panel@"), "get", DTP_SCHEMA, key)
    return out.strip() if code == 0 else None


def dtp_set(key: str, value: str) -> bool:
    code, _ = _gsettings(_schema_dir("dash-to-panel@"), "set", DTP_SCHEMA, key, value)
    return code == 0


@dataclass
class Layout:
    position: str = "BOTTOM"
    size: int = 48
    autohide: bool = False
    previews: bool = True


def _monitors() -> list[str]:
    """Dash to Panel'in bildiği ekran sıraları ("available-monitors"; yoksa ["0"])."""
    raw = (dtp_get("available-monitors") or "").replace("@ai", "").strip()
    nums = re.findall(r"\d+", raw)
    return nums or ["0"]


def _json_setting(key: str) -> dict:
    raw = (dtp_get(key) or "").strip()
    if raw.startswith("'") and raw.endswith("'"):
        raw = raw[1:-1]
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _set_json(key: str, value: dict) -> bool:
    text = json.dumps(value, separators=(",", ":"))
    return dtp_set(key, "'" + text.replace("'", "") + "'")


def read_layout() -> Layout:
    """Dash to Panel ekran başına ayarı (panel-positions / panel-sizes) önce okur."""
    lay = Layout()
    first = _monitors()[0]
    pos = _json_setting("panel-positions").get(first) or (dtp_get("panel-position") or "").strip(
        "'"
    )
    if pos in POSITIONS:
        lay.position = pos
    size = _json_setting("panel-sizes").get(first)
    if not isinstance(size, int):
        raw = dtp_get("panel-size") or ""
        size = int(raw) if raw.isdigit() else 48
    lay.size = size
    lay.autohide = dtp_get("intellihide") == "true"
    lay.previews = dtp_get("show-window-previews") != "false"
    return lay


def set_position(position: str) -> bool:
    """Dash to Panel yalnızca "panel-positions" değişimini dinler (panelManager.js); her ekrana
    aynı konum yazılır."""
    if position not in POSITIONS:
        return False
    value = _json_setting("panel-positions")
    for m in _monitors():
        value[m] = position
    dtp_set("panel-position", f"'{position}'")
    return _set_json("panel-positions", value)


def set_size(size: int) -> bool:
    size = max(SIZE_RANGE[0], min(SIZE_RANGE[1], size))
    value = _json_setting("panel-sizes")
    for m in _monitors():
        value[m] = size
    dtp_set("panel-size", str(size))
    return _set_json("panel-sizes", value)


def set_autohide(on: bool) -> bool:
    return dtp_set("intellihide", "true" if on else "false")


def set_previews(on: bool) -> bool:
    return dtp_set("show-window-previews", "true" if on else "false")


# --- Görev çubuğu öğeleri ve hizalama (Dash to Panel "panel-element-positions") ---
# Biçim (dash-to-panel panelPositions.js, GNOME 43 sürümünde doğrulandı): {"<ekran>": [{"element",
# "visible", "position"}, ...]}; yer: stackedTL (sol/üst), stackedBR (sağ/alt), centerMonitor.

ELEMENTS = (
    "showAppsButton",
    "activitiesButton",
    "leftBox",
    "taskbar",
    "centerBox",
    "rightBox",
    "dateMenu",
    "systemMenu",
    "desktopButton",
)
# Kullanıcının açıp kapatabildiği öğeler
TOGGLEABLE = ("showAppsButton", "activitiesButton", "dateMenu", "systemMenu", "desktopButton")
_DEFAULT_ELEMENTS = [
    {"element": "showAppsButton", "visible": True, "position": "stackedTL"},
    {"element": "activitiesButton", "visible": False, "position": "stackedTL"},
    {"element": "leftBox", "visible": True, "position": "stackedTL"},
    {"element": "taskbar", "visible": True, "position": "stackedTL"},
    {"element": "centerBox", "visible": True, "position": "stackedBR"},
    {"element": "rightBox", "visible": True, "position": "stackedBR"},
    {"element": "dateMenu", "visible": True, "position": "stackedBR"},
    {"element": "systemMenu", "visible": True, "position": "stackedBR"},
    {"element": "desktopButton", "visible": True, "position": "stackedBR"},
]
_CENTER = "centerMonitor"
_LEFT = "stackedTL"
_RIGHT = "stackedBR"


def read_elements() -> list[dict]:
    """İlk ekranın öğe listesi (yoksa Dash to Panel varsayılanı); bilinmeyen öğeler atlanır."""
    raw = _json_setting("panel-element-positions").get(_monitors()[0])
    if not isinstance(raw, list):
        return [dict(e) for e in _DEFAULT_ELEMENTS]
    items = [e for e in raw if isinstance(e, dict) and e.get("element") in ELEMENTS]
    names = {e["element"] for e in items}
    # Eksik öğe varsa varsayılan yerinde eklenir (sıra korunur)
    for default in _DEFAULT_ELEMENTS:
        if default["element"] not in names:
            items.append(dict(default))
    return items


def write_elements(elements: list[dict]) -> bool:
    value = _json_setting("panel-element-positions")
    for m in _monitors():
        value[m] = [dict(e) for e in elements]
    return _set_json("panel-element-positions", value)


def _element(elements: list[dict], name: str) -> dict:
    return next(e for e in elements if e["element"] == name)


def set_element_visible(name: str, visible: bool) -> bool:
    if name not in TOGGLEABLE:
        return False
    elements = read_elements()
    _element(elements, name)["visible"] = visible
    return write_elements(elements)


def alignment(elements: list[dict] | None = None) -> str:
    """ "center" (Windows 11: Başlat ve simgeler ortada) ya da "left" (Windows 10)."""
    elements = elements or read_elements()
    return "center" if _element(elements, "taskbar")["position"] == _CENTER else "left"


def set_alignment(mode: str) -> bool:
    """Başlat düğmesi ve simgeler birlikte ortaya ya da sola."""
    if mode not in ("center", "left"):
        return False
    elements = read_elements()
    position = _CENTER if mode == "center" else _LEFT
    for name in ("showAppsButton", "taskbar"):
        _element(elements, name)["position"] = position
    return write_elements(elements)


def clock_centered(elements: list[dict] | None = None) -> bool:
    elements = elements or read_elements()
    return _element(elements, "dateMenu")["position"] == _CENTER


def set_clock_centered(on: bool) -> bool:
    elements = read_elements()
    _element(elements, "dateMenu")["position"] = _CENTER if on else _RIGHT
    return write_elements(elements)


# --- Davranış (Dash to Panel anahtarları, şemada doğrulandı) ---

BEHAVIOUR_KEYS = {
    "combine": "group-apps",  # aynı programın pencereleri tek düğmede
    "all_monitors": "multi-monitors",  # her ekranda görev çubuğu
    "badge_count": "progress-show-count",  # simgede bildirim sayısı
    "progress_bar": "progress-show-bar",  # simgede indirme/kopyalama ilerlemesi
    "desktop_hover": "show-showdesktop-hover",  # köşeye gelince masaüstünü göster
}


@dataclass
class Behaviour:
    combine: bool = True
    all_monitors: bool = True
    badge_count: bool = True
    progress_bar: bool = True
    desktop_hover: bool = False


def read_behaviour() -> Behaviour:
    b = Behaviour()
    for attr, key in BEHAVIOUR_KEYS.items():
        value = dtp_get(key)
        if value in ("true", "false"):
            setattr(b, attr, value == "true")
    return b


def set_behaviour(attr: str, on: bool) -> bool:
    key = BEHAVIOUR_KEYS.get(attr)
    return bool(key) and dtp_set(key, "true" if on else "false")


# --- Saat ve tarih (GNOME: org.gnome.desktop.interface) ---

CLOCK_SCHEMA = "org.gnome.desktop.interface"
CLOCK_KEYS = {
    "date": "clock-show-date",
    "weekday": "clock-show-weekday",
    "seconds": "clock-show-seconds",
}


@dataclass
class Clock:
    date: bool = True
    weekday: bool = False
    seconds: bool = False
    format24: bool = True


def read_clock() -> Clock:
    c = Clock()
    for attr, key in CLOCK_KEYS.items():
        code, out = workgroups._gs("get", CLOCK_SCHEMA, key)
        if code == 0 and out.strip() in ("true", "false"):
            setattr(c, attr, out.strip() == "true")
    code, out = workgroups._gs("get", CLOCK_SCHEMA, "clock-format")
    if code == 0:
        c.format24 = out.strip().strip("'") != "12h"
    return c


def set_clock(attr: str, on: bool) -> bool:
    if attr == "format24":
        return workgroups._gs("set", CLOCK_SCHEMA, "clock-format", "24h" if on else "12h")[0] == 0
    key = CLOCK_KEYS.get(attr)
    return bool(key) and workgroups._gs("set", CLOCK_SCHEMA, key, "true" if on else "false")[0] == 0


# --- Sabitlenmiş programlar (GNOME "favorite-apps"; Dash to Panel de bunu gösterir) ---


def read_pinned() -> list[str]:
    code, out = workgroups._gs("get", "org.gnome.shell", "favorite-apps")
    return workgroups._parse_strv(out) if code == 0 else []


def save_pinned(apps: list[str]) -> bool:
    clean = [a for a in dict.fromkeys(apps) if a.endswith(".desktop") and "/" not in a]
    return (
        workgroups._gs("set", "org.gnome.shell", "favorite-apps", workgroups._strv(clean))[0] == 0
    )


# --- Dock (macOS düzeni; Dash to Dock anahtarları Pardus 23 şemasında doğrulandı) ---

DOCK_KEYS = {
    "position": "dock-position",
    "icon_size": "dash-max-icon-size",
    "fixed": "dock-fixed",
    "autohide": "autohide",
    "intellihide": "intellihide",
    "trash": "show-trash",
    "mounts": "show-mounts",
    "indicator": "running-indicator-style",
    "click": "click-action",
    "apps_at_top": "show-apps-at-top",
    "counter": "show-icons-notifications-counter",
    "all_monitors": "multi-monitor",
    "transparency": "transparency-mode",
    "extend": "extend-height",
}
MACOS_DOCK = {
    "dock-position": "'BOTTOM'",
    "extend-height": "false",
    "running-indicator-style": "'DOTS'",
    "click-action": "'focus-or-previews'",
    "show-apps-at-top": "true",
    "show-trash": "true",
    "show-mounts": "true",
    "transparency-mode": "'DYNAMIC'",
}
DOCK_POSITIONS = ("BOTTOM", "LEFT", "RIGHT")
DOCK_ICON_RANGE = (24, 64)
DOCK_VISIBILITY = ("always", "intellihide", "autohide")


def dock_get(key: str) -> str | None:
    code, out = _gsettings(_schema_dir("dash-to-dock@"), "get", DOCK_SCHEMA, key)
    return out.strip() if code == 0 else None


def dock_set(key: str, value: str) -> bool:
    if key not in DOCK_KEYS.values():
        return False
    code, _ = _gsettings(_schema_dir("dash-to-dock@"), "set", DOCK_SCHEMA, key, value)
    return code == 0


@dataclass
class Dock:
    position: str = "BOTTOM"
    icon_size: int = 48
    visibility: str = "always"
    trash: bool = True
    mounts: bool = True
    dots: bool = True
    counter: bool = True
    apps_at_top: bool = True
    all_monitors: bool = False


def read_dock() -> Dock:
    d = Dock()
    pos = (dock_get("dock-position") or "").strip("'")
    if pos in DOCK_POSITIONS:
        d.position = pos
    size = dock_get("dash-max-icon-size") or ""
    if size.isdigit():
        d.icon_size = int(size)
    if dock_get("dock-fixed") == "true":
        d.visibility = "always"
    elif dock_get("intellihide") == "true":
        d.visibility = "intellihide"
    else:
        d.visibility = "autohide"
    for attr, key in (
        ("trash", "show-trash"),
        ("mounts", "show-mounts"),
        ("counter", "show-icons-notifications-counter"),
        ("apps_at_top", "show-apps-at-top"),
        ("all_monitors", "multi-monitor"),
    ):
        value = dock_get(key)
        if value in ("true", "false"):
            setattr(d, attr, value == "true")
    d.dots = (dock_get("running-indicator-style") or "").strip("'") == "DOTS"
    return d


def set_dock_position(position: str) -> bool:
    return position in DOCK_POSITIONS and dock_set("dock-position", f"'{position}'")


def set_dock_icon_size(size: int) -> bool:
    size = max(DOCK_ICON_RANGE[0], min(DOCK_ICON_RANGE[1], size))
    return dock_set("dash-max-icon-size", str(size))


def set_dock_visibility(mode: str) -> bool:
    """always: hep görünür · intellihide: pencere üstüne gelince gizlenir · autohide: hep gizli."""
    if mode not in DOCK_VISIBILITY:
        return False
    fixed = mode == "always"
    ok = dock_set("dock-fixed", "true" if fixed else "false")
    ok &= dock_set("autohide", "false" if fixed else "true")
    ok &= dock_set("intellihide", "true" if mode == "intellihide" else "false")
    return ok


def set_dock_option(attr: str, on: bool) -> bool:
    if attr == "dots":
        return dock_set("running-indicator-style", "'DOTS'" if on else "'DEFAULT'")
    key = {
        "trash": "show-trash",
        "mounts": "show-mounts",
        "counter": "show-icons-notifications-counter",
        "apps_at_top": "show-apps-at-top",
        "all_monitors": "multi-monitor",
    }.get(attr)
    return bool(key) and dock_set(key, "true" if on else "false")


# --- Eklentileri açma/kapatma ---


def _enabled_extensions() -> list[str]:
    code, out = workgroups._gs("get", "org.gnome.shell", "enabled-extensions")
    return workgroups._parse_strv(out) if code == 0 else []


def set_extension_enabled(uuid: str, on: bool) -> bool:
    if on:
        return workgroups._gnome_enable_ext(uuid)
    enabled = [u for u in _enabled_extensions() if u != uuid]
    workgroups._gs("set", "org.gnome.shell", "enabled-extensions", workgroups._strv(enabled))
    workgroups._run(["gnome-extensions", "disable", uuid])
    return True


def current_preset() -> str:
    enabled = set(_enabled_extensions())
    if DTP_UUID in enabled:
        return "windows"
    uuid = dock_uuid()
    if uuid and uuid in enabled:
        return "macos"
    return "gnome"


def _save_before() -> None:
    """Hazır düzene geçmeden önceki durum; "Önceki düzene dön" kullanılana dek ilk kayıt korunur."""
    if _before_file().is_file():
        return
    snap = {
        "enabled": _enabled_extensions(),
        "dtp": {k: dtp_get(k) for k in ("panel-position", "panel-size")},
        "buttons": appearance.get("gnome", "buttons") or "",
        "dock": {k: dock_get(k) for k in DOCK_KEYS.values()} if dock_uuid() else {},
    }
    try:
        _before_file().parent.mkdir(parents=True, exist_ok=True)
        _before_file().write_text(json.dumps(snap), encoding="utf-8")
    except OSError:
        pass


def has_previous() -> bool:
    return _before_file().is_file()


def restore_previous() -> bool:
    try:
        snap = json.loads(_before_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    enabled = snap.get("enabled")
    if isinstance(enabled, list) and all(isinstance(u, str) for u in enabled):
        current = set(_enabled_extensions())
        for uuid in (DTP_UUID, dock_uuid()):
            if uuid and (uuid in enabled) != (uuid in current):
                set_extension_enabled(uuid, uuid in enabled)
    for key, value in (snap.get("dtp") or {}).items():
        if key in ("panel-position", "panel-size") and isinstance(value, str) and value:
            dtp_set(key, value)
    buttons = snap.get("buttons")
    if isinstance(buttons, str) and buttons and ";" not in buttons:
        appearance.set_value("gnome", "buttons", buttons)
    for key, value in (snap.get("dock") or {}).items():
        if key in DOCK_KEYS.values() and isinstance(value, str) and value:
            dock_set(key, value)
    _before_file().unlink(missing_ok=True)
    return True


def _wait_active(uuid: str, seconds: float = 3.0) -> bool:
    """Kabuk eklentiyi gerçekten çalıştırdı mı (yeni kurulan eklenti oturum yeniden açılmadan
    yüklenmez; o durumda durum "kapalı" kalır)."""
    import time

    deadline = time.monotonic() + seconds
    while True:
        if window_groups._shell_state(uuid) == 1:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.3)


def apply_preset(name: str) -> str:
    """ "ok" | "need_dock" (Dash to Dock kurulmalı) | "need_dtp" | "restart" (yeni kurulan eklenti
    için oturum yeniden açılmalı; düzen değiştirilmedi) | "unsupported"."""
    if name not in PRESETS:
        return "unsupported"
    dock = dock_uuid()
    if name == "windows" and not dtp_installed():
        return "need_dtp"
    if name == "macos" and not dock:
        return "need_dock"
    _save_before()
    if name == "windows":
        set_extension_enabled(DTP_UUID, True)
        if not _wait_active(DTP_UUID):
            return "restart"
        if dock:
            set_extension_enabled(dock, False)
        set_position("BOTTOM")
    elif name == "macos":
        # Önce dock açılır; çalışmazsa Dash to Panel kapatılmaz (ekran görev çubuğusuz kalmasın)
        set_extension_enabled(dock, True)
        if not _wait_active(dock):
            set_extension_enabled(dock, False)
            return "restart"
        set_extension_enabled(DTP_UUID, False)
        # macOS dock'u (kullanıcı kararı 18 Ekim 2026): altta, ortada, hep görünür; çalışan
        # programda nokta, tıklayınca öne getir; Launchpad başta; çöp kutusu ve sürücüler dock'ta.
        for key, value in MACOS_DOCK.items():
            dock_set(key, value)  # anahtar yoksa (eski sürüm) yok sayılır
        set_dock_visibility("always")
        appearance.set_value("gnome", "buttons", appearance.MACOS_BUTTON_LAYOUT)
    else:
        set_extension_enabled(DTP_UUID, False)
        if dock:
            set_extension_enabled(dock, False)
    # macOS düzeninden çıkarken solda kalan pencere düğmeleri düzenin yerine döner
    if name != "macos" and appearance.get("gnome", "buttons") == appearance.MACOS_BUTTON_LAYOUT:
        appearance.set_value(
            "gnome",
            "buttons",
            appearance.WINDOWS_BUTTON_LAYOUT
            if name == "windows"
            else appearance.GNOME_BUTTON_LAYOUT,
        )
    return "ok"


# --- Linwas eklentisi ---


def ext_dir() -> Path:
    return app_folders._data_home() / "gnome-shell" / "extensions" / EXT_UUID


def _metadata(version: int) -> str:
    if version >= window_groups.ESM_SHELL:
        versions = [str(v) for v in range(window_groups.ESM_SHELL, window_groups.MAX_SHELL + 1)]
    else:
        versions = [str(v) for v in range(window_groups.MIN_SHELL, window_groups.ESM_SHELL)]
    return json.dumps(
        {
            "uuid": EXT_UUID,
            "name": "Linwas taskbar",
            "description": "Taskbar background (transparent, matte, blur) and a media widget. "
            "Managed by Linwas.",
            "shell-version": versions,
            "version": 1,
        },
        indent=2,
    )


def build_files(version: int) -> dict[str, str]:
    kind = "esm" if version >= window_groups.ESM_SHELL else "legacy"
    read = lambda name: (_SOURCE / name).read_text(encoding="utf-8")  # noqa: E731
    return {
        "extension.js": read(f"{kind}-head.js") + read("core.js") + read(f"{kind}-tail.js"),
        "stylesheet.css": read("stylesheet.css"),
        "metadata.json": _metadata(version),
    }


def is_installed() -> bool:
    return (ext_dir() / "metadata.json").is_file()


def is_current(version: int) -> bool:
    for name, text in build_files(version).items():
        try:
            if (ext_dir() / name).read_text(encoding="utf-8") != text:
                return False
        except OSError:
            return False
    return True


def install(version: int) -> bool:
    if not window_groups.supported(version):
        return False
    if not config_file().is_file():
        save_config(load_config())
    d = ext_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, text in build_files(version).items():
        (d / name).write_text(text, encoding="utf-8")
    return workgroups._gnome_enable_ext(EXT_UUID)


def uninstall() -> None:
    set_extension_enabled(EXT_UUID, False)
    d = ext_dir()
    for name in ("extension.js", "stylesheet.css", "metadata.json"):
        (d / name).unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        d.rmdir()
    # Dash to Panel saydamlığını varsayılana döndür (eklenti değiştirmişti)
    for key in ("trans-use-custom-opacity", "trans-use-custom-bg"):
        dtp_set(key, "false")


def state(version: int) -> str:
    """ "unsupported" | "missing" | "off" | "restart" | "error" | "active"."""
    if not window_groups.supported(version):
        return "unsupported"
    if not is_installed():
        return "missing"
    if not workgroups._gnome_ext_enabled(EXT_UUID):
        return "off"
    st = window_groups._shell_state(EXT_UUID)
    if st is None:
        return "restart"
    if st == 1:
        return "active"
    if st == 3:
        return "error"
    return "restart"


def valid_hex(color: str) -> bool:
    return bool(re.match(r"^#[0-9a-fA-F]{6}$", color))
