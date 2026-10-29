# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Başka Linux dağıtımına taşıma (kullanıcı yetkisiyle; root gerekmez).

Taşıma paketi bir klasördür:
  linwas-transfer.json   manifest (öğeler, program listesi, kaynak sistem bilgisi)
  <öğe>.tar.gz           her öğe ayrı arşiv; şifreliyse <öğe>.tar.gz.gpg (GnuPG simetrik AES256)
  check.gpg              şifreli pakette parolayı doğrulamak için bilinen metin

Diğer bölümden (çift açılış ya da yeniden kurulum: eski /home) içe aktarmada paket yoktur; öğeler
doğrudan eski ev klasöründen kopyalanır. Program listesi ve masaüstü ayarları yalnızca
pakette vardır.
Metinler arayüzde çevrilir; burada yalnızca kimlikler ve not kodları döner.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

MANIFEST = "linwas-transfer.json"
CHECK_FILE = "check.gpg"
CHECK_TEXT = "linwas-transfer-ok"
FORMAT_VERSION = 1
PACKAGE_PREFIX = "Linwas-Tasima"

ProgressCallback = Callable[[str], None]

# öğe kimliği → (tür, ev klasörüne göre yollar, gizli bilgi içerir mi)
# "files.*" öğeleri kullanıcı klasörlerinden (xdg-user-dir) üretilir.
_STATIC_ITEMS: list[tuple[str, str, tuple[str, ...], bool]] = [
    ("app.firefox", "app", (".mozilla",), True),
    ("app.chrome", "app", (".config/google-chrome",), True),
    ("app.chromium", "app", (".config/chromium",), True),
    ("app.thunderbird", "app", (".thunderbird",), True),
    ("app.libreoffice", "app", (".config/libreoffice",), False),
    ("app.flatpak", "app", (".var/app",), True),  # Flatpak programlarının verileri
    ("desktop.settings", "desktop", (), False),  # dışa aktarırken üretilir
    ("desktop.fonts", "desktop", (".local/share/fonts", ".fonts"), False),
    ("desktop.launchers", "desktop", (".local/share/applications",), False),
    ("desktop.linwas", "desktop", (".config/linwas", ".local/share/linwas"), False),
    ("system.wifi", "system", (), True),  # dışa aktarırken üretilir
    ("system.keys", "system", (".ssh", ".gnupg"), True),
    ("programs", "programs", (), False),  # yalnızca manifest
]
GENERATED = {"desktop.settings", "system.wifi", "programs"}

# Arşive alınmayanlar: önbellekler, kilitler, soketler
_EXCLUDES = (
    "Cache",
    "Code Cache",
    "GPUCache",
    "cache2",
    "CacheStorage",
    "ScriptCache",
    "lock",
    ".parentlock",
    "SingletonLock",
    "SingletonSocket",
    "SingletonCookie",
    "S.gpg-agent*",
    "S.scdaemon",
    "S.dirmngr",
)

# Aynı masaüstüne taşırken birebir yüklenen dconf dalları
_DCONF_PATHS = {
    "gnome": (
        "/org/gnome/desktop/interface/",
        "/org/gnome/desktop/background/",
        "/org/gnome/desktop/input-sources/",
        "/org/gnome/desktop/peripherals/",
        "/org/gnome/desktop/wm/keybindings/",
        "/org/gnome/desktop/wm/preferences/",
        "/org/gnome/settings-daemon/plugins/media-keys/",
        "/org/gnome/shell/extensions/dash-to-panel/",
    ),
    "cinnamon": (
        "/org/cinnamon/desktop/",
        "/org/cinnamon/desktop/keybindings/",
    ),
}
# XFCE: aynı masaüstüne taşırken kopyalanan xfconf dosyaları (oturum yeniden açılınca etkin)
_XFCONF_DIR = ".config/xfce4/xfconf/xfce-perchannel-xml"
_XFCONF_FILES = (
    "xsettings.xml",
    "keyboard-layout.xml",
    "xfce4-keyboard-shortcuts.xml",
    "xfwm4.xml",
    "xfce4-panel.xml",
    "xfce4-desktop.xml",
)


@dataclass
class TransferItem:
    id: str
    kind: str  # files | app | desktop | system | programs
    paths: list[str] = field(default_factory=list)  # ev klasörüne göre
    secret: bool = False
    size: int = 0
    selected: bool = True
    file: str = ""  # paket içindeki arşiv adı


@dataclass
class Program:
    id: str  # APT paket adı ya da Flatpak kimliği (kaynak sistemde)
    name: str
    source: str  # apt | flatpak


@dataclass
class ProgramChoice:
    """İçe aktarmada programın yeni sistemdeki seçenekleri."""

    program: Program
    apt_name: str = ""  # depoda varsa
    flatpak_id: str = ""  # Flathub'da varsa
    installed: bool = False

    @property
    def options(self) -> list[str]:
        return [o for o, v in (("apt", self.apt_name), ("flatpak", self.flatpak_id)) if v]

    @property
    def recommended(self) -> str:
        """Eski sistemdeki kurulum biçimi önerilir; yoksa var olan."""
        opts = self.options
        if self.program.source in opts:
            return self.program.source
        return opts[0] if opts else ""


@dataclass
class Manifest:
    version: int = FORMAT_VERSION
    created: str = ""
    hostname: str = ""
    user: str = ""
    distro: str = ""
    distro_id: str = ""
    desktop: str = ""
    encrypted: bool = False
    items: list[TransferItem] = field(default_factory=list)
    programs: list[Program] = field(default_factory=list)
    printers: list[str] = field(default_factory=list)


@dataclass
class Source:
    """İçe aktarma kaynağı: taşıma paketi ya da eski ev klasörü."""

    path: Path
    kind: str  # package | home
    manifest: Manifest | None = None


# --- Yardımcılar ---


def _env() -> dict[str, str]:
    return {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _run(cmd: list[str], timeout: int = 30, input_text: str | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=_env(),
            input=input_text,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return r.returncode, r.stdout


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def gpg_available() -> bool:
    return _have("gpg")


def path_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def free_bytes(path: Path) -> int:
    try:
        st = os.statvfs(path)
    except OSError:
        return 0
    return st.f_bavail * st.f_frsize


def current_desktop() -> str:
    from linwas.backend.desktop import detect_desktop

    return detect_desktop(os.environ).value


# --- Öğeleri tarama ---


def _folder_items(home: Path) -> list[TransferItem]:
    """Kişisel klasörler: bu ev klasöründe xdg-user-dir, eskisinde user-dirs.dirs okunur."""
    folders: list[tuple[str, Path]] = []
    if home == Path.home():
        from linwas.backend.personal_backup import user_folders

        folders = [(f.key, f.path) for f in user_folders()]
    else:
        folders = [(k, home / rel) for k, rel in read_user_dirs(home).items()]
    items = []
    for key, path in folders:
        if path.is_dir() and path != home:
            try:
                rel = str(path.relative_to(home))
            except ValueError:
                continue
            items.append(TransferItem(id=f"files.{key.lower()}", kind="files", paths=[rel]))
    return items


def read_user_dirs(home: Path) -> dict[str, str]:
    """~/.config/user-dirs.dirs → {"DOCUMENTS": "Belgeler", …} (ev klasörüne göre)."""
    result: dict[str, str] = {}
    try:
        text = (home / ".config" / "user-dirs.dirs").read_text(encoding="utf-8")
    except OSError:
        return result
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("XDG_") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"')
        if not value.startswith("$HOME/"):
            continue
        rel = value[len("$HOME/") :].strip("/")
        if rel:
            result[key[len("XDG_") : -len("_DIR")]] = rel
    return result


def scan_items(home: Path, include_generated: bool = True) -> list[TransferItem]:
    """Bu ev klasöründe taşınabilecek öğeler (boyutlar sonra `measure` ile)."""
    items = _folder_items(home)
    for item_id, kind, paths, secret in _STATIC_ITEMS:
        if item_id in GENERATED:
            if include_generated:
                items.append(TransferItem(id=item_id, kind=kind, secret=secret))
            continue
        existing = [p for p in paths if (home / p).exists()]
        if existing:
            items.append(TransferItem(id=item_id, kind=kind, paths=existing, secret=secret))
    return items


def measure(items: list[TransferItem], home: Path) -> None:
    for item in items:
        item.size = sum(path_size(home / p) for p in item.paths)


# --- Dışa aktarma: üretilen öğeler ---


def _gsettings_get(schema: str, key: str) -> str | None:
    code, out = _run(["gsettings", "get", schema, key], timeout=5)
    return out.strip() if code == 0 else None


def _unquote(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def _xfconf_get(channel: str, prop: str) -> str:
    code, out = _run(["xfconf-query", "-c", channel, "-p", prop], timeout=5)
    return out.strip() if code == 0 else ""


def read_common_settings(desktop: str) -> dict[str, object]:
    """Masaüstünden bağımsız görünüm ayarları (başka masaüstüne çevrilebilenler)."""
    s: dict[str, object] = {}
    if desktop == "gnome":
        base = "org.gnome.desktop.interface"
        s["dark"] = _unquote(_gsettings_get(base, "color-scheme")) == "prefer-dark"
        s["gtk_theme"] = _unquote(_gsettings_get(base, "gtk-theme"))
        s["icon_theme"] = _unquote(_gsettings_get(base, "icon-theme"))
        s["font"] = _unquote(_gsettings_get(base, "font-name"))
        s["wallpaper"] = _unquote(_gsettings_get("org.gnome.desktop.background", "picture-uri"))
        left = _gsettings_get("org.gnome.desktop.peripherals.mouse", "left-handed")
        s["left_handed"] = left == "true"
    elif desktop == "cinnamon":
        base = "org.cinnamon.desktop.interface"
        s["gtk_theme"] = _unquote(_gsettings_get(base, "gtk-theme"))
        s["icon_theme"] = _unquote(_gsettings_get(base, "icon-theme"))
        s["font"] = _unquote(_gsettings_get(base, "font-name"))
        s["wallpaper"] = _unquote(_gsettings_get("org.cinnamon.desktop.background", "picture-uri"))
    elif desktop == "xfce":
        s["gtk_theme"] = _xfconf_get("xsettings", "/Net/ThemeName")
        s["icon_theme"] = _xfconf_get("xsettings", "/Net/IconThemeName")
        s["font"] = _xfconf_get("xsettings", "/Gtk/FontName")
    if "dark" not in s:
        s["dark"] = "dark" in str(s.get("gtk_theme", "")).lower()
    return s


def _wallpaper_path(uri: str) -> Path | None:
    if uri.startswith("file://"):
        from urllib.parse import unquote, urlparse

        path = Path(unquote(urlparse(uri).path))
        return path if path.is_file() else None
    return None


def _stage_desktop(stage: Path, desktop: str) -> None:
    out = stage / "desktop"
    out.mkdir(parents=True, exist_ok=True)
    common = read_common_settings(desktop)
    wp = _wallpaper_path(str(common.get("wallpaper", "")))
    if wp is not None:
        target = out / ("wallpaper" + wp.suffix.lower())
        try:
            shutil.copy2(wp, target)
            common["wallpaper_file"] = target.name
        except OSError:
            pass
    common["desktop"] = desktop
    (out / "common.json").write_text(json.dumps(common, ensure_ascii=False, indent=2), "utf-8")
    for path in _DCONF_PATHS.get(desktop, ()):
        code, dump = _run(["dconf", "dump", path], timeout=10)
        if code == 0 and dump.strip():
            name = "dconf" + path.replace("/", "_").rstrip("_") + ".ini"
            (out / name).write_text(f"# {path}\n" + dump, "utf-8")
    if desktop == "xfce":
        xdir = Path.home() / _XFCONF_DIR
        for name in _XFCONF_FILES:
            if (xdir / name).is_file():
                (out / "xfconf").mkdir(exist_ok=True)
                shutil.copy2(xdir / name, out / "xfconf" / name)


def list_wifi() -> list[dict[str, str]]:
    """Kayıtlı Wi-Fi ağları ve şifreleri (nmcli; okunamayan şifre boş kalır)."""
    code, out = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"], timeout=15)
    if code != 0:
        return []
    networks = []
    for line in out.splitlines():
        # -t çıktısında ":" kaçışlı (\:) gelir
        parts = line.replace("\\:", "\0").split(":")
        if len(parts) < 2 or parts[1] != "802-11-wireless":
            continue
        name = parts[0].replace("\0", ":")
        code, values = _run(
            [
                "nmcli",
                "-s",
                "-g",
                "802-11-wireless.ssid,802-11-wireless-security.key-mgmt,"
                "802-11-wireless-security.psk",
                "connection",
                "show",
                "id",
                name,
            ],
            timeout=15,
        )
        if code != 0:
            continue
        fields = (values.splitlines() + ["", "", ""])[:3]
        networks.append({"name": name, "ssid": fields[0], "key_mgmt": fields[1], "psk": fields[2]})
    return networks


def _stage_wifi(stage: Path) -> None:
    out = stage / "wifi"
    out.mkdir(parents=True, exist_ok=True)
    (out / "wifi.json").write_text(json.dumps(list_wifi(), ensure_ascii=False), "utf-8")


def list_programs() -> list[Program]:
    """Kullanıcının sonradan kurduğu programlar (APT + Flatpak; sistemle gelenler hariç)."""
    from linwas.backend.installed_apps import list_installed_apps

    programs = []
    for app in list_installed_apps(include_snap=False):
        if app.preinstalled or app.source not in ("apt", "flatpak"):
            continue
        programs.append(Program(id=app.id, name=app.name, source=app.source))
    return programs


def list_printers() -> list[str]:
    code, out = _run(["lpstat", "-e"], timeout=10)
    return [line.strip() for line in out.splitlines() if line.strip()] if code == 0 else []


# --- Arşivleme ve şifreleme ---


def _tar_create(base: Path, paths: list[str], output: str) -> list[str]:
    cmd = ["tar", "--warning=no-file-changed", "--warning=no-file-ignored"]
    for pattern in _EXCLUDES:
        cmd.append(f"--exclude={pattern}")
    return cmd + ["-czf", output, "-C", str(base), "--", *paths]


def _gpg_base(fd: int) -> list[str]:
    return [
        "gpg",
        "--batch",
        "--yes",
        "--quiet",
        "--no-symkey-cache",
        "--pinentry-mode",
        "loopback",
        "--passphrase-fd",
        str(fd),
    ]


def _password_fd(password: str) -> int:
    """Parolayı bir boruya yazar; okuma ucu gpg'ye verilir (diske yazılmaz)."""
    r, w = os.pipe()
    os.write(w, password.encode("utf-8") + b"\n")
    os.close(w)
    return r


def _tar_ok(code: int) -> bool:
    # 1 = arşivlenirken değişen dosya var (uyarı); arşiv yine geçerli
    return code in (0, 1)


def _archive(base: Path, paths: list[str], target: Path, password: str | None) -> bool:
    if password is None:
        try:
            r = subprocess.run(
                _tar_create(base, paths, str(target)),
                capture_output=True,
                shell=False,
                env=_env(),
            )
        except FileNotFoundError:
            return False
        return _tar_ok(r.returncode)
    fd = _password_fd(password)
    try:
        tar = subprocess.Popen(
            _tar_create(base, paths, "-"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            env=_env(),
        )
        gpg = subprocess.Popen(
            _gpg_base(fd) + ["--symmetric", "--cipher-algo", "AES256", "-o", str(target)],
            stdin=tar.stdout,
            stderr=subprocess.DEVNULL,
            pass_fds=(fd,),
            shell=False,
            env=_env(),
        )
    except FileNotFoundError:
        os.close(fd)
        return False
    os.close(fd)
    assert tar.stdout is not None
    tar.stdout.close()
    gpg_code = gpg.wait()
    return _tar_ok(tar.wait()) and gpg_code == 0


def _extract(
    archive: Path,
    dest: Path,
    password: str | None,
    skip_existing: bool,
    transform: str | None = None,
) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    tar_cmd = ["tar", "-xzpf", "-", "-C", str(dest)]
    if skip_existing:
        tar_cmd.insert(1, "--skip-old-files")
    if transform:
        tar_cmd.insert(1, f"--transform={transform}")
    if password is None:
        tar_cmd[tar_cmd.index("-")] = str(archive)
        try:
            r = subprocess.run(tar_cmd, capture_output=True, shell=False, env=_env())
        except FileNotFoundError:
            return False
        return r.returncode == 0
    fd = _password_fd(password)
    try:
        gpg = subprocess.Popen(
            _gpg_base(fd) + ["-d", str(archive)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(fd,),
            shell=False,
            env=_env(),
        )
        tar = subprocess.Popen(
            tar_cmd, stdin=gpg.stdout, stderr=subprocess.DEVNULL, shell=False, env=_env()
        )
    except FileNotFoundError:
        os.close(fd)
        return False
    os.close(fd)
    assert gpg.stdout is not None
    gpg.stdout.close()
    tar_code = tar.wait()
    return gpg.wait() == 0 and tar_code == 0


def _write_check(pkg: Path, password: str) -> bool:
    fd = _password_fd(password)
    try:
        r = subprocess.run(
            _gpg_base(fd) + ["--symmetric", "--cipher-algo", "AES256", "-o", str(pkg / CHECK_FILE)],
            input=CHECK_TEXT.encode(),
            capture_output=True,
            pass_fds=(fd,),
            shell=False,
            env=_env(),
        )
    except FileNotFoundError:
        return False
    finally:
        os.close(fd)
    return r.returncode == 0


def check_password(pkg: Path, password: str) -> bool:
    fd = _password_fd(password)
    try:
        r = subprocess.run(
            _gpg_base(fd) + ["-d", str(pkg / CHECK_FILE)],
            capture_output=True,
            pass_fds=(fd,),
            shell=False,
            env=_env(),
        )
    except FileNotFoundError:
        return False
    finally:
        os.close(fd)
    return r.returncode == 0 and r.stdout.decode(errors="replace").strip() == CHECK_TEXT


# --- Dışa aktarma ---


@dataclass
class ExportResult:
    package: Path | None
    failed: list[str] = field(default_factory=list)


def package_name(day: date | None = None, host: str | None = None) -> str:
    day = day or date.today()
    host = (host or socket.gethostname() or "linux").replace("/", "-")
    return f"{PACKAGE_PREFIX}-{host}-{day.isoformat()}"


def needs_password(items: list[TransferItem]) -> bool:
    """Şifre/anahtar içeren öğe seçildiyse paket şifrelenmek zorunda."""
    return any(i.selected and i.secret for i in items)


def export_package(
    items: list[TransferItem],
    destination: Path,
    password: str | None,
    on_progress: ProgressCallback | None = None,
) -> ExportResult:
    """Seçili öğeleri hedef klasörde yeni bir taşıma paketine yazar."""
    from linwas.backend.distro import detect_distro

    home = Path.home()
    selected = [i for i in items if i.selected]
    if password is None and needs_password(selected):
        return ExportResult(None, [i.id for i in selected])
    base_name = package_name()
    pkg = destination / base_name
    n = 2
    while pkg.exists():
        pkg = destination / f"{base_name}-{n}"
        n += 1
    try:
        pkg.mkdir(parents=True)
    except OSError:
        return ExportResult(None, [i.id for i in selected])

    desktop = current_desktop()
    distro = detect_distro()
    manifest = Manifest(
        created=date.today().isoformat(),
        hostname=socket.gethostname(),
        user=home.name,
        distro=distro.display_name,
        distro_id=distro.id,
        desktop=desktop,
        encrypted=password is not None,
    )
    if password is not None and not _write_check(pkg, password):
        return ExportResult(None, [i.id for i in selected])

    suffix = ".tar.gz.gpg" if password is not None else ".tar.gz"
    failed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="linwas-transfer-") as tmp:
        stage = Path(tmp)
        for item in selected:
            if on_progress:
                on_progress(item.id)
            if item.id == "programs":
                manifest.programs = list_programs()
                manifest.printers = list_printers()
                manifest.items.append(item)
                continue
            base, paths = home, item.paths
            if item.id == "desktop.settings":
                _stage_desktop(stage, desktop)
                base, paths = stage, ["desktop"]
            elif item.id == "system.wifi":
                _stage_wifi(stage)
                base, paths = stage, ["wifi"]
            if not paths:
                continue
            item.file = item.id + suffix
            if _archive(base, paths, pkg / item.file, password):
                manifest.items.append(item)
            else:
                failed.append(item.id)
                (pkg / item.file).unlink(missing_ok=True)

    data = asdict(manifest)
    # Program listesi ve öğeler dışında gizli bilgi manifest'e yazılmaz
    (pkg / MANIFEST).write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return ExportResult(pkg, failed)


# --- İçe aktarma: kaynak bulma ---


def read_manifest(pkg: Path) -> Manifest | None:
    try:
        data = json.loads((pkg / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
        return None
    try:
        items = [TransferItem(**i) for i in data.get("items", [])]
        programs = [Program(**p) for p in data.get("programs", [])]
    except TypeError:
        return None
    known = {d[0] for d in _STATIC_ITEMS}
    items = [
        i
        for i in items
        if (i.id in known or i.id.startswith("files."))
        and (i.id == "programs" or (i.file and "/" not in i.file and (pkg / i.file).is_file()))
    ]
    return Manifest(
        version=FORMAT_VERSION,
        created=str(data.get("created", "")),
        hostname=str(data.get("hostname", "")),
        user=str(data.get("user", "")),
        distro=str(data.get("distro", "")),
        distro_id=str(data.get("distro_id", "")),
        desktop=str(data.get("desktop", "")),
        encrypted=bool(data.get("encrypted", False)),
        items=items,
        programs=[p for p in programs if p.source in ("apt", "flatpak")],
        printers=[str(p) for p in data.get("printers", [])][:50],
    )


def _search_roots() -> list[Path]:
    user = Path.home().name
    roots = [Path("/media") / user, Path("/run/media") / user, Path("/mnt")]
    uid = os.getuid()
    roots.append(Path(f"/run/user/{uid}/gvfs"))  # GNOME Çevrimiçi Hesaplar (Google Drive vb.)
    return [r for r in roots if r.is_dir()]


def cloud_folders() -> list[Path]:
    """Bağlı bulut hesapları (gvfs: google-drive, onedrive, dav …)."""
    gvfs = Path(f"/run/user/{os.getuid()}/gvfs")
    try:
        return sorted(p for p in gvfs.iterdir() if p.is_dir())
    except OSError:
        return []


def find_packages(max_depth: int = 2) -> list[Path]:
    """Takılı disklerde, bulutta ve ev klasöründe taşıma paketlerini arar."""
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            try:
                if not entry.is_dir() or entry.is_symlink():
                    continue
            except OSError:
                continue
            if entry.name.startswith(PACKAGE_PREFIX) and (entry / MANIFEST).is_file():
                found.append(entry)
            elif depth < max_depth and not entry.name.startswith("."):
                walk(entry, depth + 1)

    for root in [*_search_roots(), Path.home()]:
        walk(root, 1 if root == Path.home() else 0)
    return sorted(set(found))


def _looks_like_home(path: Path) -> bool:
    return (path / ".config").is_dir() or (path / ".local" / "share").is_dir()


def find_old_homes() -> list[Path]:
    """Takılı diğer bölümlerdeki ev klasörleri (çift açılış ya da yeniden kurulum)."""
    current = Path.home().resolve()
    homes: set[Path] = set()
    mounts: list[Path] = []
    try:
        for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2:
                mp = Path(parts[1].replace("\\040", " "))
                if str(mp).startswith(("/media/", "/run/media/", "/mnt")):
                    mounts.append(mp)
    except OSError:
        return []
    for mp in mounts:
        candidates = []
        if (mp / "home").is_dir():  # kök bölümü
            candidates += [p for p in (mp / "home").iterdir() if p.is_dir()]
        with contextlib.suppress(OSError):
            candidates += [p for p in mp.iterdir() if p.is_dir()]  # ayrı /home bölümü
        for c in candidates:
            try:
                if _looks_like_home(c) and c.resolve() != current:
                    homes.add(c)
            except OSError:
                continue
    return sorted(homes)


def open_source(path: Path) -> Source | None:
    if (path / MANIFEST).is_file():
        manifest = read_manifest(path)
        return Source(path, "package", manifest) if manifest else None
    if _looks_like_home(path):
        return Source(path, "home", None)
    return None


def source_items(source: Source) -> list[TransferItem]:
    if source.kind == "package":
        assert source.manifest is not None
        items = [TransferItem(**asdict(i)) for i in source.manifest.items]
        for item in items:
            if item.file:
                item.size = path_size(source.path / item.file)
            item.selected = True
        return items
    items = scan_items(source.path, include_generated=False)
    measure(items, source.path)
    return items


# --- İçe aktarma: programlar ---


def _apt_candidate(name: str) -> bool:
    code, out = _run(["apt-cache", "policy", "--", name], timeout=30)
    if code != 0:
        return False
    for line in out.splitlines():
        key, _, value = line.strip().partition(":")
        if key == "Candidate":
            return value.strip() not in ("", "(none)")
    return False


def _flathub_has(app_id: str) -> bool:
    if not _have("flatpak"):
        return False
    code, _ = _run(["flatpak", "remote-info", "flathub", app_id], timeout=30)
    return code == 0


def _flatpak_for_name(name: str) -> str:
    """APT ile kurulmuş programın Flathub karşılığı (ad tam eşleşirse)."""
    from linwas.backend.flatpak import search_flatpak

    for pkg in search_flatpak(name, max_results=5):
        if pkg.name.strip().lower() == name.strip().lower():
            return pkg.app_id
    return ""


def check_programs(programs: list[Program]) -> list[ProgramChoice]:
    """Her program için yeni sistemde depo paketi / Flatpak var mı (ağ gerekebilir)."""
    from linwas.backend.apt_search import is_installed
    from linwas.backend.flatpak import _installed_ids

    installed_flatpaks = _installed_ids() if _have("flatpak") else set()
    choices = []
    for prog in programs:
        choice = ProgramChoice(program=prog)
        if prog.source == "apt":
            choice.installed = is_installed(prog.id)
            if _apt_candidate(prog.id):
                choice.apt_name = prog.id
            choice.flatpak_id = _flatpak_for_name(prog.name)
        else:
            choice.installed = prog.id in installed_flatpaks
            if _flathub_has(prog.id) or not _have("flatpak"):
                # Flatpak kurulu değilse Flathub kurulumdan sonra eklenir; kimlik bilinir
                choice.flatpak_id = prog.id
            guess = prog.name.strip().lower().replace(" ", "-")
            if guess and _apt_candidate(guess):
                choice.apt_name = guess
        choices.append(choice)
    return choices


# --- İçe aktarma: öğeler ---


@dataclass
class ItemResult:
    ok: bool
    notes: list[str] = field(default_factory=list)  # arayüzde çevrilen kısa kodlar


def _move_aside(target: Path) -> None:
    """Var olan ayar klasörünü silmeden kenara alır (geri dönülebilsin)."""
    if not target.exists():
        return
    stamp = date.today().isoformat()
    aside = target.with_name(f"{target.name}.linwas-onceki-{stamp}")
    n = 2
    while aside.exists():
        aside = target.with_name(f"{target.name}.linwas-onceki-{stamp}-{n}")
        n += 1
    target.rename(aside)


def _copy_tree(src: Path, dst: Path, overwrite: bool) -> bool:
    """Eski ev klasöründen kopyalama (rsync; yoksa cp)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _have("rsync"):
        cmd = ["rsync", "-a"]
        if not overwrite:
            cmd.append("--ignore-existing")
        for pattern in _EXCLUDES:
            cmd.append(f"--exclude={pattern}")
        cmd += [
            "--",
            f"{src}/" if src.is_dir() else str(src),
            f"{dst}/" if src.is_dir() else str(dst),
        ]
    else:
        cmd = ["cp", "-a" if overwrite else "-an", "--", str(src), str(dst.parent)]
    try:
        r = subprocess.run(cmd, capture_output=True, shell=False, env=_env())
    except FileNotFoundError:
        return False
    return r.returncode in (0, 24)  # rsync 24: kaynakta kaybolan dosya (uyarı)


def _target_folder(item: TransferItem) -> str | None:
    """Kişisel klasörün bu sistemdeki adı (ör. eski "Belgeler" → yeni "Documents")."""
    if not item.id.startswith("files."):
        return None
    from linwas.backend.personal_backup import user_folders

    key = item.id[len("files.") :].upper()
    for folder in user_folders():
        if folder.key == key:
            try:
                return str(folder.path.relative_to(Path.home()))
            except ValueError:
                return None
    return None


def _sed_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in ".[]*^$\\|&":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def import_item(source: Source, item: TransferItem, password: str | None) -> ItemResult:
    home = Path.home()
    target_rel = _target_folder(item)
    replace = item.kind in ("app", "system") or item.id in ("desktop.launchers", "desktop.linwas")

    if item.id in ("desktop.settings", "system.wifi"):
        if source.kind != "package":
            return ItemResult(False, ["not_in_home_source"])
        with tempfile.TemporaryDirectory(prefix="linwas-transfer-") as tmp:
            if not _extract(source.path / item.file, Path(tmp), password, skip_existing=False):
                return ItemResult(False, ["extract_failed"])
            if item.id == "desktop.settings":
                return apply_desktop_settings(Path(tmp) / "desktop", current_desktop())
            return import_wifi(Path(tmp) / "wifi" / "wifi.json")

    if source.kind == "package":
        if replace:
            for rel in item.paths:
                _move_aside(home / rel)
        transform = None
        if target_rel and item.paths and item.paths[0] != target_rel:
            src = _sed_escape(item.paths[0])
            transform = f"s|^{src}|{_sed_escape(target_rel)}|"
        ok = _extract(
            source.path / item.file,
            home,
            password,
            skip_existing=not replace,
            transform=transform,
        )
        return ItemResult(ok, [] if ok else ["extract_failed"])

    ok = True
    for rel in item.paths:
        src = source.path / rel
        if not src.exists():
            continue
        dest_rel = target_rel or rel
        if replace:
            _move_aside(home / dest_rel)
        ok = _copy_tree(src, home / dest_rel, overwrite=replace) and ok
    return ItemResult(ok, [] if ok else ["copy_failed"])


def _theme_exists(name: str, kind: str) -> bool:
    if not name:
        return False
    dirs = (
        [Path("/usr/share/themes"), Path.home() / ".themes", Path.home() / ".local/share/themes"]
        if kind == "gtk"
        else [Path("/usr/share/icons"), Path.home() / ".icons", Path.home() / ".local/share/icons"]
    )
    return any((d / name).is_dir() for d in dirs)


def _load_dconf(desktop_dir: Path) -> bool:
    ok = False
    for ini in sorted(desktop_dir.glob("dconf_*.ini")):
        text = ini.read_text(encoding="utf-8")
        first, _, body = text.partition("\n")
        path = first.lstrip("# ").strip()
        if not (path.startswith("/org/") and path.endswith("/")):
            continue
        code, _ = _run(["dconf", "load", path], timeout=15, input_text=body)
        ok = ok or code == 0
    return ok


def apply_desktop_settings(desktop_dir: Path, target: str) -> ItemResult:
    """Aynı masaüstüyse birebir; farklıysa ortak ayarlar karşılığına çevrilir."""
    from linwas.backend import appearance

    try:
        common = json.loads((desktop_dir / "common.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ItemResult(False, ["extract_failed"])
    notes: list[str] = []
    source_desktop = str(common.get("desktop", ""))

    # Duvar kağıdı ~/.local/share/backgrounds altına kopyalanır
    wp_file = common.get("wallpaper_file")
    wallpaper: Path | None = None
    if isinstance(wp_file, str) and "/" not in wp_file and (desktop_dir / wp_file).is_file():
        wallpaper = Path.home() / ".local/share/backgrounds" / f"linwas-tasima-{wp_file}"
        wallpaper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(desktop_dir / wp_file, wallpaper)

    if source_desktop == target and target in _DCONF_PATHS:
        _load_dconf(desktop_dir)
    elif source_desktop == target == "xfce":
        xdir = Path.home() / _XFCONF_DIR
        xdir.mkdir(parents=True, exist_ok=True)
        for f in (desktop_dir / "xfconf").glob("*.xml"):
            if f.name in _XFCONF_FILES:
                _move_aside(xdir / f.name)
                shutil.copy2(f, xdir / f.name)
        notes.append("relogin")
    else:
        notes.append("desktop_converted")

    gtk = str(common.get("gtk_theme", ""))
    icon = str(common.get("icon_theme", ""))
    font = str(common.get("font", ""))
    dark = bool(common.get("dark", False))
    if gtk and not _theme_exists(gtk, "gtk"):
        notes.append("missing_gtk_theme:" + gtk)
        gtk = ""
    if icon and not _theme_exists(icon, "icons"):
        notes.append("missing_icon_theme:" + icon)
        icon = ""
    if target == "gnome":
        base = "org.gnome.desktop.interface"
        appearance.set_dark("gnome", dark)
        if gtk:
            _run(["gsettings", "set", base, "gtk-theme", gtk], timeout=5)
        if icon:
            _run(["gsettings", "set", base, "icon-theme", icon], timeout=5)
        if font:
            _run(["gsettings", "set", base, "font-name", font], timeout=5)
        if common.get("left_handed"):
            _run(["gsettings", "set", "org.gnome.desktop.peripherals.mouse", "left-handed", "true"])
    elif target == "cinnamon":
        base = "org.cinnamon.desktop.interface"
        for key, value in (("gtk-theme", gtk), ("icon-theme", icon), ("font-name", font)):
            if value:
                _run(["gsettings", "set", base, key, value], timeout=5)
    elif target == "xfce":
        for prop, value in (
            ("/Net/ThemeName", gtk),
            ("/Net/IconThemeName", icon),
            ("/Gtk/FontName", font),
        ):
            if value:
                _run(["xfconf-query", "-c", "xsettings", "-p", prop, "-s", value], timeout=5)
    else:
        notes.append("desktop_unsupported")
    if wallpaper is not None:
        if target in ("gnome", "cinnamon"):
            appearance.set_wallpaper(target, wallpaper)
        else:
            notes.append("wallpaper_manual:" + str(wallpaper))
    return ItemResult(True, notes)


def import_wifi(path: Path) -> ItemResult:
    try:
        networks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ItemResult(False, ["extract_failed"])
    code, out = _run(["nmcli", "-t", "-f", "NAME", "connection", "show"], timeout=15)
    existing = {line.replace("\\:", ":") for line in out.splitlines()} if code == 0 else set()
    added = skipped = 0
    for net in networks if isinstance(networks, list) else []:
        name, ssid = str(net.get("name", "")), str(net.get("ssid", ""))
        mgmt, psk = str(net.get("key_mgmt", "")), str(net.get("psk", ""))
        if not ssid or name in existing:
            skipped += 1
            continue
        cmd = ["nmcli", "connection", "add", "type", "wifi", "con-name", name, "ssid", ssid]
        if mgmt in ("wpa-psk", "sae") and psk:
            cmd += ["wifi-sec.key-mgmt", mgmt, "wifi-sec.psk", psk]
        elif mgmt not in ("", "none"):
            skipped += 1  # kurumsal (802.1X) ya da şifresi okunamamış ağ
            continue
        if _run(cmd, timeout=30)[0] == 0:
            added += 1
        else:
            skipped += 1
    return ItemResult(True, [f"wifi_added:{added}", f"wifi_skipped:{skipped}"])


def clean_note_value(note: str) -> tuple[str, str]:
    """ "kod:değer" notunu ayırır."""
    code, _, value = note.partition(":")
    return code, value
