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


# Desteklenen en düşük sürümler ve güvenlik güncellemesi biten sürümler.
# Pardus 23 ve 25 karar belgesinde açıkça destek listesinde.
_MIN_VERSION: dict[str, tuple[int, ...]] = {
    "ubuntu": (20, 4),
    "debian": (11,),
    "linuxmint": (20,),
    "pardus": (23,),
}
# Bu sürümler (ve altı) destekleniyor ama artık güvenlik güncellemesi almıyor.
_END_OF_LIFE_MAX: dict[str, tuple[int, ...]] = {
    "ubuntu": (20, 4),
    "debian": (11,),
    "linuxmint": (20, 99),
}


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
