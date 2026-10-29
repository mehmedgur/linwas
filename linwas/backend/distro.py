# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Dağıtım algılama ve destek durumu.

`/etc/os-release` dosyasını okur, dağıtımı tanır ve Linwas'ın bu sistemi destekleyip
desteklemediğini söyler. Qt'ye bağımlı değildir; metinler arayüz katmanında çevrilir.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

OS_RELEASE_PATHS = (Path("/etc/os-release"), Path("/usr/lib/os-release"))


class SupportStatus(Enum):
    """Linwas'ın bu sistem için destek durumu."""

    SUPPORTED = "supported"
    # Destekleniyor ama dağıtımın güvenlik güncellemeleri bitti.
    END_OF_LIFE = "end_of_life"
    # Debian/Ubuntu ailesinden ama resmi olarak test edilmiyor.
    UNTESTED_FAMILY = "untested_family"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class DistroInfo:
    """os-release dosyasından okunan dağıtım bilgisi."""

    id: str = ""
    name: str = ""
    version_id: str = ""
    pretty_name: str = ""
    id_like: tuple[str, ...] = field(default_factory=tuple)

    @property
    def display_name(self) -> str:
        """Kullanıcıya gösterilecek ad."""
        if self.pretty_name:
            return self.pretty_name
        return f"{self.name} {self.version_id}".strip()


def parse_os_release(text: str) -> dict[str, str]:
    """os-release biçimindeki metni sözlüğe çevirir.

    Biçim: KEY=value satırları; değerler tırnaklı olabilir. Bozuk satırlar atlanır.
    """
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key.isidentifier():
            continue
        try:
            parts = shlex.split(value, posix=True)
        except ValueError:
            continue
        result[key] = parts[0] if parts else ""
    return result


def distro_from_mapping(data: dict[str, str]) -> DistroInfo:
    """Sözlükten `DistroInfo` üretir."""
    return DistroInfo(
        id=data.get("ID", "").lower(),
        name=data.get("NAME", ""),
        version_id=data.get("VERSION_ID", ""),
        pretty_name=data.get("PRETTY_NAME", ""),
        id_like=tuple(data.get("ID_LIKE", "").lower().split()),
    )


def detect_distro(paths: tuple[Path, ...] = OS_RELEASE_PATHS) -> DistroInfo:
    """Sistemdeki dağıtımı algılar. Dosya bulunamazsa boş bilgi döner."""
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        return distro_from_mapping(parse_os_release(text))
    return DistroInfo()


def _version_tuple(version: str) -> tuple[int, ...]:
    """'22.04' -> (22, 4). Sayı olmayan kısımlar 0 sayılır."""
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


# Desteklenen en düşük sürümler. Gömülü PySide6 glibc >= 2.34 istediği için Ubuntu 20.04,
# Debian 11 ve Mint 20 (glibc 2.31) desteklenmiyor (karar: seçenek A).
# Mint 21 Ubuntu 22.04, Pardus 23 Debian 12 tabanlıdır.
_MIN_VERSION: dict[str, tuple[int, ...]] = {
    "ubuntu": (22, 4),
    "debian": (12,),
    "linuxmint": (21,),
    "pardus": (23,),
}
# Bu sürümler (ve altı) destekleniyor ama artık güvenlik güncellemesi almıyor.
# Şu an desteklenen sürümlerin hepsi güvenlik desteği alıyor; bir sürümün desteği bittiğinde
# buraya eklenir (ör. Ubuntu 22.04 için "ubuntu": (22, 4)).
_END_OF_LIFE_MAX: dict[str, tuple[int, ...]] = {}


def evaluate_support(info: DistroInfo) -> SupportStatus:
    """Dağıtımın Linwas tarafından desteklenme durumunu döndürür."""
    # LMDE (Linux Mint Debian Edition) ID olarak 'linuxmint' bildirir ama sürüm numarası
    # farklıdır (ör. 6) ve Debian tabanlıdır; resmi destek listesinde değil.
    if info.id == "linuxmint" and "lmde" in f"{info.name} {info.pretty_name}".lower():
        return SupportStatus.UNTESTED_FAMILY
    if info.id in _MIN_VERSION:
        version = _version_tuple(info.version_id)
        if version < _MIN_VERSION[info.id]:
            return SupportStatus.UNSUPPORTED
        eol_max = _END_OF_LIFE_MAX.get(info.id)
        if eol_max is not None and version <= eol_max:
            return SupportStatus.END_OF_LIFE
        return SupportStatus.SUPPORTED
    if "debian" in info.id_like or "ubuntu" in info.id_like:
        return SupportStatus.UNTESTED_FAMILY
    return SupportStatus.UNSUPPORTED
