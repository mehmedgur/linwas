"""Pencere gruplama eklentisi (kararlar.md › Yeni özellikler › 9 › B).

Farklı programların pencerelerini kullanıcının seçtiği tek düğmede birleştirir; düğmeye
tıklayınca önizlemeli pencere listesi açılır. Şimdilik yalnızca GNOME Shell (42–48).

- Kayıt: ~/.local/share/linwas/window-groups.json (eklenti bu dosyayı izler, değişince yenilenir).
- Eklenti: ~/.local/share/gnome-shell/extensions/<UUID>/. Kaynağı resources/gnome-extension/:
  ortak çekirdek (core.js) + GNOME 42–44 için eski içe aktarma başlığı/sonu, 45+ için ES modülü
  başlığı/sonu; kurulumda kabuk sürümüne göre birleştirilir.
- Dash to Panel açıksa gruba alınmış programlar onun görev çubuğundan gizlenir.
- Durum: org.gnome.Shell.Extensions.GetExtensionInfo (state 1 = çalışıyor; boş sözlük = kabuk
  eklentiyi henüz tanımıyor, oturum yeniden açılmalı).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from linwas.backend import app_folders, workgroups

EXT_UUID = "linwas-window-groups@linwas"
DTP_UUID = "dash-to-panel@jderose9.github.com"
MIN_SHELL = 42
ESM_SHELL = 45  # GNOME 45'ten itibaren eklentiler ES modülü
MAX_SHELL = 48
MAX_GROUPS = 12
MAX_NAME_LEN = 30
_RE_ID = re.compile(r"^[0-9a-f]{8}$")
_SOURCE = Path(__file__).resolve().parent.parent / "resources" / "gnome-extension"


@dataclass
class WindowGroup:
    id: str
    name: str
    apps: list[str] = field(default_factory=list)  # masaüstü kimlikleri (firefox.desktop)


def groups_file() -> Path:
    return app_folders.data_dir() / "window-groups.json"


def _clean_name(name: str) -> str:
    name = " ".join(str(name).split())[:MAX_NAME_LEN]
    return "".join(c for c in name if ord(c) >= 32)


def load_groups() -> list[WindowGroup]:
    try:
        data = json.loads(groups_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    groups: list[WindowGroup] = []
    raw_groups = data.get("groups", []) if isinstance(data, dict) else []
    for raw in raw_groups:
        if not isinstance(raw, dict) or not _RE_ID.match(str(raw.get("id", ""))):
            continue
        apps = [
            a
            for a in raw.get("apps", [])
            if isinstance(a, str) and a.endswith(".desktop") and not a.startswith("/")
        ]
        name = _clean_name(raw.get("name", ""))
        if name:
            groups.append(WindowGroup(id=raw["id"], name=name, apps=apps))
    return groups[:MAX_GROUPS]


def save_groups(groups: list[WindowGroup], strings: dict[str, str] | None = None) -> None:
    """Grupları yazar; `strings`: eklentinin göstereceği çevrilmiş metinler."""
    path = groups_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"groups": [asdict(g) for g in groups[:MAX_GROUPS]], "strings": strings or {}}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def new_group(groups: list[WindowGroup], name: str) -> WindowGroup:
    group = WindowGroup(id=uuid.uuid4().hex[:8], name=_clean_name(name))
    groups.append(group)
    return group


# --- Eklenti ---


def shell_version() -> int:
    """GNOME Shell ana sürümü (bilinmiyorsa 0)."""
    code, out = workgroups._run(["gnome-shell", "--version"])
    m = re.search(r"(\d+)(?:\.\d+)*", out) if code == 0 else None
    return int(m.group(1)) if m else 0


def supported(version: int) -> bool:
    return workgroups.desktop_kind() == "gnome" and MIN_SHELL <= version <= MAX_SHELL


def ext_dir() -> Path:
    return app_folders._data_home() / "gnome-shell" / "extensions" / EXT_UUID


def _metadata(version: int) -> str:
    if version >= ESM_SHELL:
        versions = [str(v) for v in range(ESM_SHELL, MAX_SHELL + 1)]
    else:
        versions = [str(v) for v in range(MIN_SHELL, ESM_SHELL)]
    return json.dumps(
        {
            "uuid": EXT_UUID,
            "name": "Linwas window groups",
            "description": "Groups the windows of chosen programs under one panel button. "
            "Managed by Linwas.",
            "shell-version": versions,
            "version": 1,
        },
        indent=2,
    )


def build_files(version: int) -> dict[str, str]:
    """Kabuk sürümüne uygun eklenti dosyaları (ad → içerik)."""
    kind = "esm" if version >= ESM_SHELL else "legacy"
    read = lambda name: (_SOURCE / name).read_text(encoding="utf-8")  # noqa: E731
    return {
        "extension.js": read(f"{kind}-head.js") + read("core.js") + read(f"{kind}-tail.js"),
        "stylesheet.css": read("stylesheet.css"),
        "metadata.json": _metadata(version),
    }


def is_installed() -> bool:
    return (ext_dir() / "metadata.json").is_file()


def is_current(version: int) -> bool:
    """Kurulu eklenti bu Linwas sürümünün ürettiğiyle aynı mı."""
    for name, text in build_files(version).items():
        try:
            if (ext_dir() / name).read_text(encoding="utf-8") != text:
                return False
        except OSError:
            return False
    return True


def install(version: int) -> bool:
    """Eklentiyi kullanıcı klasörüne yazar ve açar (ilk kurulumda oturum yeniden açılmalı)."""
    if not supported(version):
        return False
    d = ext_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, text in build_files(version).items():
        (d / name).write_text(text, encoding="utf-8")
    return workgroups._gnome_enable_ext(EXT_UUID)


def uninstall() -> None:
    code, out = workgroups._gs("get", "org.gnome.shell", "enabled-extensions")
    if code == 0:
        enabled = [u for u in workgroups._parse_strv(out) if u != EXT_UUID]
        workgroups._gs("set", "org.gnome.shell", "enabled-extensions", workgroups._strv(enabled))
    workgroups._run(["gnome-extensions", "disable", EXT_UUID])
    d = ext_dir()
    for name in ("extension.js", "stylesheet.css", "metadata.json"):
        (d / name).unlink(missing_ok=True)
    with contextlib.suppress(OSError):
        d.rmdir()


def _shell_state(ext_uuid: str) -> float | None:
    """Kabuğun bildirdiği eklenti durumu; kabuk eklentiyi tanımıyorsa None."""
    code, out = workgroups._run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Shell.Extensions",
            "--object-path",
            "/org/gnome/Shell/Extensions",
            "--method",
            "org.gnome.Shell.Extensions.GetExtensionInfo",
            ext_uuid,
        ]
    )
    m = re.search(r"'state':\s*<([\d.]+)>", out) if code == 0 else None
    return float(m.group(1)) if m else None


def state(version: int) -> str:
    """ "unsupported" | "missing" | "off" | "restart" | "error" | "active"."""
    if not supported(version):
        return "unsupported"
    if not is_installed():
        return "missing"
    if not workgroups._gnome_ext_enabled(EXT_UUID):
        return "off"
    st = _shell_state(EXT_UUID)
    if st is None:
        return "restart"
    if st == 1:
        return "active"
    if st == 3:
        return "error"
    return "restart"


def dash_to_panel_active() -> bool:
    return _shell_state(DTP_UUID) == 1
