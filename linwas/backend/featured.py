# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Programlar › Keşfet: öne çıkan programlar (data/featured_apps.json).

Her program için kurulum kaynağı sistemde çözülür: dağıtım deposunda varsa APT,
yoksa üreticinin resmi deposu (third_party_apps.json), o da yoksa Flathub.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"

# Kategori kimliği → İngilizce ad (arayüzde çevrilir); sıra gösterim sırasıdır
CATEGORIES: dict[str, str] = {
    "internet": "Internet",
    "office": "Office",
    "graphics": "Graphics & Photo",
    "media": "Music & Video",
    "communication": "Communication",
    "tools": "Tools",
    "education": "Education",
}


@dataclass
class FeaturedApp:
    id: str
    name: str
    category: str
    text: dict[str, str]  # dil → kısa açıklama
    apt: list[str] = field(default_factory=list)
    flatpak: str = ""
    third_party: str = ""
    icon: str = ""
    # resolve() doldurur
    source: str = ""  # "apt" | "third-party" | "flatpak" | "" (bu sistemde kurulamaz)
    package: str = ""  # APT adı / Flatpak kimliği / üçüncü taraf kimliği
    installed: bool = False


def load(path: Path | None = None) -> list[FeaturedApp]:
    try:
        data = json.loads((path or _DATA / "featured_apps.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    apps = []
    for raw in data.get("apps", []):
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        apps.append(
            FeaturedApp(
                id=raw["id"],
                name=raw.get("name", raw["id"]),
                category=raw.get("category", "tools"),
                text={"tr": raw.get("tr", ""), "en": raw.get("en", "")},
                apt=list(raw.get("apt") or []),
                flatpak=raw.get("flatpak", ""),
                third_party=raw.get("third_party", ""),
                icon=raw.get("icon", ""),
            )
        )
    return apps


def _run(cmd: list[str], timeout: int = 30) -> str:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return r.stdout


def parse_policy(out: str) -> dict[str, tuple[bool, bool]]:
    """`apt-cache policy a b c` → {ad: (kurulu mu, depoda aday var mı)}."""
    result: dict[str, tuple[bool, bool]] = {}
    name = ""
    installed = candidate = False
    for line in out.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            if name:
                result[name] = (installed, candidate)
            name = line.rstrip()[:-1]
            installed = candidate = False
        elif line.strip().startswith("Installed:"):
            installed = line.split(":", 1)[1].strip() != "(none)"
        elif line.strip().startswith("Candidate:"):
            candidate = line.split(":", 1)[1].strip() != "(none)"
    if name:
        result[name] = (installed, candidate)
    return result


def _third_party_packages() -> dict[str, str]:
    """Üçüncü taraf kimliği → APT paket adı."""
    try:
        raw = json.loads((_DATA / "third_party_apps.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {r["id"]: r["package"] for r in raw if isinstance(r, dict) and "id" in r}


def resolve(apps: list[FeaturedApp], flatpak_available: bool) -> None:
    """Kaynak ve kurulu bilgisini sistemden doldurur (tek apt-cache, tek flatpak çağrısı)."""
    tp_packages = _third_party_packages()
    names = {n for a in apps for n in a.apt}
    names |= {tp_packages[a.third_party] for a in apps if a.third_party in tp_packages}
    policy = parse_policy(_run(["apt-cache", "policy", "--", *sorted(names)])) if names else {}
    flatpaks: set[str] = set()
    if flatpak_available:
        out = _run(["flatpak", "list", "--app", "--columns=application"])
        flatpaks = {line.strip() for line in out.splitlines() if line.strip()}

    for app in apps:
        tp_pkg = tp_packages.get(app.third_party, "")
        app.installed = (
            any(policy.get(n, (False, False))[0] for n in app.apt)
            or (bool(tp_pkg) and policy.get(tp_pkg, (False, False))[0])
            or app.flatpak in flatpaks
        )
        apt_name = next((n for n in app.apt if policy.get(n, (False, False))[1]), "")
        if apt_name:
            app.source, app.package = "apt", apt_name
        elif app.third_party in tp_packages:
            app.source, app.package = "third-party", app.third_party
        elif app.flatpak and flatpak_available:
            app.source, app.package = "flatpak", app.flatpak
        else:
            app.source, app.package = "", ""


def matches(app: FeaturedApp, query: str) -> bool:
    q = query.casefold().strip()
    return bool(q) and (
        q in app.name.casefold() or any(q in t.casefold() for t in app.text.values())
    )
