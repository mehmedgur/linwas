# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Windows programı (.exe / .msi) risk analizi — salt okunur, root gerekmez.

PE başlığından mimari, alt sistem, imza tablosu ve .NET bilgisi; sürüm kaynağından
(VS_VERSION_INFO) şirket/ürün adı okunur. Linux'ta Authenticode imzası doğrulanamaz;
yalnızca imzanın *var olup olmadığı* bildirilir. Dosya hiçbir yere gönderilmez.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"

# PE makine türleri
_MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64", 0x1C4: "arm"}
# Data directory sıraları (PE/COFF belirtimi)
_DIR_SECURITY = 4
_DIR_CLR = 14
# MSI (OLE bileşik belge) imzası
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
# Sürüm kaynağındaki alanlar (UTF-16LE anahtarlar)
_VERSION_KEYS = ("CompanyName", "ProductName", "FileDescription", "ProductVersion")
# Belge/medya gibi görünen ama programı gizleyen çift uzantı (ör. fatura.pdf.exe)
_RE_DISGUISED = re.compile(
    r"\.(pdf|docx?|xlsx?|pptx?|txt|jpe?g|png|gif|mp[34]|avi|mkv|zip|rar)\.(exe|scr|com|msi)$",
    re.IGNORECASE,
)
# İçerikte aranan kurulum programı işaretleri (ilk birkaç MB)
_INSTALLER_MARKERS = (
    (b"Inno Setup", "inno"),
    (b"Nullsoft", "nsis"),
    (b"NSIS", "nsis"),
    (b"InstallShield", "installshield"),
    (b"WiX", "wix"),
)
_SCAN_BYTES = 4 * 1024 * 1024

HIGH_REASONS = {"not_windows_program", "disguised", "arm"}
MEDIUM_REASONS = {"unsigned", "unknown_publisher"}


@dataclass
class ExeInfo:
    path: str
    kind: str = ""  # "exe" | "msi"
    arch: str = ""  # "x86" | "x64" | "arm64" | "arm" | ""
    gui: bool = True  # False: konsol programı
    signed: bool = False  # imza tablosu var (doğrulanmadı)
    dotnet: bool = False
    installer: str = ""  # "inno" | "nsis" | "msi" | "installshield" | "wix" | ""
    company: str = ""
    product: str = ""
    description: str = ""
    version: str = ""
    size: int = 0
    sha256: str = ""
    origin_url: str = ""  # tarayıcının bıraktığı indirme adresi (varsa)
    reasons: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def risk(self) -> str:
        """ "high" | "medium" | "low"."""
        if HIGH_REASONS & set(self.reasons):
            return "high"
        if MEDIUM_REASONS & set(self.reasons):
            return "medium"
        return "low"

    @property
    def display_name(self) -> str:
        return self.product or self.description or Path(self.path).stem


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def parse_pe(head: bytes) -> dict[str, object] | None:
    """PE başlığını çözer; PE değilse None. `head`: dosyanın başı (en az birkaç KB)."""
    try:
        if head[:2] != b"MZ":
            return None
        pe = _u32(head, 0x3C)
        if head[pe : pe + 4] != b"PE\0\0":
            return None
        coff = pe + 4
        machine = _u16(head, coff)
        opt = coff + 20
        magic = _u16(head, opt)
        if magic == 0x10B:  # PE32
            subsystem_off, dirs_off = opt + 68, opt + 96
        elif magic == 0x20B:  # PE32+
            subsystem_off, dirs_off = opt + 68, opt + 112
        else:
            return None
        count = _u32(head, dirs_off - 4)

        def directory_size(index: int) -> int:
            if index >= count:
                return 0
            return _u32(head, dirs_off + index * 8 + 4)

        return {
            "arch": _MACHINES.get(machine, ""),
            "gui": _u16(head, subsystem_off) == 2,  # 2: Windows GUI, 3: konsol
            "signed": directory_size(_DIR_SECURITY) > 0,
            "dotnet": directory_size(_DIR_CLR) > 0,
        }
    except struct.error:
        return None


def parse_version_strings(data: bytes) -> dict[str, str]:
    """Sürüm kaynağındaki StringFileInfo değerleri (UTF-16LE anahtar → değer).

    Yapıyı tam çözmek yerine anahtar aranır: anahtardan sonra 4 bayt hizalama dolgusu,
    ardından sıfırla biten UTF-16 değer gelir.
    """
    found: dict[str, str] = {}
    for key in _VERSION_KEYS:
        needle = key.encode("utf-16-le") + b"\0\0"
        idx = data.find(needle)
        if idx < 0:
            continue
        pos = idx + len(needle)
        while pos + 1 < len(data) and data[pos : pos + 2] == b"\0\0":
            pos += 2
        end = pos
        while end + 1 < len(data) and data[end : end + 2] != b"\0\0":
            end += 2
        value = data[pos:end].decode("utf-16-le", errors="ignore").strip()
        if value and value.isprintable():
            found[key] = value[:120]
    return found


def detect_installer(data: bytes) -> str:
    for marker, name in _INSTALLER_MARKERS:
        if marker in data:
            return name
    return ""


def _origin_url(path: Path) -> str:
    """Chrome/Firefox gibi tarayıcıların indirilen dosyaya yazdığı adres (xattr)."""
    for attr in ("user.xdg.origin.url", "user.xdg.referrer.url"):
        try:
            return os.getxattr(path, attr).decode("utf-8", errors="replace")
        except (OSError, AttributeError):
            continue
    return ""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect(path: str | Path) -> ExeInfo:
    p = Path(path)
    info = ExeInfo(path=str(p))
    suffix = p.suffix.lower()
    if suffix not in (".exe", ".msi") or not p.is_file():
        info.error = "not an .exe or .msi file"
        return info
    info.kind = suffix[1:]
    try:
        info.size = p.stat().st_size
        with p.open("rb") as f:
            data = f.read(_SCAN_BYTES)
        info.sha256 = _sha256(p)
    except OSError as exc:
        info.error = str(exc)
        return info
    info.origin_url = _origin_url(p)

    reasons: list[str] = []
    if _RE_DISGUISED.search(p.name):
        reasons.append("disguised")

    if info.kind == "msi":
        info.installer = "msi"
        if not data.startswith(_OLE_MAGIC):
            reasons.append("not_windows_program")
    else:
        pe = parse_pe(data)
        if pe is None:
            reasons.append("not_windows_program")
        else:
            info.arch = str(pe["arch"])
            info.gui = bool(pe["gui"])
            info.signed = bool(pe["signed"])
            info.dotnet = bool(pe["dotnet"])
            if info.arch in ("arm64", "arm"):
                reasons.append("arm")
            info.installer = detect_installer(data)

    strings = parse_version_strings(data)
    info.company = strings.get("CompanyName", "")
    info.product = strings.get("ProductName", "")
    info.description = strings.get("FileDescription", "")
    info.version = strings.get("ProductVersion", "")

    # MSI imzası OLE akışında; bu basit analizde denetlenmez
    if info.kind == "exe" and not info.signed and "not_windows_program" not in reasons:
        reasons.append("unsigned")
    if not info.company and "not_windows_program" not in reasons:
        reasons.append("unknown_publisher")
    info.reasons = reasons
    return info


def virustotal_url(sha256: str) -> str:
    """Yalnızca özet (hash) ile VirusTotal sayfası; dosyanın kendisi gönderilmez."""
    return f"https://www.virustotal.com/gui/file/{sha256}"


# --- Linux alternatifi ---


def _load_alternatives() -> dict[str, dict]:
    try:
        data = json.loads((_DATA / "windows_alternatives.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def find_alternative(info: ExeInfo, mapping: dict[str, dict] | None = None) -> tuple[str, dict]:
    """(anahtar, kayıt) — ürün adı, açıklama veya dosya adında Windows programı geçiyorsa.

    Eşleşme yoksa ("", {}). Kısa anahtarlar (ör. "word") yalnızca tam kelime olarak eşleşir.
    """
    mapping = _load_alternatives() if mapping is None else mapping
    haystack = " ".join(
        (info.product, info.description, Path(info.path).stem.replace("_", " ").replace("-", " "))
    ).lower()
    # Uzun anahtar önce: "after effects" "effects"ten önce denenir
    for key in sorted(mapping, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(key.lower())}(?![a-z0-9])", haystack):
            return key, mapping[key]
    return "", {}
