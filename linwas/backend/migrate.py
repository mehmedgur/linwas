"""Windows'tan taşıma: kaynak algılama ve dosya aktarımı.

Root gerekmez — tüm işlemler kullanıcı dizinine kopyalama yapar.
NTFS bölüm erişimi: ntfs-3g veya kernel ntfs3 sürücüsü gerekir.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# --- Kaynak algılama ---


@dataclass
class WindowsUser:
    """Tespit edilen Windows kullanıcı dizini."""

    drive: Path  # ör. /media/user/C
    user_name: str  # ör. "Ahmet"
    user_path: Path  # ör. /media/user/C/Users/Ahmet
    bitlocker: bool  # Sürücü BitLocker ile şifreli mi?
    hibernated: bool  # Fast Startup / hiberfil.sys var mı?


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _find_ntfs_mounts() -> list[Path]:
    """Bağlı NTFS bölümleri döner."""
    mounts: list[Path] = []
    for line in Path("/proc/mounts").read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2].lower() in ("ntfs", "ntfs3", "fuseblk"):
            mounts.append(Path(parts[1]))
    return mounts


def _find_windows_users(drive: Path) -> list[WindowsUser]:
    """Sürücüdeki Windows kullanıcı dizinlerini döner."""
    users_dir = drive / "Users"
    if not users_dir.is_dir():
        return []

    hibernated = (drive / "hiberfil.sys").exists()
    bitlocker = (drive / "$RECYCLE.BIN").exists() and not (drive / "Windows").is_dir()

    results: list[WindowsUser] = []
    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue
        if user_dir.name.lower() in ("all users", "default", "default user", "public"):
            continue
        results.append(
            WindowsUser(
                drive=drive,
                user_name=user_dir.name,
                user_path=user_dir,
                bitlocker=bitlocker,
                hibernated=hibernated,
            )
        )
    return results


def find_windows_users() -> list[WindowsUser]:
    """Tüm NTFS sürücülerdeki Windows kullanıcılarını döner."""
    users: list[WindowsUser] = []
    for mount in _find_ntfs_mounts():
        users.extend(_find_windows_users(mount))
    return users


# --- Import öğeleri ---


@dataclass
class ImportItem:
    id: str
    label: str
    description: str
    source: Path | None
    dest: Path | None
    available: bool
    size_mb: float = 0.0
    selected: bool = True
    # Birden fazla kaynak→hedef çifti olabilen öğeler için
    extra_pairs: list[tuple[Path, Path]] = field(default_factory=list)


def _dir_size_mb(path: Path, max_mb: float = 10000) -> float:
    """Dizin boyutunu MB olarak döner; çok büyükse max_mb döner."""
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return round(total / (1024 * 1024), 1)
    except (OSError, PermissionError):
        return 0.0


def _appdata(user: WindowsUser) -> Path:
    return user.user_path / "AppData" / "Roaming"


def _local_appdata(user: WindowsUser) -> Path:
    return user.user_path / "AppData" / "Local"


def scan_import_items(user: WindowsUser) -> list[ImportItem]:
    """Taşınabilir öğeleri listeler ve boyutlarını hesaplar."""
    items: list[ImportItem] = []

    # --- Kişisel klasörler ---
    personal_folders = [
        ("Documents", "Belgeler"),
        ("Pictures", "Resimler"),
        ("Music", "Müzik"),
        ("Videos", "Videolar"),
        ("Downloads", "İndirilenler"),
    ]
    for win_name, _ in personal_folders:
        src = user.user_path / win_name
        # Windows bazen farklı adlar kullanır
        if not src.exists():
            src = user.user_path / win_name.lower()
        if not src.exists():
            continue
        dest = Path.home() / win_name
        items.append(
            ImportItem(
                id=f"folder_{win_name.lower()}",
                label=win_name,
                description=f"Your Windows {win_name} folder",
                source=src,
                dest=dest,
                available=True,
                size_mb=_dir_size_mb(src),
            )
        )

    # --- Firefox profili ---
    ff_src = _appdata(user) / "Mozilla" / "Firefox" / "Profiles"
    if ff_src.is_dir():
        ff_dest = Path.home() / ".mozilla" / "firefox"
        items.append(
            ImportItem(
                id="firefox",
                label="Firefox",
                description="Bookmarks, passwords, history and extensions",
                source=ff_src,
                dest=ff_dest,
                available=True,
                size_mb=_dir_size_mb(ff_src),
            )
        )

    # --- Thunderbird profili ---
    tb_src = _appdata(user) / "Thunderbird" / "Profiles"
    if tb_src.is_dir():
        tb_dest = Path.home() / ".thunderbird"
        items.append(
            ImportItem(
                id="thunderbird",
                label="Thunderbird",
                description="Emails, contacts and account settings",
                source=tb_src,
                dest=tb_dest,
                available=True,
                size_mb=_dir_size_mb(tb_src),
            )
        )

    # --- Chrome yer imleri ---
    for browser_name, rel_path in [
        ("Google Chrome", _local_appdata(user) / "Google" / "Chrome" / "User Data"),
        ("Microsoft Edge", _local_appdata(user) / "Microsoft" / "Edge" / "User Data"),
    ]:
        bookmarks = rel_path / "Default" / "Bookmarks"
        if bookmarks.exists():
            items.append(
                ImportItem(
                    id=f"bookmarks_{browser_name.lower().replace(' ', '_')}",
                    label=f"{browser_name} Bookmarks",
                    description=f"Bookmarks and browsing history from {browser_name}",
                    source=bookmarks,
                    dest=None,  # Hedef çalışma zamanında belirlenir
                    available=True,
                    size_mb=round(bookmarks.stat().st_size / (1024 * 1024), 2),
                )
            )

    # --- Fontlar ---
    win_fonts = user.drive / "Windows" / "Fonts"
    user_fonts = user.user_path / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"
    font_items: list[tuple[Path, Path]] = []
    dest_fonts = Path.home() / ".local" / "share" / "fonts" / "from_windows"
    for fsrc in [win_fonts, user_fonts]:
        if fsrc.is_dir():
            # Yalnızca kullanıcı fontları taşı (Windows sistem fontları değil)
            if fsrc == win_fonts:
                # Sistem fontlarını atla — lisans sorunları
                continue
            font_files = list(fsrc.glob("*.ttf")) + list(fsrc.glob("*.otf"))
            for f in font_files:
                font_items.append((f, dest_fonts / f.name))
    if user_fonts.is_dir():
        items.append(
            ImportItem(
                id="user_fonts",
                label="Custom Fonts",
                description="Fonts you installed on Windows",
                source=user_fonts,
                dest=dest_fonts,
                available=bool(font_items),
                size_mb=_dir_size_mb(user_fonts) if user_fonts.is_dir() else 0,
            )
        )

    return items


# --- Sistem tercihleri ---


@dataclass
class WindowsPrefs:
    keyboard_layout: str  # "TR Q", "TR F", "US" vb.
    timezone: str  # Windows timezone adı
    dark_mode: bool | None
    mouse_buttons_swapped: bool | None
    locale: str  # "tr-TR", "en-US" vb.


_LAYOUT_MAP = {
    "0000041f": "TR Q",
    "0001041f": "TR F",
    "00000409": "US",
    "00000407": "DE",
    "0000040c": "FR",
    "00000410": "IT",
    "00000419": "RU",
}


def detect_windows_prefs(user: WindowsUser) -> WindowsPrefs | None:
    """NTUser.dat'tan klavye düzeni ve diğer tercihleri okur.

    hivexsh veya reged kurulu değilse None döner.
    """
    ntuser = user.user_path / "NTUSER.DAT"
    if not ntuser.exists():
        return None

    # hivexsh ile klavye düzenini oku
    layout = _read_keyboard_layout(ntuser)
    return WindowsPrefs(
        keyboard_layout=layout or "Unknown",
        timezone="",
        dark_mode=None,
        mouse_buttons_swapped=None,
        locale="",
    )


def _read_keyboard_layout(ntuser: Path) -> str | None:
    """hivexsh kullanarak aktif klavye düzenini okur."""
    script = "open " + str(ntuser) + "\ncd /Keyboard Layout/Preload\nls\n"
    try:
        r = subprocess.run(
            ["hivexsh"],
            input=script,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        for line in r.stdout.splitlines():
            # "1 = 00000409" formatı
            if "=" in line:
                val = line.split("=")[-1].strip().strip('"').lower()
                if val in _LAYOUT_MAP:
                    return _LAYOUT_MAP[val]
    except FileNotFoundError:
        pass
    return None


# --- Programlar listesi ---


def list_installed_programs(user: WindowsUser) -> list[str]:
    """Program Files klasörlerinden kurulu uygulama adlarını listeler."""
    programs: list[str] = []
    for prog_dir in [
        user.drive / "Program Files",
        user.drive / "Program Files (x86)",
    ]:
        if not prog_dir.is_dir():
            continue
        try:
            for entry in prog_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    programs.append(entry.name)
        except PermissionError:
            continue
    return sorted(set(programs))


# --- İçe aktarma ---

ProgressCallback = Callable[[str, float], None]  # (mesaj, 0-1 ilerleme)


def import_item(item: ImportItem, on_progress: ProgressCallback | None = None) -> bool:
    """Tek bir öğeyi içe aktarır. Başarılıysa True döner."""
    try:
        if item.id.startswith("bookmarks_"):
            return _import_browser_bookmarks(item, on_progress)
        if item.id == "firefox":
            return _import_profile(item, on_progress)
        if item.id == "thunderbird":
            return _import_profile(item, on_progress)
        if item.id == "user_fonts":
            return _import_fonts(item, on_progress)
        if item.id.startswith("folder_"):
            return _import_folder(item, on_progress)
    except Exception as exc:
        if on_progress:
            on_progress(f"Error: {exc}", 0.0)
    return False


def _import_folder(item: ImportItem, cb: ProgressCallback | None) -> bool:
    if not item.source or not item.dest:
        return False
    if cb:
        cb(f"Copying {item.label}…", 0.0)
    item.dest.mkdir(parents=True, exist_ok=True)
    files = list(item.source.rglob("*"))
    total = max(len(files), 1)
    for i, f in enumerate(files):
        if not f.is_file():
            continue
        rel = f.relative_to(item.source)
        target = item.dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        import contextlib

        with contextlib.suppress(OSError, PermissionError):
            shutil.copy2(f, target)
        if cb and i % 50 == 0:
            cb(f"Copying {item.label}: {f.name}", i / total)
    if cb:
        cb(f"{item.label} done", 1.0)
    return True


def _import_profile(item: ImportItem, cb: ProgressCallback | None) -> bool:
    """Firefox/Thunderbird profilini aktarır."""
    if not item.source or not item.dest:
        return False
    if cb:
        cb(f"Importing {item.label} profile…", 0.0)
    item.dest.mkdir(parents=True, exist_ok=True)
    try:
        # profiles.ini yoksa oluştur
        profiles = list(item.source.iterdir())
        for i, profile_dir in enumerate(profiles):
            if not profile_dir.is_dir():
                continue
            dest_profile = item.dest / profile_dir.name
            if dest_profile.exists():
                dest_profile = item.dest / (profile_dir.name + "_from_windows")
            if cb:
                cb(f"Copying {profile_dir.name}…", i / max(len(profiles), 1))
            shutil.copytree(str(profile_dir), str(dest_profile), dirs_exist_ok=True)
    except (OSError, shutil.Error) as exc:
        if cb:
            cb(f"Warning: {exc}", 0.5)
    if cb:
        cb(f"{item.label} done", 1.0)
    return True


def _import_browser_bookmarks(item: ImportItem, cb: ProgressCallback | None) -> bool:
    """Chrome/Edge yer imlerini Linux Chrome profiline aktarır."""
    if not item.source:
        return False
    if cb:
        cb(f"Importing {item.label}…", 0.0)

    # Linux Chrome profil dizini
    chrome_profile = (
        Path.home() / ".config" / "google-chrome" / "Default"
        if "google_chrome" in item.id
        else Path.home() / ".config" / "chromium" / "Default"
    )
    chrome_profile.mkdir(parents=True, exist_ok=True)

    dest = chrome_profile / "Bookmarks_from_windows"
    try:
        shutil.copy2(item.source, dest)
        if cb:
            cb(
                f"Bookmarks saved to {dest.name} — open Chrome and import manually.",
                1.0,
            )
    except OSError as exc:
        if cb:
            cb(f"Error: {exc}", 0.0)
        return False
    return True


def _import_fonts(item: ImportItem, cb: ProgressCallback | None) -> bool:
    if not item.source or not item.dest:
        return False
    item.dest.mkdir(parents=True, exist_ok=True)
    fonts = list(item.source.glob("*.ttf")) + list(item.source.glob("*.otf"))
    total = max(len(fonts), 1)
    import contextlib

    for i, f in enumerate(fonts):
        with contextlib.suppress(OSError, PermissionError):
            shutil.copy2(f, item.dest / f.name)
        if cb:
            cb(f"Copying font: {f.name}", i / total)
    # Font önbelleğini güncelle
    subprocess.run(["fc-cache", "-f"], capture_output=True, shell=False)
    if cb:
        cb("Fonts imported", 1.0)
    return True
