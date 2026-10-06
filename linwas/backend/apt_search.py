"""APT paket arama ve bilgi sorgulama (salt okunur)."""

from __future__ import annotations

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


def _apt_show_batch(names: list[str]) -> dict[str, tuple[str, str, str]]:
    """apt-cache show ile paket bilgilerini toplu çeker.

    Döner: {name: (version, description, section)}
    """
    if not names:
        return {}
    out = _run(["apt-cache", "show", "--no-all-versions"] + names, timeout=20)

    result: dict[str, tuple[str, str, str]] = {}
    pkg = ver = desc = section = ""
    for line in out.splitlines():
        if line.startswith("Package: "):
            pkg = line.split(": ", 1)[1].strip()
            ver = desc = section = ""
        elif line.startswith("Version: "):
            ver = line.split(": ", 1)[1].strip()
        elif line.startswith("Description: ") or line.startswith("Description-tr: "):
            desc = line.split(": ", 1)[1].strip()
        elif line.startswith("Section: "):
            section = line.split(": ", 1)[1].strip()
        elif line == "" and pkg:
            if pkg not in result:
                result[pkg] = (ver, desc, section)
            pkg = ver = desc = section = ""
    if pkg and pkg not in result:
        result[pkg] = (ver, desc, section)
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
        names = names[:max_results]
        if not names:
            return []

        installed = _installed_names()
        details = _apt_show_batch(names)

        packages: list[AptPackage] = []
        for name in names:
            ver, desc, section = details.get(name, ("", "", ""))
            # Kütüphane/geliştirme bölümleri gizle
            if section and _SKIP_SECTIONS.match(section):
                continue
            packages.append(
                AptPackage(
                    name=name,
                    version=ver,
                    description=desc or name,
                    installed=name in installed,
                    section=section,
                )
            )
        return packages
    except Exception:
        return []


def is_installed(package: str) -> bool:
    out = _run(["dpkg-query", "-W", "-f=${Status}", package], timeout=5)
    return "install ok installed" in out
