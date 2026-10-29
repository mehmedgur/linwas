# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Çalışma grupları (kararlar.md › Yeni özellikler › 9 › A).

Her grup bir sanal masaüstüdür (grup sırası = masaüstü sırası). Görev çubuğu yalnızca geçerli
masaüstünün pencerelerini gösterir; grup değiştirici panelde durur; gruba eklenen programlar
istenirse hep o grupta açılır; "Grubu aç" o masaüstüne geçip programları başlatır.

Masaüstüne özel parçalar (doğrulanan anahtarlar):
- GNOME: org.gnome.mutter dynamic-workspaces, org.gnome.desktop.wm.preferences num-workspaces ve
  workspace-names; görev çubuğu: Dash to Panel / Dash to Dock `isolate-workspaces`, window-list
  `display-all-workspaces`; değiştirici: workspace-indicator eklentisi; kural: auto-move-windows
  eklentisi `application-list` ("firefox.desktop:2", 1'den başlar).
- XFCE: xfconf xfwm4 /general/workspace_count, /general/workspace_names; xfce4-panel tasklist
  `include-all-workspaces`; değiştirici: `xfce4-panel --add=pager`; kural: Linwas ajanı.
- Cinnamon: org.cinnamon.desktop.wm.preferences num-workspaces, workspace-names; pencere listesi
  uygulamacıkları ~/.config/cinnamon/spices/<uuid>/<kopya>.json `show-all-workspaces`;
  değiştirici: org.cinnamon enabled-applets'e workspace-switcher@cinnamon.org; kural: Linwas ajanı.
Ortak (X11): `wmctrl` ile geçiş (-s), pencere listesi (-lx) ve taşıma (-i -r … -t).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from linwas.backend import app_folders
from linwas.backend.app_folders import AppEntry

MAX_GROUPS = 12
MAX_NAME_LEN = 30
_RE_ID = re.compile(r"^[0-9a-f]{8}$")

GNOME_EXT_DIRS = (
    Path("/usr/share/gnome-shell/extensions"),
    Path.home() / ".local/share/gnome-shell/extensions",
)
AUTO_MOVE_UUID = "auto-move-windows@gnome-shell-extensions.gcampax.github.com"
INDICATOR_UUID = "workspace-indicator@gnome-shell-extensions.gcampax.github.com"
GNOME_EXTENSIONS_PACKAGE = "gnome-shell-extensions"
# (eklenti UUID'si, şema) — görev çubuğunda yalnızca geçerli masaüstü
GNOME_TASKBARS = (
    (
        "dash-to-panel@jderose9.github.com",
        "org.gnome.shell.extensions.dash-to-panel",
        "isolate-workspaces",
        "true",
    ),
    (
        "dash-to-dock@micxgx.gmail.com",
        "org.gnome.shell.extensions.dash-to-dock",
        "isolate-workspaces",
        "true",
    ),
    (
        "ubuntu-dock@ubuntu.com",
        "org.gnome.shell.extensions.dash-to-dock",
        "isolate-workspaces",
        "true",
    ),
    (
        "window-list@gnome-shell-extensions.gcampax.github.com",
        "org.gnome.shell.extensions.window-list",
        "display-all-workspaces",
        "false",
    ),
)
CINNAMON_WINDOW_LISTS = ("grouped-window-list@cinnamon.org", "window-list@cinnamon.org")
CINNAMON_SWITCHER = "workspace-switcher@cinnamon.org"


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
            env={**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout


def _strv(values: list[str]) -> str:
    """GVariant "as" metni."""
    return (
        "["
        + ", ".join("'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'" for v in values)
        + "]"
    )


def _parse_strv(text: str) -> list[str]:
    return [m.replace("\\'", "'") for m in re.findall(r"'((?:[^'\\]|\\.)*)'", text)]


# --- Kayıt ---


@dataclass
class WorkGroup:
    id: str
    name: str
    apps: list[str] = field(default_factory=list)  # app_folders başvuruları
    keep_apps_here: bool = True  # programlar hep bu grupta açılsın


def groups_file() -> Path:
    return app_folders.data_dir() / "workgroups.json"


def state_file() -> Path:
    """Gruplar açılmadan önceki masaüstü ayarları (kapatınca geri yüklenir)."""
    return app_folders.data_dir() / "workgroups-before.json"


def _clean_name(name: str) -> str:
    name = " ".join(str(name).split())[:MAX_NAME_LEN]
    return "".join(c for c in name if ord(c) >= 32)


def load_groups() -> list[WorkGroup]:
    try:
        data = json.loads(groups_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    groups: list[WorkGroup] = []
    for raw in data.get("groups", []) if isinstance(data, dict) else []:
        if not isinstance(raw, dict) or not _RE_ID.match(str(raw.get("id", ""))):
            continue
        apps = [a for a in raw.get("apps", []) if isinstance(a, str) and a.endswith(".desktop")]
        groups.append(
            WorkGroup(
                id=raw["id"],
                name=_clean_name(raw.get("name", "")) or "Group",
                apps=list(dict.fromkeys(apps)),
                keep_apps_here=raw.get("keep_apps_here", True) is not False,
            )
        )
    return groups[:MAX_GROUPS]


def save_groups(groups: list[WorkGroup]) -> None:
    path = groups_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"version": 1, "groups": [asdict(g) for g in groups]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def new_group(groups: list[WorkGroup], name: str) -> WorkGroup:
    group = WorkGroup(id=uuid.uuid4().hex[:8], name=_clean_name(name) or "Group")
    groups.append(group)
    return group


# --- X11 pencere yönetimi (wmctrl) ---


def is_x11() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11" or (
        bool(os.environ.get("DISPLAY")) and not os.environ.get("WAYLAND_DISPLAY")
    )


def has_wmctrl() -> bool:
    return shutil.which("wmctrl") is not None


def can_control_windows() -> bool:
    return is_x11() and has_wmctrl()


@dataclass
class Window:
    id: str  # onaltılık pencere kimliği
    workspace: int  # -1: bütün masaüstlerinde
    wm_class: str  # "örnek.Sınıf"
    title: str


def list_windows() -> list[Window]:
    code, out = _run(["wmctrl", "-lx"])
    if code != 0:
        return []
    windows = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4 or not parts[1].lstrip("-").isdigit():
            continue
        title = parts[4] if len(parts) > 4 else ""
        windows.append(Window(parts[0], int(parts[1]), parts[2], title))
    return windows


def current_workspace() -> int:
    code, out = _run(["wmctrl", "-d"])
    for line in out.splitlines() if code == 0 else []:
        parts = line.split()
        if len(parts) > 1 and parts[1] == "*":
            return int(parts[0])
    return -1


def switch_to(index: int) -> bool:
    return can_control_windows() and _run(["wmctrl", "-s", str(index)])[0] == 0


def move_window(window_id: str, index: int) -> bool:
    if not re.fullmatch(r"0x[0-9a-fA-F]+", window_id):
        return False
    return (
        can_control_windows() and _run(["wmctrl", "-i", "-r", window_id, "-t", str(index)])[0] == 0
    )


def remap_windows(mapping: dict[int, int]) -> None:
    """Grup sırası değişince ya da grup silinince pencereleri yeni masaüstü sırasına taşır
    ({eski sıra: yeni sıra}; X11). Wayland'de pencere masaüstü yöneticisinin elinde kalır."""
    if not can_control_windows():
        return
    for window in list_windows():
        new = mapping.get(window.workspace)
        if window.workspace >= 0 and new is not None and new != window.workspace:
            move_window(window.id, new)


def _desktop_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return values
    in_entry = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
        elif in_entry and "=" in line:
            k, _, v = line.partition("=")
            values.setdefault(k.strip(), v.strip())
    return values


def wm_class_keys(entry: AppEntry) -> set[str]:
    """Programın pencere sınıfı adayları: StartupWMClass, masaüstü kimliği, Exec komutu."""
    values = _desktop_values(entry.path)
    keys = {Path(entry.ref).stem.lower()}
    if values.get("StartupWMClass"):
        keys.add(values["StartupWMClass"].lower())
    exec_line = values.get("Exec", "").split()
    if exec_line:
        cmd = exec_line[1] if exec_line[0] == "env" and len(exec_line) > 1 else exec_line[0]
        keys.add(Path(cmd).name.lower())
    # Flatpak kimliği (org.mozilla.firefox) → son parça da aday
    keys |= {k.rsplit(".", 1)[-1] for k in list(keys) if "." in k}
    return {k for k in keys if k}


def window_matches(window: Window, keys: set[str]) -> bool:
    parts = {p.lower() for p in window.wm_class.split(".") if p}
    parts.add(window.wm_class.lower())
    return bool(parts & keys)


# --- Masaüstüne özel ayarlar ---


def desktop_kind() -> str:
    """ "gnome" | "xfce" | "cinnamon" | "" (desteklenmiyor)."""
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    if "X-CINNAMON" in current or "CINNAMON" in current:
        return "cinnamon"
    if "XFCE" in current:
        return "xfce"
    if "GNOME" in current:
        return "gnome"
    return ""


def _gs(*args: str, schemadir: Path | None = None) -> tuple[int, str]:
    cmd = ["gsettings"] + (["--schemadir", str(schemadir)] if schemadir else []) + list(args)
    return _run(cmd)


def _xfconf(*args: str) -> tuple[int, str]:
    return _run(["xfconf-query", *args])


def _gnome_ext_dir(ext_uuid: str) -> Path | None:
    for base in GNOME_EXT_DIRS:
        d = base / ext_uuid
        if d.is_dir():
            return d
    return None


def _gnome_ext_enabled(ext_uuid: str) -> bool:
    code, out = _gs("get", "org.gnome.shell", "enabled-extensions")
    return code == 0 and ext_uuid in _parse_strv(out)


def _gnome_enable_ext(ext_uuid: str) -> bool:
    if _run(["gnome-extensions", "enable", ext_uuid])[0] == 0:
        return True
    code, out = _gs("get", "org.gnome.shell", "enabled-extensions")
    if code != 0:
        return False
    enabled = _parse_strv(out)
    if ext_uuid not in enabled:
        enabled.append(ext_uuid)
    return _gs("set", "org.gnome.shell", "enabled-extensions", _strv(enabled))[0] == 0


def _gnome_ext_gs(ext_uuid: str, schema: str, *args: str) -> tuple[int, str]:
    """Eklenti şeması sistemde derlenmiş değilse eklentinin kendi schemas/ klasöründen."""
    code, out = _gs(*args[:1], schema, *args[1:])
    if code == 0:
        return code, out
    d = _gnome_ext_dir(ext_uuid)
    if d and (d / "schemas").is_dir():
        return _gs(*args[:1], schema, *args[1:], schemadir=d / "schemas")
    return 1, ""


def workspace_names() -> list[str]:
    kind = desktop_kind()
    if kind in ("gnome", "cinnamon"):
        schema = (
            "org.gnome.desktop.wm.preferences"
            if kind == "gnome"
            else "org.cinnamon.desktop.wm.preferences"
        )
        return _parse_strv(_gs("get", schema, "workspace-names")[1])
    if kind == "xfce":
        code, out = _xfconf("-c", "xfwm4", "-p", "/general/workspace_names")
        if code == 0:
            lines = out.splitlines()
            return [ln for ln in lines[2:] if ln] if len(lines) > 2 else []
    return []


def _snapshot() -> dict[str, str]:
    """Gruplar açılmadan önceki değerler (geri yüklemek için)."""
    kind = desktop_kind()
    snap: dict[str, str] = {"kind": kind}
    if kind == "gnome":
        snap["dynamic"] = _gs("get", "org.gnome.mutter", "dynamic-workspaces")[1].strip()
        snap["count"] = _gs("get", "org.gnome.desktop.wm.preferences", "num-workspaces")[1].strip()
        snap["names"] = _gs("get", "org.gnome.desktop.wm.preferences", "workspace-names")[1].strip()
    elif kind == "cinnamon":
        snap["count"] = _gs("get", "org.cinnamon.desktop.wm.preferences", "num-workspaces")[
            1
        ].strip()
        snap["names"] = _gs("get", "org.cinnamon.desktop.wm.preferences", "workspace-names")[
            1
        ].strip()
    elif kind == "xfce":
        snap["count"] = _xfconf("-c", "xfwm4", "-p", "/general/workspace_count")[1].strip()
        snap["names"] = json.dumps(workspace_names(), ensure_ascii=False)
    return snap


def set_workspaces(names: list[str]) -> bool:
    """Masaüstü sayısını gruplara eşitler ve adlarını yazar."""
    if not names:
        return False
    if not state_file().exists():
        state_file().parent.mkdir(parents=True, exist_ok=True)
        state_file().write_text(json.dumps(_snapshot(), ensure_ascii=False), encoding="utf-8")
    kind = desktop_kind()
    count = str(len(names))
    if kind == "gnome":
        _gs("set", "org.gnome.mutter", "dynamic-workspaces", "false")
        ok = _gs("set", "org.gnome.desktop.wm.preferences", "num-workspaces", count)[0] == 0
        return (
            _gs("set", "org.gnome.desktop.wm.preferences", "workspace-names", _strv(names))[0] == 0
            and ok
        )
    if kind == "cinnamon":
        ok = _gs("set", "org.cinnamon.desktop.wm.preferences", "num-workspaces", count)[0] == 0
        return (
            _gs("set", "org.cinnamon.desktop.wm.preferences", "workspace-names", _strv(names))[0]
            == 0
            and ok
        )
    if kind == "xfce":
        ok = (
            _xfconf("-c", "xfwm4", "-p", "/general/workspace_count", "-t", "int", "-s", count)[0]
            == 0
        )
        args = ["-c", "xfwm4", "-p", "/general/workspace_names", "-n", "--force-array"]
        for n in names:
            args += ["-t", "string", "-s", n]
        return _xfconf(*args)[0] == 0 and ok
    return False


def restore_workspaces() -> None:
    """Grupların hepsi silinince eski masaüstü ayarlarını geri yükler."""
    try:
        snap = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    kind = snap.get("kind")
    if kind == "gnome":
        if snap.get("dynamic"):
            _gs("set", "org.gnome.mutter", "dynamic-workspaces", snap["dynamic"])
        if snap.get("count"):
            _gs("set", "org.gnome.desktop.wm.preferences", "num-workspaces", snap["count"])
        _gs("set", "org.gnome.desktop.wm.preferences", "workspace-names", snap.get("names") or "[]")
    elif kind == "cinnamon":
        if snap.get("count"):
            _gs("set", "org.cinnamon.desktop.wm.preferences", "num-workspaces", snap["count"])
        _gs(
            "set",
            "org.cinnamon.desktop.wm.preferences",
            "workspace-names",
            snap.get("names") or "[]",
        )
    elif kind == "xfce":
        if snap.get("count", "").isdigit():
            _xfconf(
                "-c", "xfwm4", "-p", "/general/workspace_count", "-t", "int", "-s", snap["count"]
            )
        names = json.loads(snap.get("names") or "[]")
        if names:
            args = ["-c", "xfwm4", "-p", "/general/workspace_names", "-n", "--force-array"]
            for n in names:
                args += ["-t", "string", "-s", n]
            _xfconf(*args)
    state_file().unlink(missing_ok=True)


# --- Görev çubuğu: yalnızca geçerli masaüstü ---


def _xfce_tasklists() -> list[str]:
    code, out = _xfconf("-c", "xfce4-panel", "-l")
    plugins = (
        [p for p in out.splitlines() if re.fullmatch(r"/plugins/plugin-\d+", p)]
        if code == 0
        else []
    )
    return [p for p in plugins if _xfconf("-c", "xfce4-panel", "-p", p)[1].strip() == "tasklist"]


def _xfce_has_plugin(name: str) -> bool:
    code, out = _xfconf("-c", "xfce4-panel", "-l")
    for p in out.splitlines() if code == 0 else []:
        if (
            re.fullmatch(r"/plugins/plugin-\d+", p)
            and _xfconf("-c", "xfce4-panel", "-p", p)[1].strip() == name
        ):
            return True
    return False


def _cinnamon_list_files() -> list[Path]:
    base = (
        Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "cinnamon" / "spices"
    )
    return [f for u in CINNAMON_WINDOW_LISTS for f in (base / u).glob("*.json")]


def taskbar_isolated() -> bool | None:
    """Görev çubuğu yalnızca geçerli masaüstünü gösteriyor mu; bulunamazsa None."""
    kind = desktop_kind()
    if kind == "gnome":
        found = None
        for ext, schema, key, want in GNOME_TASKBARS:
            if not _gnome_ext_enabled(ext):
                continue
            code, out = _gnome_ext_gs(ext, schema, "get", key)
            if code == 0:
                found = (found is not False) and out.strip() == want
        return found
    if kind == "xfce":
        lists = _xfce_tasklists()
        if not lists:
            return None
        return all(
            _xfconf("-c", "xfce4-panel", "-p", f"{p}/include-all-workspaces")[1].strip() != "true"
            for p in lists
        )
    if kind == "cinnamon":
        for f in _cinnamon_list_files():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("show-all-workspaces", {}).get("value") is True:
                return False
        return True  # varsayılan: yalnızca geçerli masaüstü (settings-schema.json)
    return None


def isolate_taskbar() -> bool:
    kind = desktop_kind()
    ok = False
    if kind == "gnome":
        for ext, schema, key, want in GNOME_TASKBARS:
            if _gnome_ext_enabled(ext):
                ok |= _gnome_ext_gs(ext, schema, "set", key, want)[0] == 0
    elif kind == "xfce":
        for p in _xfce_tasklists():
            ok |= (
                _xfconf(
                    "-c",
                    "xfce4-panel",
                    "-p",
                    f"{p}/include-all-workspaces",
                    "-n",
                    "-t",
                    "bool",
                    "-s",
                    "false",
                )[0]
                == 0
            )
    elif kind == "cinnamon":
        ok = True
        for f in _cinnamon_list_files():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if "show-all-workspaces" in data:
                    data["show-all-workspaces"]["value"] = False
                    f.write_text(json.dumps(data, indent=4), encoding="utf-8")
            except (OSError, json.JSONDecodeError, TypeError):
                ok = False
    return ok


# --- Grup değiştirici (panelde) ---


def switcher_state() -> str:
    """ "enabled" | "available" (eklenebilir) | "missing" (paket gerekli) | "unsupported"."""
    kind = desktop_kind()
    if kind == "gnome":
        if _gnome_ext_dir(INDICATOR_UUID) is None:
            return "missing"
        return "enabled" if _gnome_ext_enabled(INDICATOR_UUID) else "available"
    if kind == "xfce":
        return "enabled" if _xfce_has_plugin("pager") else "available"
    if kind == "cinnamon":
        code, out = _gs("get", "org.cinnamon", "enabled-applets")
        return "enabled" if code == 0 and CINNAMON_SWITCHER in out else "available"
    return "unsupported"


def add_switcher() -> bool:
    kind = desktop_kind()
    if kind == "gnome":
        return _gnome_enable_ext(INDICATOR_UUID)
    if kind == "xfce":
        try:
            subprocess.Popen(["xfce4-panel", "--add=pager"], start_new_session=True, shell=False)
        except OSError:
            return False
        return True
    if kind == "cinnamon":
        code, out = _gs("get", "org.cinnamon", "enabled-applets")
        if code != 0:
            return False
        applets = _parse_strv(out)
        if any(CINNAMON_SWITCHER in a for a in applets):
            return True
        applets.append(f"panel1:right:0:{CINNAMON_SWITCHER}")
        return _gs("set", "org.cinnamon", "enabled-applets", _strv(applets))[0] == 0
    return False


# --- Programlar hep kendi grubunda ---

AGENT_AUTOSTART = "linwas-workgroups.desktop"


def _autostart_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart"


def rules(groups: list[WorkGroup]) -> dict[str, int]:
    """{program başvurusu: masaüstü sırası (0'dan)}; bir program yalnızca ilk grubunda."""
    out: dict[str, int] = {}
    for i, g in enumerate(groups):
        if g.keep_apps_here:
            for ref in g.apps:
                out.setdefault(ref, i)
    return out


def apply_rules(groups: list[WorkGroup]) -> bool:
    """GNOME: auto-move-windows eklentisi (Wayland'de de çalışır); XFCE/Cinnamon: Linwas ajanı."""
    table = rules(groups)
    kind = desktop_kind()
    if kind == "gnome":
        # Yalnızca menüdeki programlar (eklenti uygulama kimliğiyle eşleştirir)
        entries = [f"{ref}:{i + 1}" for ref, i in table.items() if not ref.startswith("/")]
        schema = "org.gnome.shell.extensions.auto-move-windows"
        code, out = _gnome_ext_gs(AUTO_MOVE_UUID, schema, "get", "application-list")
        if code != 0:
            return False
        ours = {ref for g in groups for ref in g.apps}
        kept = [e for e in _parse_strv(out) if e.rsplit(":", 1)[0] not in ours]
        _gnome_ext_gs(AUTO_MOVE_UUID, schema, "set", "application-list", _strv(kept + entries))
        return _gnome_enable_ext(AUTO_MOVE_UUID) if entries else True
    if kind in ("xfce", "cinnamon"):
        path = _autostart_dir() / AGENT_AUTOSTART
        if table:
            cmd = " ".join(app_folders._quote(a) for a in app_folders.exec_command())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Linwas work groups\n"
                "Name[tr]=Linwas çalışma grupları\n"
                f"Exec={cmd} --workgroups-agent\nNoDisplay=true\nOnlyShowIn=XFCE;X-Cinnamon;\n",
                encoding="utf-8",
            )
            start_agent()
        else:
            path.unlink(missing_ok=True)
        return True
    return False


def start_agent() -> None:
    """Ajan çalışmıyorsa başlatır (oturum açılınca autostart da başlatır)."""
    if _run(["pgrep", "-u", str(os.getuid()), "-f", "--", "--workgroups-agent"])[0] == 0:
        return
    with contextlib.suppress(OSError):
        subprocess.Popen(
            [*app_folders.exec_command(), "--workgroups-agent"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            shell=False,
        )


def run_agent() -> int:
    """X11 ajanı: yeni açılan pencereyi kuralına göre kendi grubuna taşır (1 sn'de bir)."""
    if not can_control_windows():
        return 1
    seen = {w.id for w in list_windows()}  # açılışta var olanlara dokunulmaz
    table_mtime = -1.0
    keys: list[tuple[set[str], int]] = []
    while True:
        try:
            mtime = groups_file().stat().st_mtime
        except OSError:
            return 0  # gruplar silindi
        if mtime != table_mtime:
            table_mtime = mtime
            keys = []
            for ref, index in rules(load_groups()).items():
                entry = app_folders.app_entry(ref)
                if entry:
                    keys.append((wm_class_keys(entry), index))
            if not keys:
                return 0
        for window in list_windows():
            if window.id in seen:
                continue
            seen.add(window.id)
            if window.workspace < 0:
                continue
            for k, index in keys:
                if window_matches(window, k) and window.workspace != index:
                    move_window(window.id, index)
                    break
        time.sleep(1)


# --- Grubu aç ---


def open_group(groups: list[WorkGroup], group_id: str) -> bool:
    """Gruba geçer (X11) ve o grupta penceresi olmayan programları başlatır."""
    index = next((i for i, g in enumerate(groups) if g.id == group_id), -1)
    if index < 0:
        return False
    switch_to(index)
    windows = [w for w in list_windows() if w.workspace == index] if can_control_windows() else []
    for ref in groups[index].apps:
        entry = app_folders.app_entry(ref)
        if entry is None:
            continue
        if windows and any(window_matches(w, wm_class_keys(entry)) for w in windows):
            continue
        app_folders.launch(entry)
    return True


# --- Menü kısayolu (her masaüstünde panele/favorilere sabitlenebilir) ---


def launcher_path(group: WorkGroup) -> Path:
    return app_folders.user_apps_dir() / f"linwas-group-{group.id}.desktop"


def refresh_launchers() -> None:
    """Komutu eskimiş grup kısayollarını ve X11 ajanının autostart dosyasını yeniden yazar
    (ör. kaynak koddan çalışırken yazılmış, sonra paket kurulmuş)."""
    cmd = " ".join(app_folders._quote(a) for a in app_folders.exec_command())
    stale = False
    for path in app_folders.user_apps_dir().glob("linwas-group-*.desktop"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if f"Exec={cmd} --open-group " not in text:
            stale = True
            break
    if stale:
        write_launchers(load_groups())
    agent = _autostart_dir() / AGENT_AUTOSTART
    try:
        text = agent.read_text(encoding="utf-8")
    except OSError:
        return
    exec_line = f"Exec={cmd} --workgroups-agent\n"
    if exec_line not in text:
        lines = [
            exec_line if line.startswith("Exec=") else line
            for line in text.splitlines(keepends=True)
        ]
        agent.write_text("".join(lines), encoding="utf-8")


def write_launchers(groups: list[WorkGroup]) -> None:
    folder = app_folders.user_apps_dir()
    folder.mkdir(parents=True, exist_ok=True)
    keep = set()
    cmd = " ".join(app_folders._quote(a) for a in app_folders.exec_command())
    for group in groups:
        path = launcher_path(group)
        keep.add(path.name)
        name = group.name.replace("\n", " ")
        path.write_text(
            "[Desktop Entry]\nType=Application\n"
            f"Name={name}\nGenericName=Linwas work group\nGenericName[tr]=Linwas çalışma grubu\n"
            f"Exec={cmd} --open-group {group.id}\nIcon=view-grid-symbolic\nTerminal=false\n"
            "Categories=Utility;\n",
            encoding="utf-8",
        )
    for old in folder.glob("linwas-group-*.desktop"):
        if old.name not in keep:
            old.unlink(missing_ok=True)


def apply_all(groups: list[WorkGroup], previous: list[str] | None = None) -> None:
    """Grupları kaydeder ve masaüstüne uygular. `previous`: değişiklikten önceki grup kimlikleri
    (sırası değişen ya da silinen grupların pencereleri taşınsın diye)."""
    if previous:
        new_ids = [g.id for g in groups]
        mapping = {
            old: (new_ids.index(gid) if gid in new_ids else 0) for old, gid in enumerate(previous)
        }
        # Masaüstü sayısı azalmadan önce taşınır (silinen masaüstündekiler kaybolmasın)
        remap_windows(mapping)
    save_groups(groups)
    write_launchers(groups)
    if groups:
        set_workspaces([g.name for g in groups])
        apply_rules(groups)
    else:
        apply_rules([])
        restore_workspaces()
