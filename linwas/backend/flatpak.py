"""Flatpak paket arama (salt okunur).

Flatpak kurulu değilse tüm fonksiyonlar boş/False döner.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class FlatpakPackage:
    app_id: str  # ör. "org.videolan.VLC"
    name: str  # görünen ad
    description: str
    version: str
    installed: bool


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def is_available() -> bool:
    return bool(_run(["which", "flatpak"], timeout=3).strip())


def _installed_ids() -> set[str]:
    out = _run(["flatpak", "list", "--columns=application"])
    return {line.strip() for line in out.splitlines() if line.strip()}


def search_flatpak(query: str, max_results: int = 20) -> list[FlatpakPackage]:
    """Flathub'da arama yapar; hata/eksik durumunda boş liste döner."""
    if not query.strip() or not is_available():
        return []
    try:
        # --columns: application,name,description,version
        out = _run(
            ["flatpak", "search", "--columns=application,name,description,version", "--", query]
        )
        installed = _installed_ids()
        packages: list[FlatpakPackage] = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            app_id = parts[0].strip()
            name = parts[1].strip() if len(parts) > 1 else app_id
            desc = parts[2].strip() if len(parts) > 2 else ""
            ver = parts[3].strip() if len(parts) > 3 else ""
            if not app_id or app_id == "Application ID":
                continue
            packages.append(
                FlatpakPackage(
                    app_id=app_id,
                    name=name,
                    description=desc,
                    version=ver,
                    installed=app_id in installed,
                )
            )
            if len(packages) >= max_results:
                break
        return packages
    except Exception:
        return []


def install_command(app_id: str) -> list[str]:
    """Flatpak kurulum komutunu döner (kuyruğa göre değil, doğrudan)."""
    return ["flatpak", "install", "-y", "flathub", app_id]
