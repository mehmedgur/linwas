"""İzin listesi: root helper'ın çalıştırabileceği işlemler ve parametre doğrulama.

Yeni işlem eklemek için buraya OperationSpec tanımı eklenir. Eklentiler doğrudan
bu listeyi değiştiremez; izin önerileri root helper tarafından onaylanmalıdır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ParamKind(Enum):
    PACKAGE_NAME = "package_name"
    SERVICE_NAME = "service_name"
    HTTPS_URL = "https_url"
    # /usr/share/keyrings/ altındaki .gpg veya .asc dosyası
    KEYRING_PATH = "keyring_path"
    # /etc/apt/sources.list.d/ altındaki .list dosyası adı (yalnızca dosya adı)
    APT_LIST_NAME = "apt_list_name"
    # Tek satır APT kaynak tanımı
    APT_SOURCE_LINE = "apt_source_line"
    # Kurulacak .deb dosyasının mutlak yolu
    DEB_PATH = "deb_path"
    # Yazılacak sistem dosyasının mutlak yolu (izin verilen önekler altında)
    ALLOWED_SYSTEM_PATH = "allowed_system_path"
    # Serbest metin (sistem dosyasına yazılacak içerik vb.)
    TEXT = "text"


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: ParamKind
    required: bool = True


@dataclass(frozen=True)
class OperationSpec:
    params: list[ParamSpec]
    risk: RiskLevel
    label: str = ""  # İngilizce; UI katmanında çevrilir


class ValidationError(ValueError):
    """İzin listesi doğrulama hatası."""


# --- Doğrulayıcılar ---

# Debian paket adı: en az 2 karakter, [a-z0-9][a-z0-9.+\-]*
_RE_PKG = re.compile(r"^[a-z0-9][a-z0-9.+\-]+$")

# systemd birim adı: harfler, rakamlar, - _ . @ : (süslü olmayan)
_RE_SVC = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-@:]*$")

# .list dosyası adı: yalnızca dosya adı, linwas- önekli, .list uzantılı
_RE_LIST_NAME = re.compile(r"^linwas-[a-z0-9\-]+\.list$")

# APT kaynak satırı: deb https://... ile başlamalı; kabuk metachar yok
_RE_APT_SOURCE = re.compile(
    r"^deb\s+https://[a-zA-Z0-9./_\-]+"
    r"(\s+[a-zA-Z0-9./_\-]+)+"
    r"(\s*#.*)?$"
)

# Keyring yolu: /usr/share/keyrings/linwas-*.gpg veya .asc
_KEYRING_DIR = Path("/usr/share/keyrings")
_RE_KEYRING_NAME = re.compile(r"^linwas-[a-z0-9\-]+\.(gpg|asc)$")

# Yazılabilir sistem yolu önekleri
_ALLOWED_WRITE_PREFIXES = (
    "/etc/linwas/",
    "/usr/local/share/linwas/",
    "/usr/share/linwas/",
)


def _validate_package_name(value: str) -> str:
    if not _RE_PKG.match(value):
        raise ValidationError(f"Geçersiz paket adı: {value!r}")
    return value


def _validate_service_name(value: str) -> str:
    if not _RE_SVC.match(value):
        raise ValidationError(f"Geçersiz servis adı: {value!r}")
    # .service uzantısı zorunlu değil; fazla noktalı birim adı da geçerli
    return value


def _validate_https_url(value: str) -> str:
    if not value.startswith("https://"):
        raise ValidationError(f"URL https:// ile başlamalı: {value!r}")
    # Kabuk metakarı yasak
    if any(c in value for c in " \t\n;&|`$<>(){}"):
        raise ValidationError(f"URL geçersiz karakter içeriyor: {value!r}")
    return value


def _validate_keyring_path(value: str) -> str:
    p = Path(value)
    if p.parent != _KEYRING_DIR:
        raise ValidationError(f"Keyring yolu {_KEYRING_DIR} altında olmalı: {value!r}")
    if not _RE_KEYRING_NAME.match(p.name):
        raise ValidationError(f"Keyring dosya adı geçersiz: {p.name!r}")
    return value


def _validate_apt_list_name(value: str) -> str:
    # Yalnızca dosya adı beklenir, yol bileşeni yok
    if "/" in value or ".." in value:
        raise ValidationError(f"APT list adında yol bileşeni olamaz: {value!r}")
    if not _RE_LIST_NAME.match(value):
        raise ValidationError(f"APT list adı geçersiz: {value!r}")
    return value


def _validate_apt_source_line(value: str) -> str:
    if not _RE_APT_SOURCE.match(value.strip()):
        raise ValidationError(f"APT kaynak satırı geçersiz: {value!r}")
    return value.strip()


def _validate_deb_path(value: str) -> str:
    p = Path(value)
    if not p.is_absolute():
        raise ValidationError(f".deb yolu mutlak olmalı: {value!r}")
    if ".." in p.parts:
        raise ValidationError(f".deb yolunda '..' olamaz: {value!r}")
    if p.suffix != ".deb":
        raise ValidationError(f".deb yolu .deb uzantılı olmalı: {value!r}")
    return value


def _validate_allowed_system_path(value: str) -> str:
    p = Path(value)
    if not p.is_absolute():
        raise ValidationError(f"Sistem yolu mutlak olmalı: {value!r}")
    if ".." in p.parts:
        raise ValidationError(f"Sistem yolunda '..' olamaz: {value!r}")
    if not any(value.startswith(prefix) for prefix in _ALLOWED_WRITE_PREFIXES):
        allowed = ", ".join(_ALLOWED_WRITE_PREFIXES)
        raise ValidationError(
            f"Yazılabilir yol şu öneklerden biriyle başlamalı: {allowed} — gelen: {value!r}"
        )
    return value


def _validate_text(value: str) -> str:
    # Serbest metin; boş olabilir, NUL byte yok
    if "\x00" in value:
        raise ValidationError("Metin NUL byte içeremez")
    return value


_VALIDATORS: dict[ParamKind, object] = {
    ParamKind.PACKAGE_NAME: _validate_package_name,
    ParamKind.SERVICE_NAME: _validate_service_name,
    ParamKind.HTTPS_URL: _validate_https_url,
    ParamKind.KEYRING_PATH: _validate_keyring_path,
    ParamKind.APT_LIST_NAME: _validate_apt_list_name,
    ParamKind.APT_SOURCE_LINE: _validate_apt_source_line,
    ParamKind.DEB_PATH: _validate_deb_path,
    ParamKind.ALLOWED_SYSTEM_PATH: _validate_allowed_system_path,
    ParamKind.TEXT: _validate_text,
}


# --- İzin listesi ---


def _op(
    *params: tuple[str, ParamKind],
    risk: RiskLevel,
    label: str = "",
    required: bool = True,
) -> OperationSpec:
    return OperationSpec(
        params=[ParamSpec(name=p[0], kind=p[1], required=required) for p in params],
        risk=risk,
        label=label,
    )


OPERATIONS: dict[str, OperationSpec] = {
    "package.install": _op(
        ("name", ParamKind.PACKAGE_NAME),
        risk=RiskLevel.LOW,
        label="Install package",
    ),
    "package.remove": _op(
        ("name", ParamKind.PACKAGE_NAME),
        risk=RiskLevel.MEDIUM,
        label="Remove package",
    ),
    "package.update_all": OperationSpec(
        params=[],
        risk=RiskLevel.LOW,
        label="Update all packages",
    ),
    "package.update_index": OperationSpec(
        params=[],
        risk=RiskLevel.LOW,
        label="Refresh package index",
    ),
    "service.enable": _op(
        ("name", ParamKind.SERVICE_NAME),
        risk=RiskLevel.LOW,
        label="Enable service",
    ),
    "service.disable": _op(
        ("name", ParamKind.SERVICE_NAME),
        risk=RiskLevel.MEDIUM,
        label="Disable service",
    ),
    "service.restart": _op(
        ("name", ParamKind.SERVICE_NAME),
        risk=RiskLevel.LOW,
        label="Restart service",
    ),
    "apt.add_key": _op(
        ("url", ParamKind.HTTPS_URL),
        ("keyring_path", ParamKind.KEYRING_PATH),
        risk=RiskLevel.HIGH,
        label="Add APT signing key",
    ),
    "apt.add_source": _op(
        ("source_line", ParamKind.APT_SOURCE_LINE),
        ("list_name", ParamKind.APT_LIST_NAME),
        risk=RiskLevel.HIGH,
        label="Add APT source",
    ),
    "deb.install": _op(
        ("path", ParamKind.DEB_PATH),
        risk=RiskLevel.HIGH,
        label="Install .deb file",
    ),
    "file.write_text": _op(
        ("path", ParamKind.ALLOWED_SYSTEM_PATH),
        ("content", ParamKind.TEXT),
        risk=RiskLevel.MEDIUM,
        label="Write configuration file",
    ),
    "snapshot.timeshift_create": OperationSpec(
        params=[],
        risk=RiskLevel.LOW,
        label="Create Timeshift snapshot",
    ),
    "firmware.fwupd_update": OperationSpec(
        params=[],
        risk=RiskLevel.HIGH,
        label="Update firmware via fwupd",
    ),
    "snapshot.timeshift_restore": _op(
        ("name", ParamKind.SERVICE_NAME),  # snapshot adı güvenli karakter içerir
        risk=RiskLevel.HIGH,
        label="Restore Timeshift snapshot",
    ),
    "snapshot.timeshift_delete": _op(
        ("name", ParamKind.SERVICE_NAME),
        risk=RiskLevel.MEDIUM,
        label="Delete Timeshift snapshot",
    ),
    "apt.clean": OperationSpec(
        params=[],
        risk=RiskLevel.LOW,
        label="Clean APT package cache",
    ),
    "journal.vacuum": OperationSpec(
        params=[],
        risk=RiskLevel.LOW,
        label="Trim system journal logs",
    ),
}


def validate(op_id: str, params: dict[str, str]) -> dict[str, str]:
    """İşlem adını ve parametrelerini doğrular; temizlenmiş parametre sözlüğü döner.

    Bilinmeyen işlem veya geçersiz parametre varsa ValidationError fırlatır.
    """
    spec = OPERATIONS.get(op_id)
    if spec is None:
        raise ValidationError(f"Bilinmeyen işlem: {op_id!r}")

    validated: dict[str, str] = {}
    param_index = {p.name: p for p in spec.params}

    for name, pspec in param_index.items():
        if name not in params:
            if pspec.required:
                raise ValidationError(f"'{op_id}' için zorunlu parametre eksik: {name!r}")
            continue
        raw = params[name]
        if not isinstance(raw, str):
            raise ValidationError(f"Parametre string olmalı: {name!r}")
        validator = _VALIDATORS[pspec.kind]
        validated[name] = validator(raw)  # type: ignore[operator]

    extra = set(params) - set(param_index)
    if extra:
        raise ValidationError(f"'{op_id}' için bilinmeyen parametreler: {sorted(extra)}")

    return validated
