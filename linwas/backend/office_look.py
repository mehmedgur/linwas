# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Office görünümü: LibreOffice'i Microsoft Office benzeri yapan `linwas-office-look` paketi.

Paket `packaging/plugins/office-look` altında; LibreOffice'e dokunan her şey oradaki
`linwas-office-look` aracındadır. Linwas yalnız bu aracı çağırır (kabuk yok, kullanıcı
yetkisiyle) ve paketi kuyruk üzerinden kurar/kaldırır (`package.install`/`package.remove`).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

PACKAGE = "linwas-office-look"
TOOL = "linwas-office-look"
LIBREOFFICE_PACKAGES = ("libreoffice-writer", "libreoffice-calc", "libreoffice-impress")

# Aracın çıkış kodları (packaging/plugins/office-look/tools/cli.py)
EXIT_LO_RUNNING = 3

RIBBONS = ("simple", "full", "classic")
AUTOSAVE_CHOICES = (0, 1, 2, 5, 10)
SAVE_FORMATS = ("ooxml", "odf")
FONTS = ("carlito", "liberation")


@dataclass
class Settings:
    ribbon: str = "simple"
    file_menu: bool = True
    autosave_minutes: int = 2
    save_format: str = "ooxml"
    font: str = "carlito"
    office_names: bool = True  # menüde ve başlıkta "LibreOffice Writer (Word)"


@dataclass
class OfficeLookStatus:
    package_version: str | None = None
    libreoffice_version: str | None = None
    libreoffice_running: bool = False
    disabled: bool = False
    simple_ribbon_apps: list[str] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)

    @property
    def installed(self) -> bool:
        return self.package_version is not None

    @property
    def libreoffice_installed(self) -> bool:
        return self.libreoffice_version is not None


@dataclass
class Result:
    ok: bool
    libreoffice_running: bool = False
    message: str = ""


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            [TOOL, *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _dpkg_version(package: str) -> str | None:
    try:
        r = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}|${Version}", package],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    status, _, version = r.stdout.partition("|")
    return version if "install ok installed" in status else None


def short_version(version: str | None) -> str:
    """Debian sürümünden kullanıcıya gösterilen kısım: "4:7.4.7-1+deb12u14" -> "7.4.7"."""
    if not version:
        return ""
    return version.split(":", 1)[-1].split("-", 1)[0].split("~", 1)[0]


def parse_status(text: str) -> OfficeLookStatus:
    """`linwas-office-look status --json` çıktısını çözer; tanınmayan değerler varsayılana döner."""
    data = json.loads(text)
    raw = data.get("settings") or {}
    defaults = Settings()
    ribbon = raw.get("ribbon")
    settings = Settings(
        # "default": kullanıcı seçmemiş, paketin varsayılanı (sade şerit) geçerli
        ribbon=ribbon if ribbon in RIBBONS else defaults.ribbon,
        file_menu=raw.get("file_menu") if isinstance(raw.get("file_menu"), bool) else True,
        office_names=raw.get("office_names") if isinstance(raw.get("office_names"), bool) else True,
        autosave_minutes=raw.get("autosave_minutes")
        if raw.get("autosave_minutes") in AUTOSAVE_CHOICES
        else defaults.autosave_minutes,
        save_format=raw.get("save_format")
        if raw.get("save_format") in SAVE_FORMATS
        else defaults.save_format,
        font=raw.get("font") if raw.get("font") in FONTS else defaults.font,
    )
    apps = data.get("simple_ribbon_apps")
    return OfficeLookStatus(
        package_version=data.get("package_version") or None,
        libreoffice_version=data.get("libreoffice_version") or None,
        libreoffice_running=bool(data.get("libreoffice_running")),
        disabled=bool(data.get("disabled")),
        simple_ribbon_apps=[a for a in apps if isinstance(a, str)]
        if isinstance(apps, list)
        else [],
        settings=settings,
    )


def status() -> OfficeLookStatus:
    """Durum; paket kurulu değilse yalnız LibreOffice sürümü doldurulur."""
    r = _run(["status", "--json"], timeout=20)
    if r is not None and r.returncode == 0:
        try:
            return parse_status(r.stdout)
        except (ValueError, AttributeError):
            pass
    return OfficeLookStatus(libreoffice_version=_dpkg_version("libreoffice-core"))


def _result(r: subprocess.CompletedProcess | None) -> Result:
    if r is None:
        return Result(False, message="linwas-office-look not found")
    if r.returncode == EXIT_LO_RUNNING:
        return Result(False, libreoffice_running=True)
    return Result(r.returncode == 0, message=r.stderr.strip())


def set_option(key: str, value: str) -> Result:
    """key: ribbon, file_menu (on/off), autosave (dakika), save_format, font."""
    return _result(_run(["set", key, value]))


def apply_settings(old: Settings, new: Settings) -> Result:
    """Yalnız değişen ayarları yazar; LibreOffice açıksa ilk profil ayarında durur."""
    changes: list[tuple[str, str]] = []
    # LibreOffice açıkken de yazılabilir; önce gelsin
    if new.office_names != old.office_names:
        changes.append(("office_names", "on" if new.office_names else "off"))
    if new.file_menu != old.file_menu:
        changes.append(("file_menu", "on" if new.file_menu else "off"))
    if new.autosave_minutes != old.autosave_minutes:
        changes.append(("autosave", str(new.autosave_minutes)))
    if new.ribbon != old.ribbon:
        changes.append(("ribbon", new.ribbon))
    if new.save_format != old.save_format:
        changes.append(("save_format", new.save_format))
    if new.font != old.font:
        changes.append(("font", new.font))
    for key, value in changes:
        result = set_option(key, value)
        if not result.ok:
            return result
    return Result(True)


def disable_for_me() -> Result:
    return _result(_run(["disable"]))


def enable_for_me() -> Result:
    return _result(_run(["enable"]))


def install_steps(current: OfficeLookStatus) -> list[tuple[str, dict[str, str]]]:
    """Kurulum adımları (op_id, params). Paket LibreOffice'e bağımlıdır; LibreOffice yoksa
    adımlar açıkça yazılır ki onay penceresi ne kurulacağını göstersin."""
    steps: list[tuple[str, dict[str, str]]] = []
    if not current.libreoffice_installed:
        steps += [("package.install", {"name": p}) for p in LIBREOFFICE_PACKAGES]
    steps.append(("package.install", {"name": PACKAGE}))
    return steps
