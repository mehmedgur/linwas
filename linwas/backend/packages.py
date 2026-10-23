"""APT paket sorgulama (salt okunur, root gerekmez).

Paket kurulumu/kaldırma kuyruğa gider ve root helper üzerinden yapılır.
Bu modül yalnızca durum bilgisini okur.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class UpgradablePackage:
    name: str
    installed_version: str
    available_version: str
    is_security: bool
    source: str  # ör. "jammy-security", "yirmiuc-deb"


# Dil bağımsız: `name/source version arch [<herhangi metin>: old_version]`
# Pardus Türkçe çıktısı: "[şundan yükseltilebilir: X]"
# Ubuntu İngilizce çıktısı: "[upgradable from: X]"
# [^\]:]*  → köşeli parantez veya iki nokta içermeyen açıklama metni (dil bağımsız)
# Böylece "2:8.0.1" gibi epoch'lu sürümdeki ikinci ":" yanlış grupla eşleşmez.
_APT_LINE = re.compile(r"^([^/\s]+)/(\S+)\s+(\S+)\s+\S+\s+\[[^\]]:*[^\]:]*:\s*([^\]]+)\]")

_SECURITY_SOURCES = re.compile(r"security", re.IGNORECASE)


def _is_security(source: str) -> bool:
    """Kaynak dizesindeki herhangi bir bileşen 'security' içeriyorsa True döner."""
    return bool(_SECURITY_SOURCES.search(source))


def list_upgradable() -> list[UpgradablePackage]:
    """Güncellenebilir paketlerin listesini döner.

    APT önbelleği eski olabilir; `apt-get update` çalıştırılmaz.
    Hata durumunda boş liste döner.
    """
    try:
        result = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    packages: list[UpgradablePackage] = []
    for line in result.stdout.splitlines():
        m = _APT_LINE.match(line.strip())
        if not m:
            continue
        name, source, available, installed = m.groups()
        packages.append(
            UpgradablePackage(
                name=name,
                installed_version=installed.strip(),
                available_version=available,
                is_security=_is_security(source),
                source=source,
            )
        )
    return packages


def count_upgradable() -> tuple[int, int]:
    """(toplam, güvenlik) güncelleme sayısını döner."""
    pkgs = list_upgradable()
    security = sum(1 for p in pkgs if p.is_security)
    return len(pkgs), security


def apt_cache_age_hours() -> float | None:
    """APT önbelleğinin kaç saat önce güncellendiğini döner; bilinmiyorsa None."""
    cache_file = Path("/var/cache/apt/pkgcache.bin")
    if not cache_file.exists():
        return None
    try:
        mtime = cache_file.stat().st_mtime
        age = (datetime.now().timestamp() - mtime) / 3600
        return round(age, 1)
    except OSError:
        return None
