# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Wine ile Windows programı açma (kullanıcı yetkisiyle; kabuk kullanılmaz).

Ortam (WINEPREFIX) yaklaşımı — karma:
- Varsayılan tek ortak ortam: ~/.local/share/linwas/wine/shared
- Yüksek riskli program ya da ortak ortamda sorun çıkaran program ayrı ortama alınır;
  kullanıcı da "Ayrı ortamda aç" diyebilir: ~/.local/share/linwas/wine/<ad>
Her ortamın kökünde linwas.json (ad, oluşturulma nedeni) tutulur.

Wine kurulan programlar için menü kısayolları (.desktop) oluşturur; bunlar
~/.local/share/applications/wine/ altından okunur, Linwas ortamlarına ait olanlar listelenir.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SHARED_ID = "shared"
META_FILE = "linwas.json"

# Wine kurulumu (Debian/Ubuntu/Pardus deposu): 32 bit programlar için wine32:i386 gerekir
WINE_PACKAGES = ("wine", "wine64", "wine32:i386")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def base_dir() -> Path:
    return _data_home() / "linwas" / "wine"


def wine_available() -> bool:
    return shutil.which("wine") is not None


def slug(name: str) -> str:
    """Ortam klasör adı: küçük harf, rakam ve tire (Türkçe harfler sadeleştirilir)."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")
    text = re.sub(r"[^a-z0-9]+", "-", name.translate(table).lower()).strip("-")
    text = text[:40] or "program"
    return "shared-" + text if text == SHARED_ID else text


@dataclass
class WineEnv:
    id: str
    path: Path
    name: str
    shared: bool
    reason: str = ""  # "risk" | "user" | "retry" (ayrı ortamlar için)


@dataclass
class WineShortcut:
    name: str
    desktop_file: Path
    env_id: str
    exec_args: list[str]
    icon: str = ""


def env_path(env_id: str) -> Path:
    return base_dir() / env_id


def _write_meta(path: Path, name: str, reason: str) -> None:
    meta = {
        "name": name,
        "reason": reason,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.mkdir(parents=True, exist_ok=True)
    (path / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_env(name: str = "", separate: bool = False, reason: str = "user") -> WineEnv:
    """Ortamı hazırlar (klasör + linwas.json). Wine ortamı ilk çalıştırmada kendini kurar."""
    if not separate:
        path = env_path(SHARED_ID)
        if not (path / META_FILE).exists():
            _write_meta(path, "Shared", "")
        return WineEnv(SHARED_ID, path, "Shared", True)
    env_id = slug(name)
    path = env_path(env_id)
    n = 2
    while (path / META_FILE).exists():  # aynı adlı ortam varsa yenisini aç
        env_id = f"{slug(name)}-{n}"
        path = env_path(env_id)
        n += 1
    _write_meta(path, name or env_id, reason)
    return WineEnv(env_id, path, name or env_id, False, reason)


def list_envs() -> list[WineEnv]:
    envs: list[WineEnv] = []
    base = base_dir()
    if not base.is_dir():
        return envs
    for child in sorted(base.iterdir()):
        meta_file = child / META_FILE
        if not meta_file.is_file():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        shared = child.name == SHARED_ID
        envs.append(
            WineEnv(
                child.name, child, meta.get("name") or child.name, shared, meta.get("reason", "")
            )
        )
    # Ortak ortam önce
    return sorted(envs, key=lambda e: (not e.shared, e.name.lower()))


def build_command(exe: str | Path, env: WineEnv) -> tuple[list[str], dict[str, str]]:
    """(argv, ortam değişkenleri). .msi dosyaları msiexec ile açılır."""
    path = str(Path(exe).resolve())
    msi = path.lower().endswith(".msi")
    argv = ["wine", "msiexec", "/i", path] if msi else ["wine", path]
    env_vars = {**os.environ, "WINEPREFIX": str(env.path), "WINEDEBUG": "-all"}
    return argv, env_vars


def uninstaller_command(env: WineEnv) -> tuple[list[str], dict[str, str]]:
    """Wine'ın "Program Ekle/Kaldır" penceresi (ortak ortamdaki tek bir programı kaldırmak için)."""
    return ["wine", "uninstaller"], {**os.environ, "WINEPREFIX": str(env.path), "WINEDEBUG": "-all"}


def remove_env(env_id: str) -> bool:
    """Ayrı ortamı ve ona ait menü kısayollarını siler. Ortak ortam bu yolla silinmez."""
    if env_id == SHARED_ID or not env_id or "/" in env_id or env_id.startswith("."):
        return False
    path = env_path(env_id)
    # Yalnızca Linwas'ın oluşturduğu ortam (linwas.json var) silinir
    if not (path / META_FILE).is_file() or path.resolve().parent != base_dir().resolve():
        return False
    for shortcut in list_shortcuts():
        if shortcut.env_id == env_id:
            shortcut.desktop_file.unlink(missing_ok=True)
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


# --- Menü kısayolları (.desktop) ---


def _desktop_dirs() -> list[Path]:
    dirs = [_data_home() / "applications" / "wine"]
    desktop = os.environ.get("XDG_DESKTOP_DIR") or str(Path.home() / "Desktop")
    dirs.append(Path(desktop))
    return dirs


def parse_desktop_exec(exec_line: str) -> tuple[str, list[str]]:
    """Wine kısayolunun Exec satırı → (WINEPREFIX, wine argümanları).

    Örnek: env WINEPREFIX="/home/u/.local/share/linwas/wine/shared" wine C:\\\\users\\\\x.lnk
    Exec değeri .desktop kaçışlarıyla yazılır; ters eğik çizgiler iki kez çözülür.
    """
    try:
        parts = shlex.split(exec_line)
    except ValueError:
        return "", []
    parts = [p.replace("\\\\", "\\") for p in parts]
    prefix = ""
    args: list[str] = []
    for i, part in enumerate(parts):
        if part.startswith("WINEPREFIX="):
            prefix = part.split("=", 1)[1]
        elif Path(part).name in ("wine", "wine64"):
            args = parts[i:]
            break
    return prefix, args


def _read_desktop(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fields
    in_entry = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if in_entry and "=" in line:
            key, _, value = line.partition("=")
            fields.setdefault(key.strip(), value.strip())
    return fields


def list_shortcuts() -> list[WineShortcut]:
    """Linwas ortamlarına ait Wine kısayolları (ada göre sıralı, yinelenenler tek)."""
    base = str(base_dir())
    found: dict[tuple[str, str], WineShortcut] = {}
    for directory in _desktop_dirs():
        if not directory.is_dir():
            continue
        pattern = "**/*.desktop" if directory.name == "wine" else "*.desktop"
        for file in directory.glob(pattern):
            fields = _read_desktop(file)
            prefix, args = parse_desktop_exec(fields.get("Exec", ""))
            if not args or not prefix.startswith(base + "/"):
                continue
            env_id = Path(prefix).name
            name = fields.get("Name", file.stem)
            key = (env_id, name)
            # Menüdeki kısayol masaüstündekine tercih edilir
            if key not in found or directory.name == "wine":
                found[key] = WineShortcut(name, file, env_id, args, fields.get("Icon", ""))
    return sorted(found.values(), key=lambda s: s.name.lower())


def shortcut_command(shortcut: WineShortcut) -> tuple[list[str], dict[str, str]]:
    env = {**os.environ, "WINEPREFIX": str(env_path(shortcut.env_id)), "WINEDEBUG": "-all"}
    return list(shortcut.exec_args), env


# --- .exe/.msi çift tıklama ---

EXE_MIME_TYPES = (
    "application/x-ms-dos-executable",
    "application/x-msdownload",
    "application/vnd.microsoft.portable-executable",
    "application/x-msi",
)
INSTALLED_DESKTOP_FILE = Path("/usr/share/applications/linwas.desktop")


def set_default_exe_handler() -> bool:
    """Linwas'ı .exe/.msi için kullanıcının varsayılan uygulaması yapar (xdg-mime, root gerekmez).

    Yalnızca paket kuruluysa (masaüstü dosyası varsa) yapılır.
    """
    if not INSTALLED_DESKTOP_FILE.is_file() or not shutil.which("xdg-mime"):
        return False
    try:
        r = subprocess.run(
            ["xdg-mime", "default", INSTALLED_DESKTOP_FILE.name, *EXE_MIME_TYPES],
            capture_output=True,
            timeout=15,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0
