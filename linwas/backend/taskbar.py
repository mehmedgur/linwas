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

from linwas.backend import app_folders, window_groups, workgroups

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


def write_palette(light: dict[str, str], dark: dict[str, str], accent: str) -> None:
    """Linwas'ın açık/koyu renklerini ve vurgu rengini eklentiye verir."""
    cfg = load_config()
    palette = {"light": light, "dark": dark, "accent": accent}
    if cfg.palette != palette:
        cfg.palette = palette
        save_config(cfg)


def sync_palette(light: dict[str, str], dark: dict[str, str], accent: str) -> None:
    """Renkleri günceller (değişmediyse dosyaya yazılmaz)."""
    write_palette(light, dark, accent)


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


def read_layout() -> Layout:
    lay = Layout()
    pos = (dtp_get("panel-position") or "").strip("'")
    if pos in POSITIONS:
        lay.position = pos
    size = dtp_get("panel-size") or ""
    if size.isdigit():
        lay.size = int(size)
    lay.autohide = dtp_get("intellihide") == "true"
    lay.previews = dtp_get("show-window-previews") != "false"
    return lay


def set_position(position: str) -> bool:
    if position not in POSITIONS:
        return False
    # Ekran başına ayar (panel-positions) boşsa genel değer kullanılır
    dtp_set("panel-positions", "'{}'")
    return dtp_set("panel-position", f"'{position}'")


def set_size(size: int) -> bool:
    size = max(SIZE_RANGE[0], min(SIZE_RANGE[1], size))
    dtp_set("panel-sizes", "'{}'")
    return dtp_set("panel-size", str(size))


def set_autohide(on: bool) -> bool:
    return dtp_set("intellihide", "true" if on else "false")


def set_previews(on: bool) -> bool:
    return dtp_set("show-window-previews", "true" if on else "false")


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
    snap = {
        "enabled": _enabled_extensions(),
        "dtp": {k: dtp_get(k) for k in ("panel-position", "panel-size")},
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
    _before_file().unlink(missing_ok=True)
    return True


def apply_preset(name: str) -> str:
    """ "ok" | "need_dock" (Dash to Dock kurulmalı) | "need_dtp" | "unsupported"."""
    if name not in PRESETS:
        return "unsupported"
    dock = dock_uuid()
    if name == "windows" and not dtp_installed():
        return "need_dtp"
    if name == "macos" and not dock:
        return "need_dock"
    _save_before()
    if name == "windows":
        if dock:
            set_extension_enabled(dock, False)
        set_extension_enabled(DTP_UUID, True)
        set_position("BOTTOM")
    elif name == "macos":
        set_extension_enabled(DTP_UUID, False)
        set_extension_enabled(dock, True)
        schema = _schema_dir("dash-to-dock@")
        for key, value in (
            ("dock-position", "'BOTTOM'"),
            ("extend-height", "false"),
            ("dock-fixed", "false"),
        ):
            _gsettings(schema, "set", DOCK_SCHEMA, key, value)  # anahtar yoksa yok sayılır
    else:
        set_extension_enabled(DTP_UUID, False)
        if dock:
            set_extension_enabled(dock, False)
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
