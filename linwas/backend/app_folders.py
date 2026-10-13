"""Program klasörleri (Android ana ekran klasörü gibi; kararlar.md › Yeni özellikler › 9 › C).

Klasör = birkaç programın kısayolu. Masaüstünde ve görev çubuğunda tek simge olarak durur;
tıklanınca Linwas'ın açılır penceresi (`linwas --app-folder <kimlik>`) program ızgarasını gösterir.

- Kayıt: ~/.local/share/linwas/app-folders.json (kullanıcıya özel)
- Kısayol: ~/.local/share/applications/linwas-folder-<kimlik>.desktop (görev çubuğu için)
  ve masaüstünde aynı adla kopya (Desktop Icons NG'de "güvenilir": çalıştırılabilir +
  metadata::trusted=true; fileItem.js › trustedDesktopFile).
- Sürükle-bırak: DING, güvenilir kısayolun üstüne bırakılan dosyaları kısayolu çalıştırarak
  argüman olarak verir (fileItem.js: "open the desktopfile with these dropped files as the
  arguments"); Exec satırındaki %U bu adresleri `linwas --app-folder <kimlik> <adresler>` yapar.
  Masaüstündeki bir program simgesi bırakılınca Android'deki gibi klasöre taşınır
  (~/.local/share/linwas/folder-items/), klasörden çıkarılınca masaüstüne geri döner.

XFCE (xfdesktop) kısayolu ancak çalıştırılabilir ve `metadata::xfce-exe-checksum` içeriğin
SHA-256'sına eşitse güvenilir sayar (libxfce4util xfce_g_file_set_trusted).
Masaüstünde sağ tık eylemleri (grupla / klasöre ekle / klasörü çöz): backend/folder_menu.py.

Görev çubuğuna sabitleme şimdilik GNOME'da (org.gnome.shell favorite-apps; Dash to Panel de bunu
kullanır); KDE ve XFCE sonraki sürümde.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from linwas.backend.installed_apps import _ui_languages, parse_desktop_entry

DING_UUID = "ding@rastersoft.com"
DING_PACKAGE = "gnome-shell-extension-desktop-icons-ng"
INSTALLED_LINWAS = Path("/usr/bin/linwas")
# Paketin kurulduğu yer (gömülü Python ve site-packages/linwas)
INSTALLED_ROOT = Path("/opt/linwas")
LAUNCHER_PREFIX = "linwas-folder-"
MAX_NAME_LEN = 40
_RE_ID = re.compile(r"^[0-9a-f]{8}$")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def data_dir() -> Path:
    return _data_home() / "linwas"


def folders_file() -> Path:
    return data_dir() / "app-folders.json"


def icons_dir() -> Path:
    return data_dir() / "folder-icons"


def icon_path(folder_id: str) -> Path:
    """Klasörün geçerli simgesi. Simge her değişimde yeni adla yazılır (<kimlik>-<sürüm>.png);
    masaüstü ve görev çubuğu eski simgeyi önbellekte tutmasın diye."""
    icons = sorted(icons_dir().glob(f"{folder_id}-*.png"), key=lambda p: p.stat().st_mtime)
    return icons[-1] if icons else icons_dir() / f"{folder_id}-0.png"


def new_icon_path(folder_id: str) -> Path:
    """Yeni simge yolu; eskileri siler."""
    for old in icons_dir().glob(f"{folder_id}-*.png"):
        old.unlink(missing_ok=True)
    icons_dir().mkdir(parents=True, exist_ok=True)
    return icons_dir() / f"{folder_id}-{uuid.uuid4().hex[:6]}.png"


def items_dir() -> Path:
    return data_dir() / "folder-items"


def user_apps_dir() -> Path:
    return _data_home() / "applications"


def app_dirs() -> list[Path]:
    """.desktop arama sırası (XDG Base Directory): kullanıcı, sonra XDG_DATA_DIRS."""
    dirs = [user_apps_dir()]
    system = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs += [Path(d) / "applications" for d in system.split(":") if d]
    for extra in (
        Path.home() / ".local/share/flatpak/exports/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
    ):
        if extra not in dirs:
            dirs.append(extra)
    return dirs


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


def desktop_dir() -> Path:
    """Masaüstü klasörü (xdg-user-dir; Türkçe sistemde ~/Masaüstü)."""
    code, out = _run(["xdg-user-dir", "DESKTOP"])
    path = out.strip()
    if code == 0 and path and path != str(Path.home()):
        return Path(path)
    return Path(os.environ.get("XDG_DESKTOP_DIR") or Path.home() / "Desktop")


# --- Kayıt ---


@dataclass
class AppFolder:
    id: str
    name: str
    # Program başvuruları: masaüstü kimliği ("firefox.desktop") ya da klasöre taşınmış
    # kısayolun tam yolu
    apps: list[str] = field(default_factory=list)
    on_desktop: bool = True
    pinned: bool = False


def _clean_name(name: str) -> str:
    name = " ".join(str(name).split())[:MAX_NAME_LEN]
    return "".join(c for c in name if ord(c) >= 32)


def load_folders() -> list[AppFolder]:
    try:
        data = json.loads(folders_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    folders: list[AppFolder] = []
    for raw in data.get("folders", []) if isinstance(data, dict) else []:
        if not isinstance(raw, dict) or not _RE_ID.match(str(raw.get("id", ""))):
            continue
        apps = [a for a in raw.get("apps", []) if isinstance(a, str) and a.endswith(".desktop")]
        folders.append(
            AppFolder(
                id=raw["id"],
                name=_clean_name(raw.get("name", "")) or "Folder",
                apps=list(dict.fromkeys(apps)),
                on_desktop=raw.get("on_desktop", True) is not False,
                pinned=raw.get("pinned", False) is True,
            )
        )
    return folders


def save_folders(folders: list[AppFolder]) -> None:
    path = folders_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"version": 1, "folders": [asdict(f) for f in folders]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def get_folder(folder_id: str) -> AppFolder | None:
    return next((f for f in load_folders() if f.id == folder_id), None)


def update_folder(folder: AppFolder) -> None:
    folders = load_folders()
    for i, f in enumerate(folders):
        if f.id == folder.id:
            folders[i] = folder
            break
    else:
        folders.append(folder)
    save_folders(folders)


def new_folder(name: str, apps: list[str] | None = None) -> AppFolder:
    folder = AppFolder(
        id=uuid.uuid4().hex[:8],
        name=_clean_name(name) or "Folder",
        apps=list(dict.fromkeys(apps or [])),
    )
    update_folder(folder)
    return folder


# --- Programlar ---


@dataclass
class AppEntry:
    ref: str  # klasörde saklanan başvuru
    name: str
    icon: str  # tema adı ya da dosya yolu
    path: Path


def resolve(ref: str) -> Path | None:
    if ref.startswith("/"):
        p = Path(ref)
        return p if p.is_file() else None
    for d in app_dirs():
        p = d / ref
        if p.is_file():
            return p
    return None


def _entry(path: Path, ref: str) -> AppEntry | None:
    try:
        info = parse_desktop_entry(path.read_text(encoding="utf-8"), _ui_languages())
    except (OSError, UnicodeDecodeError):
        return None
    if info is None:
        return None
    return AppEntry(ref=ref, name=info["name"], icon=info["icon"], path=path)


def app_entry(ref: str) -> AppEntry | None:
    path = resolve(ref)
    return _entry(path, ref) if path else None


def folder_entries(folder: AppFolder) -> list[AppEntry]:
    """Klasördeki programlar (kaldırılmış programlar atlanır)."""
    return [e for e in (app_entry(r) for r in folder.apps) if e]


def all_apps() -> list[AppEntry]:
    """Menüde görünen bütün programlar (Linwas klasör kısayolları hariç), ada göre sıralı."""
    seen: dict[str, AppEntry] = {}
    for d in app_dirs():
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.desktop")):
            if path.name in seen or path.name.startswith(LAUNCHER_PREFIX):
                continue
            entry = _entry(path, path.name)
            if entry:
                seen[path.name] = entry
    return sorted(seen.values(), key=lambda e: e.name.casefold())


def launch(entry: AppEntry) -> bool:
    """Programı oturumdan bağımsız başlatır (`gio launch`, GLib ≥ 2.67)."""
    cmd = (
        ["gio", "launch", str(entry.path)]
        if shutil.which("gio")
        else ["gtk-launch", entry.path.name]
    )
    try:
        subprocess.Popen(  # noqa: S603 — sabit komut, kabuk yok
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            shell=False,
        )
    except OSError:
        return False
    return True


# --- Kısayollar ---


def exec_command() -> list[str]:
    """Şu an çalışan Linwas'ı başlatan komut. Kaynak koddan çalışırken kurulu (belki eski)
    paket çağrılmaz; yoksa eski sürüm yeni seçenekleri bilmeyip ana pencereyi açar."""
    root = Path(__file__).resolve().parents[2]
    if INSTALLED_LINWAS.is_file() and root.is_relative_to(INSTALLED_ROOT):
        return [str(INSTALLED_LINWAS)]
    return ["/usr/bin/env", f"PYTHONPATH={root}", sys.executable, "-m", "linwas"]


def _quote(arg: str) -> str:
    """Desktop Entry Exec= tırnaklama kuralı (boşluk ya da özel karakter varsa)."""
    if re.fullmatch(r"[A-Za-z0-9_./=:@+-]+", arg):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def launcher_name(folder: AppFolder) -> str:
    return f"{LAUNCHER_PREFIX}{folder.id}.desktop"


def launcher_text(folder: AppFolder) -> str:
    cmd = " ".join(_quote(a) for a in [*exec_command(), "--app-folder", folder.id])
    name = folder.name.replace("\n", " ")
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Icon={icon_path(folder.id)}\n"
        f"Exec={cmd} %U\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "StartupNotify=false\n"
        f"X-Linwas-Folder={folder.id}\n"
    )


def _trust(path: Path) -> None:
    """Masaüstünün çalıştırması için: grup/diğerleri yazamaz + çalıştırılabilir + güvenilir.

    GNOME (DING) `metadata::trusted`, XFCE `metadata::xfce-exe-checksum` (içeriğin SHA-256'sı;
    içerik değişince yeniden onay ister) bakar; ikisi de yazılır.
    """
    path.chmod(0o755)
    _run(["gio", "set", str(path), "metadata::trusted", "true"])
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return
    _run(["gio", "set", str(path), "metadata::xfce-exe-checksum", digest])


def write_launchers(folder: AppFolder) -> None:
    text = launcher_text(folder)
    menu = user_apps_dir() / launcher_name(folder)
    menu.parent.mkdir(parents=True, exist_ok=True)
    menu.write_text(text, encoding="utf-8")
    desk = desktop_dir() / launcher_name(folder)
    if folder.on_desktop and desktop_dir().is_dir():
        desk.write_text(text, encoding="utf-8")
        _trust(desk)
    else:
        desk.unlink(missing_ok=True)
    set_pinned(folder, folder.pinned)


def refresh_launchers(folders: list[AppFolder]) -> None:
    """Komutu eskimiş kısayolları (ör. başka kopyanın yazdığı) yeniden yazar."""
    for folder in folders:
        menu = user_apps_dir() / launcher_name(folder)
        try:
            current = menu.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current != launcher_text(folder):
            write_launchers(folder)
            continue
        desk = desktop_dir() / launcher_name(folder)
        if folder.on_desktop and desk.is_file():
            _trust(desk)  # eski sürümün yazdığı kopyada XFCE onayı yoktu


def remove_launchers(folder: AppFolder) -> None:
    set_pinned(folder, False)
    (user_apps_dir() / launcher_name(folder)).unlink(missing_ok=True)
    (desktop_dir() / launcher_name(folder)).unlink(missing_ok=True)
    for old in icons_dir().glob(f"{folder.id}-*.png"):
        old.unlink(missing_ok=True)


def delete_folder(folder_id: str) -> None:
    """Klasörü siler; klasöre taşınmış masaüstü simgeleri masaüstüne geri döner."""
    folders = load_folders()
    folder = next((f for f in folders if f.id == folder_id), None)
    if folder is None:
        return
    for ref in list(folder.apps):
        remove_app(folder, ref)
    remove_launchers(folder)
    save_folders([f for f in folders if f.id != folder_id])


# --- Görev çubuğu (GNOME favorileri) ---


def _is_gnome() -> bool:
    return "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")


def can_pin() -> bool:
    return _is_gnome() and shutil.which("gsettings") is not None


def _favorites() -> list[str] | None:
    code, out = _run(["gsettings", "get", "org.gnome.shell", "favorite-apps"])
    if code != 0:
        return None
    text = out.strip().removeprefix("@as ")
    return re.findall(r"'((?:[^'\\]|\\.)*)'", text)


def set_pinned(folder: AppFolder, pinned: bool) -> bool:
    if not can_pin():
        return False
    favorites = _favorites()
    if favorites is None:
        return False
    name = launcher_name(folder)
    if pinned and name not in favorites:
        favorites.append(name)
    elif not pinned and name in favorites:
        favorites.remove(name)
    else:
        return True
    value = "[" + ", ".join(f"'{f}'" for f in favorites) + "]"
    return _run(["gsettings", "set", "org.gnome.shell", "favorite-apps", value])[0] == 0


# --- Klasöre ekleme / çıkarma ---


def _uri_to_path(uri: str) -> Path | None:
    if uri.startswith("/"):
        return Path(uri)
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def _system_ref(path: Path) -> str | None:
    """Menü klasörlerindeki kısayolsa masaüstü kimliği (ör. firefox.desktop)."""
    for d in app_dirs():
        try:
            if path.resolve().parent == d.resolve() and path.name == path.resolve().name:
                return path.name
        except OSError:
            continue
    return None


def add_dropped(folder: AppFolder, uris: list[str]) -> int:
    """Bırakılan kısayolları klasöre ekler; eklenen sayısını döner. Masaüstündeki kısayol
    klasöre taşınır (Android'deki gibi), menüdeki program kimliğiyle eklenir."""
    added = 0
    desk = desktop_dir()
    for uri in uris:
        path = _uri_to_path(uri)
        if path is None or path.suffix != ".desktop" or not path.is_file():
            continue
        if path.name.startswith(LAUNCHER_PREFIX):
            continue  # klasör klasöre eklenmez
        if app_entry(str(path)) is None:
            continue
        ref = _system_ref(path)
        if ref is None and path.parent == desk:
            # Asıl dosya adı korunur: folder-items/<klasör>/[<n>/]<ad>
            target = items_dir() / folder.id / path.name
            n = 1
            while target.exists():
                target = items_dir() / folder.id / str(n) / path.name
                n += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), target)
            ref = str(target)
        ref = ref or str(path)
        if ref not in folder.apps:
            folder.apps.append(ref)
            added += 1
    return added


def group_paths(name: str, paths: list[str]) -> AppFolder | None:
    """Masaüstünde seçilen program kısayollarından yeni klasör (sağ tık › Klasörde grupla).

    Hiçbiri program kısayolu değilse klasör oluşturulmaz (None)."""
    folder = new_folder(name)
    if not add_dropped(folder, paths):
        save_folders([f for f in load_folders() if f.id != folder.id])
        return None
    folder.pinned = can_pin()
    update_folder(folder)
    return folder


def folder_of_launcher(path: str) -> AppFolder | None:
    """Klasör kısayolunun (linwas-folder-<kimlik>.desktop) klasörü."""
    p = _uri_to_path(path)
    if p is None or not p.name.startswith(LAUNCHER_PREFIX) or p.suffix != ".desktop":
        return None
    return get_folder(p.stem.removeprefix(LAUNCHER_PREFIX))


def remove_app(folder: AppFolder, ref: str) -> None:
    """Programı klasörden çıkarır; klasöre taşınmış kısayol masaüstüne geri döner."""
    if ref in folder.apps:
        folder.apps.remove(ref)
    path = Path(ref)
    if ref.startswith("/") and items_dir() in path.parents and path.is_file():
        target = desktop_dir() / path.name
        if target.exists():
            target = desktop_dir() / f"{target.stem}-{folder.id}{target.suffix}"
        try:
            shutil.move(str(path), target)
            _trust(target)
        except OSError:
            pass


# --- Masaüstü simgeleri (Desktop Icons NG) ---


def desktop_icons_state() -> str:
    """ "enabled" | "disabled" | "missing" | "unsupported" (GNOME dışı)."""
    if not _is_gnome():
        return "unsupported"
    from linwas.backend.appearance import extension_state

    return extension_state(DING_UUID)


def enable_desktop_icons() -> bool:
    """Eklentiyi açar. Yeni kurulduysa GNOME onu oturum yeniden açılana dek tanımaz; o zaman
    etkin eklenti listesine yazılır ve sonraki oturumda açılır."""
    from linwas.backend.appearance import set_extension

    if set_extension(True, DING_UUID):
        return True
    code, out = _run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"])
    if code != 0:
        return False
    enabled = re.findall(r"'([^']*)'", out)
    if DING_UUID in enabled:
        return True
    value = "[" + ", ".join(f"'{e}'" for e in [*enabled, DING_UUID]) + "]"
    return _run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", value])[0] == 0


def ding_installed() -> bool:
    return (
        Path("/usr/share/gnome-shell/extensions", DING_UUID).is_dir()
        or Path(_data_home(), "gnome-shell/extensions", DING_UUID).is_dir()
    )


def ding_package_available() -> bool:
    code, out = _run(["apt-cache", "policy", DING_PACKAGE])
    m = re.search(r"Candidate:\s*(\S+)", out)
    return bool(m and m.group(1) != "(none)")
