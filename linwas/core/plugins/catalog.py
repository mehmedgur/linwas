# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Linwas eklenti kataloğu: imzalı `index.json`, indirme, SHA-256 ve geri çekme listesi.

Katalog Linwas APT deposunun yanında durur (`<depo>/plugins/index.json` + `index.json.sig`) ve
APT deposuyla aynı Linwas anahtarıyla imzalanır. İmza `gpgv` ile doğrulanır (apt'nin bağımlılığı;
her Debian/Ubuntu'da kurulu, yeni Python bağımlılığı gerekmez). Eklenti dosyaları imzalı
indeksteki SHA-256 ile denetlenir. Adres paket derlenirken yazılır
(`/usr/share/linwas/plugin-catalog.json`); deneme için `LINWAS_PLUGIN_CATALOG` ve
`LINWAS_PLUGIN_KEYRING` ortam değişkenleri kullanılabilir.

Biçim (şema 1):
    {
      "schema": 1,
      "plugins": [{"id", "version", "name": T, "description": T, "publisher",
                   "url": "files/<id>-<sürüm>.json", "sha256": "...", "size": 1234}],
      "revoked": [{"id": "...", "versions": ["1.0.0"] | ["*"], "reason": T}]
    }
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from linwas.core.plugins import declarative

CONFIG = Path("/usr/share/linwas/plugin-catalog.json")
KEYRING = Path("/usr/share/keyrings/linwas-archive-keyring.gpg")
ENV_URL = "LINWAS_PLUGIN_CATALOG"
ENV_KEYRING = "LINWAS_PLUGIN_KEYRING"
MAX_INDEX_BYTES = 2 * 1024 * 1024
TIMEOUT = 20

_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CatalogError(Exception):
    """code: not_configured | network | signature | format | checksum"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class CatalogEntry:
    id: str
    version: str
    name: dict[str, str]
    description: dict[str, str]
    publisher: str
    url: str  # mutlak adres
    sha256: str
    size: int


@dataclass
class Catalog:
    entries: list[CatalogEntry] = field(default_factory=list)
    # kimlik → (sürümler ya da {"*"}, neden metni)
    revoked: dict[str, tuple[set[str], dict[str, str]]] = field(default_factory=dict)

    def entry(self, plugin_id: str) -> CatalogEntry | None:
        return next((e for e in self.entries if e.id == plugin_id), None)

    def revoked_reason(self, plugin_id: str, version: str) -> dict[str, str] | None:
        found = self.revoked.get(plugin_id)
        if found and ("*" in found[0] or version in found[0]):
            return found[1]
        return None


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "linwas" / "plugin-catalog"


def catalog_url() -> str:
    """Katalog adresi; yapılandırılmamışsa ""."""
    env = os.environ.get(ENV_URL, "")
    if env:
        return env
    try:
        url = json.loads(CONFIG.read_text(encoding="utf-8")).get("url", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return url if isinstance(url, str) and url.startswith("https://") else ""


def keyring() -> Path:
    env = os.environ.get(ENV_KEYRING, "")
    return Path(env) if env else KEYRING


def _allowed(url: str) -> bool:
    scheme = urlparse(url).scheme
    # file:// yalnızca deneme için ortam değişkeniyle verilen katalogda
    return scheme == "https" or (scheme == "file" and bool(os.environ.get(ENV_URL)))


def _fetch(url: str, limit: int) -> bytes:
    if not _allowed(url):
        raise CatalogError("network", f"not allowed: {url}")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:  # noqa: S310 — https/file denetlendi
            data = resp.read(limit + 1)
    except (OSError, ValueError) as exc:
        raise CatalogError("network", str(exc)) from exc
    if len(data) > limit:
        raise CatalogError("format", "file is too large")
    return data


def verify(data: bytes, signature: bytes, keyring_path: Path | None = None) -> bool:
    """Ayrık imzayı Linwas anahtarıyla doğrular (gpgv; kabuk yok)."""
    ring = keyring_path or keyring()
    if not ring.is_file():
        return False
    with tempfile.TemporaryDirectory(prefix="linwas-catalog-") as tmp:
        data_path = Path(tmp) / "index.json"
        sig_path = Path(tmp) / "index.json.sig"
        data_path.write_bytes(data)
        sig_path.write_bytes(signature)
        try:
            r = subprocess.run(
                ["gpgv", "--keyring", str(ring), str(sig_path), str(data_path)],
                capture_output=True,
                timeout=30,
                shell=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return r.returncode == 0


def parse_index(data: bytes, base_url: str) -> Catalog:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CatalogError("format", str(exc)) from exc
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise CatalogError("format", "schema must be 1")
    catalog = Catalog()
    for item in raw.get("plugins", []):
        try:
            entry = CatalogEntry(
                id=item["id"],
                version=item["version"],
                name=declarative._text(item.get("name"), "name"),
                description=declarative._opt_text(item.get("description"), "description"),
                publisher=str(item.get("publisher", ""))[:80],
                url=urljoin(base_url, item["url"]),
                sha256=item["sha256"],
                size=int(item["size"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogError("format", f"bad entry: {exc}") from exc
        if not (
            declarative._RE_ID.match(entry.id)
            and declarative._RE_VERSION.match(entry.version)
            and _RE_SHA256.match(entry.sha256)
            and 0 < entry.size <= declarative.MAX_FILE_BYTES
            and _allowed(entry.url)
        ):
            raise CatalogError("format", f"bad entry: {entry.id}")
        catalog.entries.append(entry)
    for item in raw.get("revoked", []):
        try:
            versions = {str(v) for v in item["versions"]}
            reason = declarative._opt_text(item.get("reason"), "reason")
            catalog.revoked[str(item["id"])] = (versions, reason)
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalogError("format", f"bad revoked entry: {exc}") from exc
    return catalog


def refresh() -> Catalog:
    """İndeksi ve imzasını indirir, doğrular, önbelleğe yazar."""
    url = catalog_url()
    if not url:
        raise CatalogError("not_configured")
    data = _fetch(url, MAX_INDEX_BYTES)
    signature = _fetch(url + ".sig", 64 * 1024)
    if not verify(data, signature):
        raise CatalogError("signature")
    catalog = parse_index(data, url)
    cache = cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "index.json").write_bytes(data)
        (cache / "index.json.sig").write_bytes(signature)
        (cache / "url").write_text(url, encoding="utf-8")
    except OSError:
        pass
    return catalog


def cached() -> Catalog | None:
    """Ağsız: son indirilen ve imzası yeniden doğrulanan katalog (geri çekme listesi için)."""
    cache = cache_dir()
    try:
        data = (cache / "index.json").read_bytes()
        signature = (cache / "index.json.sig").read_bytes()
        url = (cache / "url").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not verify(data, signature):
        return None
    try:
        return parse_index(data, url)
    except CatalogError:
        return None


def download(entry: CatalogEntry) -> str:
    """Eklenti tanımını indirir; boyut, SHA-256, kimlik ve sürüm imzalı indeksle eşleşmeli."""
    data = _fetch(entry.url, declarative.MAX_FILE_BYTES)
    if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
        raise CatalogError("checksum")
    try:
        text = data.decode("utf-8")
        manifest = declarative.parse(text)
    except (UnicodeDecodeError, declarative.ManifestError) as exc:
        raise CatalogError("format", str(exc)) from exc
    if manifest["id"] != entry.id or manifest["version"] != entry.version:
        raise CatalogError("format", "id or version does not match the catalog")
    return text
