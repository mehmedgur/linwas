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
    # Flatpak uygulama kimliği (ör. org.videolan.VLC)
    FLATPAK_ID = "flatpak_id"
    # Snap adı (ör. firefox)
    SNAP_NAME = "snap_name"
    # Kapak kapanınca davranışı (logind HandleLidSwitch=)
    LID_ACTION = "lid_action"
    # Pil adı (/sys/class/power_supply altında, ör. BAT0)
    BATTERY_NAME = "battery_name"
    # Pil şarj sınırı yüzdesi
    CHARGE_LIMIT = "charge_limit"
    # Geri alma kaydı kimliği (uuid4)
    RECORD_ID = "record_id"
    # "true" | "false"
    BOOL = "bool"
    # Otomatik güncelleme duraklatma: "-1" (değiştirme), "0" (devam), "1"–"5" hafta
    PAUSE_WEEKS = "pause_weeks"
    # Saat (SS:DD, 24 saat), ör. yeniden başlatma zamanı
    CLOCK_TIME = "clock_time"
    # Secure Boot MOK kaydı için 8 haneli tek kullanımlık şifre
    MOK_PASSWORD = "mok_password"
    # fwupd aygıt kimliği (40 karakter onaltılık)
    FWUPD_DEVICE_ID = "fwupd_device_id"
    # Backports kod adı (ör. bookworm-backports)
    BACKPORTS_SUITE = "backports_suite"
    # Ubuntu nvidia-prime kipi (prime-select): nvidia | on-demand | intel
    PRIME_MODE = "prime_mode"


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

# Flatpak kimliği: en az üç noktalı bileşen; harfle başlar (tire ile başlayamaz)
_RE_FLATPAK_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*(\.[A-Za-z0-9_\-]+){2,}$")

# Snap adı: küçük harf, rakam, tek tire; harf/rakamla başlar ve biter, en fazla 40 karakter
_RE_SNAP_NAME = re.compile(r"^[a-z0-9](?:-?[a-z0-9])*$")

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


def _validate_flatpak_id(value: str) -> str:
    if len(value) > 255 or not _RE_FLATPAK_ID.match(value):
        raise ValidationError(f"Geçersiz Flatpak kimliği: {value!r}")
    return value


def _validate_snap_name(value: str) -> str:
    if len(value) > 40 or not _RE_SNAP_NAME.match(value):
        raise ValidationError(f"Geçersiz snap adı: {value!r}")
    return value


# Linwas'ın sunduğu kapak davranışları (backend.power.LID_ACTIONS ile aynı)
_LID_ACTIONS = ("suspend", "lock", "ignore", "poweroff")
_RE_BATTERY = re.compile(r"^BAT[0-9A-Za-z_]{0,8}$")
_CHARGE_LIMITS = ("60", "80", "100")


def _validate_lid_action(value: str) -> str:
    if value not in _LID_ACTIONS:
        raise ValidationError(f"Geçersiz kapak davranışı: {value!r}")
    return value


_PRIME_MODES = ("nvidia", "on-demand", "intel")


def _validate_prime_mode(value: str) -> str:
    if value not in _PRIME_MODES:
        raise ValidationError(f"Geçersiz grafik kipi: {value!r}")
    return value


def _validate_battery_name(value: str) -> str:
    if not _RE_BATTERY.match(value):
        raise ValidationError(f"Geçersiz pil adı: {value!r}")
    return value


def _validate_charge_limit(value: str) -> str:
    if value not in _CHARGE_LIMITS:
        raise ValidationError(f"Geçersiz şarj sınırı: {value!r}")
    return value


def _validate_bool(value: str) -> str:
    if value not in ("true", "false"):
        raise ValidationError(f"Geçersiz doğru/yanlış değeri: {value!r}")
    return value


def _validate_pause_weeks(value: str) -> str:
    if value not in ("-1", "0", "1", "2", "3", "4", "5"):
        raise ValidationError(f"Geçersiz duraklatma süresi: {value!r}")
    return value


_RE_CLOCK = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def _validate_clock_time(value: str) -> str:
    if not _RE_CLOCK.match(value):
        raise ValidationError(f"Geçersiz saat: {value!r}")
    return value


_RE_MOK_PASSWORD = re.compile(r"^[0-9]{8}$")


def _validate_mok_password(value: str) -> str:
    if not _RE_MOK_PASSWORD.match(value):
        raise ValidationError("Geçersiz MOK şifresi (8 rakam olmalı)")
    return value


_RE_FWUPD_ID = re.compile(r"^[0-9a-f]{40}$")
_RE_BACKPORTS = re.compile(r"^[a-z]+-backports$")


def _validate_fwupd_device_id(value: str) -> str:
    if not _RE_FWUPD_ID.match(value):
        raise ValidationError(f"Geçersiz fwupd aygıt kimliği: {value!r}")
    return value


def _validate_backports_suite(value: str) -> str:
    if not _RE_BACKPORTS.match(value):
        raise ValidationError(f"Geçersiz backports adı: {value!r}")
    return value


_RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _validate_record_id(value: str) -> str:
    if not _RE_UUID.match(value):
        raise ValidationError(f"Geçersiz kayıt kimliği: {value!r}")
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
    ParamKind.FLATPAK_ID: _validate_flatpak_id,
    ParamKind.SNAP_NAME: _validate_snap_name,
    ParamKind.LID_ACTION: _validate_lid_action,
    ParamKind.PRIME_MODE: _validate_prime_mode,
    ParamKind.BATTERY_NAME: _validate_battery_name,
    ParamKind.CHARGE_LIMIT: _validate_charge_limit,
    ParamKind.RECORD_ID: _validate_record_id,
    ParamKind.BOOL: _validate_bool,
    ParamKind.PAUSE_WEEKS: _validate_pause_weeks,
    ParamKind.CLOCK_TIME: _validate_clock_time,
    ParamKind.MOK_PASSWORD: _validate_mok_password,
    ParamKind.FWUPD_DEVICE_ID: _validate_fwupd_device_id,
    ParamKind.BACKPORTS_SUITE: _validate_backports_suite,
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
    # Program kaldırma: bağımlı paketler ve artık gerekmeyen bağımlılıklar da kaldırılır.
    # Helper çalıştırmadan önce planı yeniden hesaplar ve kritik paketleri engeller.
    "app.remove_apt": _op(
        ("name", ParamKind.PACKAGE_NAME),
        risk=RiskLevel.MEDIUM,
        label="Remove program",
    ),
    "app.remove_apt_purge": _op(
        ("name", ParamKind.PACKAGE_NAME),
        risk=RiskLevel.MEDIUM,
        label="Remove program and its settings",
    ),
    "app.remove_flatpak": _op(
        ("app_id", ParamKind.FLATPAK_ID),
        risk=RiskLevel.MEDIUM,
        label="Remove program",
    ),
    "app.remove_flatpak_data": _op(
        ("app_id", ParamKind.FLATPAK_ID),
        risk=RiskLevel.MEDIUM,
        label="Remove program and its settings",
    ),
    "app.remove_snap": _op(
        ("name", ParamKind.SNAP_NAME),
        risk=RiskLevel.MEDIUM,
        label="Remove program",
    ),
    "app.remove_snap_purge": _op(
        ("name", ParamKind.SNAP_NAME),
        risk=RiskLevel.MEDIUM,
        label="Remove program and its settings",
    ),
    # Tek programı güncelleme
    "package.upgrade_one": _op(
        ("name", ParamKind.PACKAGE_NAME),
        risk=RiskLevel.LOW,
        label="Update program",
    ),
    "flatpak.update": _op(
        ("app_id", ParamKind.FLATPAK_ID),
        risk=RiskLevel.LOW,
        label="Update program",
    ),
    "snap.refresh": _op(
        ("name", ParamKind.SNAP_NAME),
        risk=RiskLevel.LOW,
        label="Update program",
    ),
    # Geri alma ve Flatpak kurulumu
    "flatpak.update_all": OperationSpec(
        params=[], risk=RiskLevel.LOW, label="Update all Flatpak apps"
    ),
    "snap.refresh_all": OperationSpec(params=[], risk=RiskLevel.LOW, label="Update all snaps"),
    "flatpak.install": _op(
        ("app_id", ParamKind.FLATPAK_ID),
        risk=RiskLevel.LOW,
        label="Install program (Flatpak)",
    ),
    "snap.install": _op(
        ("name", ParamKind.SNAP_NAME),
        risk=RiskLevel.LOW,
        label="Install program (Snap)",
    ),
    "snap.install_classic": _op(
        ("name", ParamKind.SNAP_NAME),
        risk=RiskLevel.MEDIUM,
        label="Install program (Snap, classic)",
    ),
    # Güç ve pil
    "power.set_lid_action": _op(
        ("action", ParamKind.LID_ACTION),
        risk=RiskLevel.LOW,
        label="Change what happens when the lid is closed",
    ),
    "battery.set_charge_limit": _op(
        ("battery", ParamKind.BATTERY_NAME),
        ("percent", ParamKind.CHARGE_LIMIT),
        risk=RiskLevel.LOW,
        label="Set battery charge limit",
    ),
    "rollback.restore_files": _op(
        ("record_id", ParamKind.RECORD_ID),
        risk=RiskLevel.MEDIUM,
        label="Restore files to how they were before",
    ),
    "autoupdate.configure": _op(
        ("enabled", ParamKind.BOOL),
        ("snapshot", ParamKind.BOOL),
        ("pause_weeks", ParamKind.PAUSE_WEEKS),
        risk=RiskLevel.LOW,
        label="Change automatic update settings",
    ),
    "power.schedule_reboot": _op(
        ("time", ParamKind.CLOCK_TIME),
        risk=RiskLevel.LOW,
        label="Schedule a restart",
    ),
    "power.cancel_reboot": OperationSpec(
        params=[], risk=RiskLevel.LOW, label="Cancel the scheduled restart"
    ),
    "driver.remove_nvidia": OperationSpec(
        params=[],
        risk=RiskLevel.HIGH,
        label="Remove the NVIDIA driver (use the open-source driver)",
    ),
    "prime.select": _op(
        ("mode", ParamKind.PRIME_MODE),
        risk=RiskLevel.MEDIUM,
        label="Change the hybrid graphics mode (prime-select)",
    ),
    "driver.rebuild_modules": OperationSpec(
        params=[],
        risk=RiskLevel.MEDIUM,
        label="Rebuild driver modules for the running kernel (DKMS)",
    ),
    "secureboot.enroll_mok": _op(
        ("password", ParamKind.MOK_PASSWORD),
        risk=RiskLevel.MEDIUM,
        label="Register the driver signing key for Secure Boot",
    ),
    "firmware.refresh": OperationSpec(
        params=[], risk=RiskLevel.LOW, label="Download the latest firmware information"
    ),
    "firmware.update_device": _op(
        ("device_id", ParamKind.FWUPD_DEVICE_ID),
        risk=RiskLevel.HIGH,
        label="Update device firmware",
    ),
    "kernel.install_backports": _op(
        ("suite", ParamKind.BACKPORTS_SUITE),
        risk=RiskLevel.HIGH,
        label="Install a newer kernel (backports)",
    ),
    "flatpak.setup": OperationSpec(
        params=[],
        risk=RiskLevel.MEDIUM,
        label="Install Flatpak and add Flathub",
    ),
    "wine.setup": OperationSpec(
        params=[],
        risk=RiskLevel.MEDIUM,
        label="Install Wine (with 32-bit support)",
    ),
    "fonts.install_microsoft": OperationSpec(
        params=[],
        risk=RiskLevel.MEDIUM,
        label="Install Microsoft core fonts (licence accepted)",
    ),
    "package.update_all": OperationSpec(
        params=[],
        risk=RiskLevel.LOW,
        label="Update all packages",
    ),
    # Yarım kalmış kurulumları tamamla ve kırık bağımlılıkları onar
    "package.fix_broken": OperationSpec(
        params=[],
        risk=RiskLevel.MEDIUM,
        label="Repair interrupted installations",
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
