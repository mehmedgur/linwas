"""Program kaldırma güvenlik denetimi.

Kaldırma işleminden önce paket yöneticisinin sileceği tüm paketler hesaplanır
(`apt-get -s`, root gerekmez) ve kritik paket listesine karşı denetlenir.
Aynı denetim hem arayüzde (onay penceresi) hem root helper'da (çalıştırmadan
hemen önce) yapılır; arayüzün gönderdiği plana güvenilmez.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_CRITICAL_FILE = Path(__file__).resolve().parent.parent / "data" / "critical_packages.json"

# Kritik paket kategorileri; arayüz bunları sade dille açıklar
CATEGORIES = ("desktop", "login", "network", "sound", "system", "linwas")

# `apt-get -s` çıktısı: "Remv paket [sürüm]" veya "Purg paket [sürüm]"
# Mimari eki (paket:i386) olabilir; ad kısmı alınır.
_RE_SIM_LINE = re.compile(r"^(?:Remv|Purg)\s+([a-z0-9][a-z0-9.+\-]+)(?::\S+)?(?:\s|$)")

# Bu öncelikteki paketler sistemin temelidir (Debian Policy 2.5)
_SYSTEM_PRIORITIES = {"required", "important"}


@dataclass(frozen=True)
class BlockedPackage:
    name: str
    category: str  # CATEGORIES'den biri


@dataclass
class AptRemovalPlan:
    """APT kaldırma planı."""

    target: str
    # Hedef + ona bağımlı olduğu için birlikte kaldırılacak paketler
    removed: list[str] = field(default_factory=list)
    # Artık gerekmeyen bağımlılıklar (--autoremove)
    autoremoved: list[str] = field(default_factory=list)
    blocked: list[BlockedPackage] = field(default_factory=list)
    error: str = ""

    @property
    def all_packages(self) -> list[str]:
        return self.removed + self.autoremoved


def load_critical(path: Path = _CRITICAL_FILE) -> dict[str, dict[str, list[str]]]:
    """Kritik paket listesini okur: {"apt": {kategori: [ad]}, "snap": {...}}."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Liste okunamazsa kaldırma hiç yapılamasın diye boş değil, hata
        raise RuntimeError(f"Kritik paket listesi okunamadı: {path}") from None
    return {k: v for k, v in data.items() if not k.startswith("_")}


def parse_simulation(output: str) -> list[str]:
    """`apt-get -s remove/purge` çıktısından kaldırılacak paket adlarını döner."""
    names: list[str] = []
    for line in output.splitlines():
        m = _RE_SIM_LINE.match(line.strip())
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def _apt_env() -> dict[str, str]:
    return {**os.environ, "LANG": "C", "LC_ALL": "C"}


def _simulate(name: str, autoremove: bool) -> tuple[list[str], str]:
    """(paketler, hata) döner. Hata boş değilse simülasyon başarısız."""
    cmd = ["apt-get", "-s", "remove"]
    if autoremove:
        cmd.append("--autoremove")
    cmd += ["--", name]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, shell=False, env=_apt_env()
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)
    if r.returncode != 0:
        return [], (r.stderr or r.stdout).strip()
    return parse_simulation(r.stdout), ""


def _system_priority_packages(names: list[str]) -> set[str]:
    """Önceliği required/important olan veya Essential: yes paketleri döner."""
    if not names:
        return set()
    try:
        r = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Priority}\t${Essential}\n", "--", *names],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            env=_apt_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    found: set[str] = set()
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        pkg, priority, essential = parts[0], parts[1].strip(), parts[2].strip()
        if priority in _SYSTEM_PRIORITIES or essential == "yes":
            found.add(pkg)
    return found


def find_blocked(
    names: list[str],
    critical: dict[str, list[str]],
    system_packages: set[str] | None = None,
) -> list[BlockedPackage]:
    """Listede kritik paket varsa onları kategorileriyle döner."""
    index = {pkg: cat for cat, pkgs in critical.items() for pkg in pkgs}
    blocked: list[BlockedPackage] = []
    for name in names:
        if name in index:
            blocked.append(BlockedPackage(name, index[name]))
        elif system_packages and name in system_packages:
            blocked.append(BlockedPackage(name, "system"))
    return blocked


def plan_apt_removal(name: str) -> AptRemovalPlan:
    """APT paketinin kaldırma planını hesaplar ve kritik paketleri işaretler.

    `remove` ile `purge` aynı paketleri kaldırır; fark yalnızca ayar dosyalarıdır.
    """
    plan = AptRemovalPlan(target=name)
    removed, err = _simulate(name, autoremove=False)
    if err:
        plan.error = err
        return plan
    with_auto, err = _simulate(name, autoremove=True)
    if err:
        plan.error = err
        return plan
    plan.removed = removed
    plan.autoremoved = [p for p in with_auto if p not in removed]
    if not plan.removed:
        plan.error = f"Paket kurulu değil: {name}"
        return plan
    critical = load_critical()["apt"]
    plan.blocked = find_blocked(
        plan.all_packages, critical, _system_priority_packages(plan.all_packages)
    )
    return plan


def snap_blocked(name: str, notes: str = "") -> list[BlockedPackage]:
    """Snap kritikse (temel/çekirdek snap) engel listesi döner.

    `notes`: `snap list` çıktısındaki Notes sütunu (ör. "base", "snapd").
    """
    critical = load_critical().get("snap", {})
    blocked = find_blocked([name], critical)
    if not blocked and any(t in notes.split(",") for t in ("base", "core", "snapd", "kernel")):
        blocked.append(BlockedPackage(name, "system"))
    return blocked
