"""APT paket arama ve bilgi sorgulama (salt okunur)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AptPackage:
    name: str
    version: str
    description: str
    installed: bool
    section: str  # "utils", "gnome", "games" vb. — libs/devel filtrelemek için
    graphical: bool | None = None  # debtags: masaüstü uygulaması mı; etiket yoksa None


_SKIP_SECTIONS = re.compile(
    r"^(lib|python|perl|ruby|java|php|dev|debug|doc|kernel|linux-)",
    re.IGNORECASE,
)


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _installed_names() -> set[str]:
    """Kurulu paket adlarını döner."""
    out = _run(["dpkg-query", "--show", "--showformat=${Package} ${Status}\n"], timeout=10)
    installed: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[-1] == "installed":
            installed.add(parts[0])
    return installed


_GUI_TAGS = ("interface::graphical", "x11::application")


def _apt_show_batch(names: list[str]) -> dict[str, tuple[str, str, str, bool | None]]:
    """apt-cache show ile paket bilgilerini toplu çeker.

    Döner: {name: (version, description, section, graphical)}; graphical debtags
    (Tag alanı) yoksa None.
    """
    if not names:
        return {}
    out = _run(["apt-cache", "show", "--no-all-versions"] + names, timeout=20)

    result: dict[str, tuple[str, str, str, bool | None]] = {}
    pkg = ver = desc = section = ""
    gui: bool | None = None
    for line in out.splitlines():
        if line.startswith("Package: "):
            pkg = line.split(": ", 1)[1].strip()
            ver = desc = section = ""
            gui = None
        elif line.startswith("Tag: "):
            gui = any(t in line for t in _GUI_TAGS)
        elif line.startswith("Version: "):
            ver = line.split(": ", 1)[1].strip()
        elif line.startswith("Description: ") or line.startswith("Description-tr: "):
            desc = line.split(": ", 1)[1].strip()
        elif line.startswith("Section: "):
            section = line.split(": ", 1)[1].strip()
        elif line == "" and pkg:
            if pkg not in result:
                result[pkg] = (ver, desc, section, gui)
            pkg = ver = desc = section = ""
            gui = None
    if pkg and pkg not in result:
        result[pkg] = (ver, desc, section, gui)
    return result


def search_apt(query: str, max_results: int = 40) -> list[AptPackage]:
    """APT paketlerinde arama yapar; kullanıcıya yönelik uygulamaları döner.

    Hata durumunda boş liste döner.
    """
    if not query.strip():
        return []
    try:
        out = _run(["apt-cache", "search", "--", query], timeout=15)
        # Satır biçimi: "name - description"
        names: list[str] = []
        for line in out.splitlines():
            if " - " not in line:
                continue
            name = line.split(" - ", 1)[0].strip()
            # Dil paketleri (ör. firefox-esr-l10n-tr) program değildir
            if name and not _SKIP_SECTIONS.match(name) and "-l10n-" not in name:
                names.append(name)
        # Grafik olmayanlar sonradan elendiği için daha geniş bir küme incelenir
        names = names[: max_results * 4]
        if not names:
            return []

        installed = _installed_names()
        details = _apt_show_batch(names)

        packages: list[AptPackage] = []
        for name in names:
            ver, desc, section, gui = details.get(name, ("", "", "", None))
            # Kütüphane/geliştirme bölümleri ve etiketi olup grafik olmayanlar gizlenir
            if (section and _SKIP_SECTIONS.match(section)) or gui is False:
                continue
            packages.append(
                AptPackage(
                    name=name,
                    version=ver,
                    description=desc or name,
                    installed=name in installed,
                    section=section,
                    graphical=gui,
                )
            )
        # Önce masaüstü uygulamaları, sonra etiketsizler
        packages.sort(key=lambda p: p.graphical is not True)
        return packages[:max_results]
    except Exception:
        return []


def is_installed(package: str) -> bool:
    out = _run(["dpkg-query", "-W", "-f=${Status}", package], timeout=5)
    return "install ok installed" in out


# --- Türkçe arama ---

_TERMS_FILE = (
    __import__("pathlib").Path(__file__).resolve().parent.parent / "data" / "search_terms_tr.json"
)


def _tr_fold(text: str) -> str:
    """Türkçe büyük/küçük harf duyarsız karşılaştırma (İ/I → i/ı)."""
    return text.replace("İ", "i").replace("I", "ı").lower().strip()


def expand_query(query: str) -> list[str]:
    """Türkçe sözcüğün İngilizce karşılıkları (yoksa boş): önce tam ifade, sonra sözcükler."""

    try:
        terms: dict[str, list[str]] = json.loads(_TERMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    q = _tr_fold(query)
    if q in terms and not q.startswith("_"):
        return list(terms[q])
    found: list[str] = []
    for word in q.split():
        for term in terms.get(word, []):
            if term not in found:
                found.append(term)
    return found
