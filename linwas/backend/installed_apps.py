"""Kurulu programlar listesi (salt okunur, root gerekmez).

Yalnızca kullanıcıya yönelik masaüstü uygulamaları listelenir:
- APT: /usr/share/applications altındaki .desktop dosyaları → `dpkg-query -S` ile paket
- Flatpak: `flatpak list --app`
- Snap: /var/lib/snapd/desktop/applications altında .desktop dosyası olan snap'ler

Kurulma tarihi APT'de dpkg günlüklerinden (dpkg(1), --log) okunur; günlükler
zamanla silindiği için bulunamazsa None döner. Flatpak ve Snap'te None.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from linwas.backend.packages import list_upgradable

APT_DESKTOP_DIR = Path("/usr/share/applications")
SNAP_DESKTOP_DIR = Path("/var/lib/snapd/desktop/applications")
SNAP_FILES_DIR = Path("/var/lib/snapd/snaps")
DPKG_LOG_DIR = Path("/var/log")
# Kurulum sırasında kurulu paketlerin listesi (Debian/Pardus: status, Ubuntu: initial-status.gz)
INSTALLER_STATUS_FILES = (
    Path("/var/log/installer/status"),
    Path("/var/log/installer/initial-status.gz"),
)
_THIRD_PARTY_FILE = Path(__file__).resolve().parent.parent / "data" / "third_party_apps.json"


@dataclass
class InstalledApp:
    id: str  # APT paket adı, Flatpak kimliği veya snap adı
    name: str  # görünen ad
    icon: str  # simge adı veya yolu; boş olabilir
    source: str  # "apt" | "flatpak" | "snap" | "third-party"
    size_bytes: int | None = None
    installed_on: date | None = None
    update_available: bool = False
    preinstalled: bool = False  # sistemle birlikte gelmiş
    user_install: bool = False  # Flatpak --user kurulumu (şimdilik kaldırılamaz)
    classic: bool = False  # Snap classic kipi


def _run(cmd: list[str], timeout: int = 30) -> str:
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


# --- .desktop dosyaları ---


def _ui_languages() -> list[str]:
    """Name[xx] anahtarları için dil kodları: ör. ["tr_TR", "tr"]."""
    lang = os.environ.get("LANGUAGE", "").split(":")[0]
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if lang:
            break
        lang = os.environ.get(var, "")
    lang = lang.split(".")[0].split("@")[0]
    if not lang or lang in ("C", "POSIX"):
        return []
    return [lang, lang.split("_")[0]] if "_" in lang else [lang]


def parse_desktop_entry(text: str, languages: list[str] | None = None) -> dict[str, str] | None:
    """[Desktop Entry] bölümünü okur; listelenmemesi gereken girişte None döner.

    Döner: {"name": ..., "icon": ...}
    """
    languages = languages or []
    values: dict[str, str] = {}
    in_entry = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry or "=" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values.setdefault(key.strip(), value.strip())

    if values.get("Type") != "Application":
        return None
    if values.get("NoDisplay", "").lower() == "true" or values.get("Hidden", "").lower() == "true":
        return None
    name = next((values[f"Name[{lg}]"] for lg in languages if f"Name[{lg}]" in values), "")
    name = name or values.get("Name", "")
    if not name:
        return None
    return {"name": name, "icon": values.get("Icon", "")}


def _read_desktop_files(directory: Path) -> dict[Path, dict[str, str]]:
    languages = _ui_languages()
    entries: dict[Path, dict[str, str]] = {}
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.desktop")):
        try:
            entry = parse_desktop_entry(path.read_text(encoding="utf-8"), languages)
        except (OSError, UnicodeDecodeError):
            continue
        if entry:
            entries[path] = entry
    return entries


# --- APT ---


def parse_dpkg_search(output: str) -> dict[str, str]:
    """`dpkg-query -S` çıktısı → {yol: paket}. "pkg1, pkg2: yol" satırında ilk paket alınır."""
    owners: dict[str, str] = {}
    for line in output.splitlines():
        if ": " not in line or line.startswith("diversion"):
            continue
        pkgs, _, path = line.partition(": ")
        first = pkgs.split(",")[0].strip().split(":")[0]  # mimari eki atılır
        if first and path:
            owners[path.strip()] = first
    return owners


_RE_LOG_INSTALL = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} install ([^\s:]+)(?::\S+)? ")


def parse_dpkg_log_installs(lines: Iterable[str]) -> dict[str, date]:
    """dpkg günlük satırlarından her paketin son "install" tarihini döner.

    Biçim (dpkg(1)): "YYYY-MM-DD HH:MM:SS install paket:mimari eski-sürüm yeni-sürüm"
    """
    found: dict[str, date] = {}
    for line in lines:
        m = _RE_LOG_INSTALL.match(line)
        if not m:
            continue
        try:
            day = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        pkg = m.group(2)
        if pkg not in found or day > found[pkg]:
            found[pkg] = day
    return found


def _dpkg_log_lines(log_dir: Path = DPKG_LOG_DIR) -> Iterable[str]:
    for path in sorted(log_dir.glob("dpkg.log*")):
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                    yield from fh
            else:
                with path.open(encoding="utf-8", errors="replace") as fh:
                    yield from fh
        except OSError:
            continue


def parse_installer_status(text: str) -> set[str]:
    """dpkg status biçimindeki dosyadan kurulu paket adlarını döner."""
    names: set[str] = set()
    pkg = ""
    for line in text.splitlines():
        if line.startswith("Package: "):
            pkg = line.split(": ", 1)[1].strip()
        elif line.startswith("Status: ") and pkg and line.rstrip().endswith(" installed"):
            names.add(pkg)
    return names


def _installer_packages() -> set[str]:
    for path in INSTALLER_STATUS_FILES:
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                    return parse_installer_status(fh.read())
            return parse_installer_status(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return set()


def _preinstalled_packages() -> set[str]:
    """Sistemle gelmiş görünen paketler (tahmin).

    Kurulum dosyası yalnızca temel sistemi içerir; masaüstü uygulamaları kurulumda
    bir meta paketin bağımlılığı olarak gelir ve "otomatik kurulmuş" işaretlenir
    (apt-mark(8), showauto). Kullanıcının kendi kurduğu program elle işaretlidir.
    """
    auto = {line.strip() for line in _run(["apt-mark", "showauto"]).splitlines()}
    return _installer_packages() | auto


def is_preinstalled(package: str) -> bool:
    return package in _preinstalled_packages()


def _third_party_packages() -> set[str]:
    try:
        data = json.loads(_THIRD_PARTY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {d["package"] for d in data if isinstance(d, dict) and "package" in d}


def _apt_sizes(names: list[str]) -> dict[str, int]:
    """Installed-Size (KiB, dpkg-query(1)) → bayt."""
    out = _run(["dpkg-query", "-W", "-f=${Package}\t${Installed-Size}\n", "--", *names])
    sizes: dict[str, int] = {}
    for line in out.splitlines():
        pkg, _, size = line.partition("\t")
        if size.strip().isdigit():
            sizes[pkg] = int(size) * 1024
    return sizes


def list_apt_apps() -> list[InstalledApp]:
    entries = _read_desktop_files(APT_DESKTOP_DIR)
    if not entries:
        return []
    owners = parse_dpkg_search(_run(["dpkg-query", "-S", "--", *map(str, entries)], timeout=60))

    # Paket başına tek satır: ilk .desktop dosyasının adı kullanılır
    apps: dict[str, InstalledApp] = {}
    for path, entry in entries.items():
        pkg = owners.get(str(path))
        if pkg and pkg not in apps:
            apps[pkg] = InstalledApp(id=pkg, name=entry["name"], icon=entry["icon"], source="apt")
    if not apps:
        return []

    sizes = _apt_sizes(list(apps))
    dates = parse_dpkg_log_installs(_dpkg_log_lines())
    upgradable = {p.name for p in list_upgradable()}
    preinstalled = _preinstalled_packages()
    third_party = _third_party_packages()
    for app in apps.values():
        app.size_bytes = sizes.get(app.id)
        app.installed_on = dates.get(app.id)
        app.update_available = app.id in upgradable
        app.preinstalled = app.id in preinstalled
        if app.id in third_party:
            app.source = "third-party"
    return list(apps.values())


# --- Flatpak ---

_SIZE_UNITS = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
_RE_SIZE = re.compile(r"^([\d.,]+)\s*([KMGT]?B)$", re.IGNORECASE)


def parse_human_size(text: str) -> int | None:
    """ "123.4 MB" / "1,2 GB" → bayt; okunamazsa None. (Flatpak SI birimleri kullanır.)"""
    m = _RE_SIZE.match(text.strip().replace("\xa0", " "))
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return int(value * _SIZE_UNITS[m.group(2).upper()])


def parse_flatpak_list(output: str) -> list[InstalledApp]:
    """`flatpak list --app --columns=application,name,size,installation` çıktısı."""
    apps: list[InstalledApp] = []
    for line in output.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 4 or not parts[0] or parts[0] == "Application ID":
            continue
        app_id, name, size, installation = parts[:4]
        apps.append(
            InstalledApp(
                id=app_id,
                name=name or app_id,
                icon=app_id,  # Flatpak simgeleri uygulama kimliğiyle dışa aktarılır
                source="flatpak",
                size_bytes=parse_human_size(size),
                user_install=installation == "user",
            )
        )
    return apps


def list_flatpak_apps() -> list[InstalledApp]:
    out = _run(["flatpak", "list", "--app", "--columns=application,name,size,installation"])
    apps = parse_flatpak_list(out)
    if apps:
        updates = _run(["flatpak", "remote-ls", "--updates", "--app", "--columns=application"])
        pending = {line.strip() for line in updates.splitlines() if line.strip()}
        for app in apps:
            app.update_available = app.id in pending
    return apps


# --- Snap ---


def parse_snap_list(output: str) -> dict[str, tuple[str, str]]:
    """`snap list` → {ad: (revizyon, notlar)}."""
    snaps: dict[str, tuple[str, str]] = {}
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6:
            snaps[parts[0]] = (parts[2], parts[-1])
    return snaps


def parse_snap_refresh_list(output: str) -> set[str]:
    """`snap refresh --list` → güncellemesi olan snap adları."""
    lines = output.splitlines()
    if not lines or not lines[0].startswith("Name"):
        return set()
    return {line.split()[0] for line in lines[1:] if line.split()}


def list_snap_apps() -> list[InstalledApp]:
    snaps = parse_snap_list(_run(["snap", "list"]))
    if not snaps:
        return []
    # .desktop adı: <snap>_<uygulama>.desktop
    apps: dict[str, InstalledApp] = {}
    for path, entry in _read_desktop_files(SNAP_DESKTOP_DIR).items():
        snap = path.name.split("_", 1)[0]
        if snap in snaps and snap not in apps:
            rev, notes = snaps[snap]
            size: int | None
            try:
                size = (SNAP_FILES_DIR / f"{snap}_{rev}.snap").stat().st_size
            except OSError:
                size = None
            apps[snap] = InstalledApp(
                id=snap,
                name=entry["name"],
                icon=entry["icon"],
                source="snap",
                size_bytes=size,
                classic="classic" in notes.split(","),
            )
    pending = parse_snap_refresh_list(_run(["snap", "refresh", "--list"], timeout=60))
    for app in apps.values():
        app.update_available = app.id in pending
    return list(apps.values())


def list_installed_apps(include_snap: bool = True) -> list[InstalledApp]:
    """Tüm kaynaklardaki kurulu uygulamaları ada göre sıralı döner."""
    apps = list_apt_apps() + list_flatpak_apps()
    if include_snap:
        apps += list_snap_apps()
    apps.sort(key=lambda a: a.name.casefold())
    return apps


# --- Filtreleme, sıralama ve arama eşleştirme ---

# Kaynağa göre sıralamada grup sırası
SOURCE_ORDER = ("apt", "flatpak", "snap", "third-party")

SORT_KEYS = ("name", "source", "size", "newest", "oldest")


def filter_apps(apps: list[InstalledApp], source: str = "", query: str = "") -> list[InstalledApp]:
    """Kaynağa (boşsa hepsi) ve ad/kimlikte geçen metne göre süzer."""
    q = query.strip().casefold()
    return [
        a
        for a in apps
        if (not source or a.source == source)
        and (not q or q in a.name.casefold() or q in a.id.casefold())
    ]


def sort_apps(apps: list[InstalledApp], key: str = "name") -> list[InstalledApp]:
    """Yeni sıralı liste döner. Tarihi bilinmeyenler iki tarih sıralamasında da en altta."""
    by_name = sorted(apps, key=lambda a: a.name.casefold())
    if key == "source":
        order = {s: i for i, s in enumerate(SOURCE_ORDER)}
        return sorted(by_name, key=lambda a: order.get(a.source, len(order)))
    if key == "size":
        return sorted(by_name, key=lambda a: a.size_bytes or 0, reverse=True)
    if key in ("newest", "oldest"):
        known = [a for a in by_name if a.installed_on]
        unknown = [a for a in by_name if not a.installed_on]
        known.sort(key=lambda a: a.installed_on, reverse=key == "newest")  # type: ignore[arg-type, return-value]
        return known + unknown
    return by_name


def match_installed(query: str, apps: list[InstalledApp]) -> list[InstalledApp]:
    """Aranan metin kurulu bir programın adında veya kimliğinde geçiyorsa onları döner."""
    if len(query.strip()) < 2:
        return []
    return filter_apps(apps, query=query)


def is_other_version(package: str, installed: list[InstalledApp]) -> InstalledApp | None:
    """Kurulu olmayan `package`, kurulu bir programın başka sürümü mü?

    Örnek: `firefox` aranırken `firefox-esr` kurulu. Ad öneki tek başına yetmez
    (`gnome` ile `gnome-2048`), bu yüzden kurulu programın görünen adı da
    paketin ilk sözcüğüyle başlamalı ("Firefox ESR").
    """
    for app in installed:
        if app.id == package or app.source not in ("apt", "third-party"):
            continue
        # Yalnızca kurulu paket, aranan paketin bir türeviyse (firefox → firefox-esr).
        # Ters yön (firefox-esr → firefox-esr-mobile-config) eklenti/parçadır, sürüm değil.
        base = package.split("-")[0]
        if app.id.startswith(package + "-") and app.name.casefold().startswith(base.casefold()):
            return app
    return None


# --- Güncellemeler sayfası için ---


@dataclass
class AppUpdate:
    source: str  # "flatpak" | "snap"
    id: str
    name: str


def pending_app_updates(include_snap: bool = True) -> list[AppUpdate]:
    """Güncellemesi bekleyen Flatpak uygulamaları ve snap'ler (masaüstü taraması yapmadan)."""
    updates: list[AppUpdate] = []
    out = _run(["flatpak", "remote-ls", "--updates", "--app", "--columns=application,name"])
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if parts and parts[0] and parts[0] != "Application ID":
            updates.append(AppUpdate("flatpak", parts[0], parts[1] if len(parts) > 1 else parts[0]))
    if include_snap:
        for name in sorted(
            parse_snap_refresh_list(_run(["snap", "refresh", "--list"], timeout=60))
        ):
            updates.append(AppUpdate("snap", name, name))
    return updates
