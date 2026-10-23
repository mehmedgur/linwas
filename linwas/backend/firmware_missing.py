"""Eksik firmware tespiti (salt okunur, root gerekmez; sağlık kontrolüyle elle çalışır).

İki kaynak:
1. Çekirdek günlüğü (`journalctl -k -b`): "Direct firmware load for <dosya> failed" ve
   "firmware: failed to load <dosya>" satırları. Normal kullanıcı çoğu sistemde günlüğü
   okuyamaz (Debian/Pardus `dmesg_restrict=1`, journal yalnızca adm/systemd-journal grubu);
   okunamazsa bu kaynak atlanır.
2. Sürücüsü başlamamış aygıt: modülü var ama bağlı sürücüsü yok ve modülün istediği
   firmware dosyalarının (`modinfo -F firmware`) hiçbiri /lib/firmware'de yok.

Dosya → paket eşlemesi dizin/ön ekten yapılır; öneri yalnızca depoda gerçekten bulunan
paketten verilir (Debian 12/Pardus 23 `firmware-*`, Ubuntu hepsi `linux-firmware`).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from linwas.backend.devices import Device

FIRMWARE_DIRS = (Path("/lib/firmware"), Path("/usr/lib/firmware"))
_COMPRESSED = ("", ".xz", ".zst")
_IMPORTANT = {"display", "network", "bluetooth", "audio", "camera"}

# Firmware dosya yolu ön eki → olası paketler (sırayla; ilk depoda bulunan seçilir)
_PREFIX_PACKAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("iwlwifi-", ("firmware-iwlwifi",)),
    ("intel/ibt", ("firmware-iwlwifi",)),
    ("intel/sof", ("firmware-sof-signed",)),
    ("intel/avs", ("firmware-intel-sound",)),
    ("intel/", ("firmware-misc-nonfree",)),
    ("i915/", ("firmware-misc-nonfree",)),
    ("rtl_nic/", ("firmware-realtek",)),
    ("rtl_bt/", ("firmware-realtek",)),
    ("rtlwifi/", ("firmware-realtek",)),
    ("rtw88/", ("firmware-realtek",)),
    ("rtw89/", ("firmware-realtek",)),
    ("ath", ("firmware-atheros",)),
    ("qca/", ("firmware-atheros",)),
    ("brcm/", ("firmware-brcm80211",)),
    ("mediatek/", ("firmware-mediatek", "firmware-misc-nonfree")),
    ("mt7", ("firmware-mediatek", "firmware-misc-nonfree")),
    ("amdgpu/", ("firmware-amd-graphics",)),
    ("radeon/", ("firmware-amd-graphics",)),
    ("nvidia/", ("firmware-misc-nonfree",)),
    ("libertas/", ("firmware-libertas",)),
    ("ti-connectivity/", ("firmware-ti-connectivity",)),
)
_FALLBACK = ("linux-firmware", "firmware-misc-nonfree")

_LOG_PATTERNS = (
    re.compile(r"^(?P<drv>\S+) \S+: Direct firmware load for (?P<file>\S+) failed"),
    re.compile(r"^(?P<drv>\S+) \S+: firmware: failed to load (?P<file>\S+)"),
)


@dataclass
class MissingFirmware:
    driver: str  # çekirdek modülü/sürücüsü (ör. iwlwifi)
    files: list[str] = field(default_factory=list)
    package: str = ""  # önerilen paket; "" = depoda bulunamadı
    installed: bool = False  # paket kurulu ama dosya yine yok/yüklenmemiş (yeniden başlatma)


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for d in ("/usr/sbin", "/sbin"):
        path = os.path.join(d, name)
        if os.access(path, os.X_OK):
            return path
    return ""


def parse_kernel_log(out: str) -> dict[str, set[str]]:
    """Günlük satırları → {sürücü: {dosya}}."""
    found: dict[str, set[str]] = {}
    for line in out.splitlines():
        for pat in _LOG_PATTERNS:
            m = pat.search(line.strip())
            if m:
                found.setdefault(m.group("drv"), set()).add(m.group("file"))
                break
    return found


def firmware_exists(name: str, dirs: tuple[Path, ...] = FIRMWARE_DIRS) -> bool:
    return any((d / f"{name}{ext}").exists() for d in dirs for ext in _COMPRESSED)


def packages_for(file: str) -> tuple[str, ...]:
    for prefix, pkgs in _PREFIX_PACKAGES:
        if file.startswith(prefix):
            return pkgs + ("linux-firmware",)
    return _FALLBACK


def _available(pkg: str) -> bool:
    code, out = _run(["apt-cache", "policy", pkg])
    m = re.search(r"Candidate:\s*(\S+)", out)
    return bool(m and m.group(1) != "(none)")


def _installed(pkg: str) -> bool:
    code, out = _run(["dpkg-query", "-W", "-f=${Status}", pkg], timeout=5)
    return "install ok installed" in out


def _from_log() -> dict[str, set[str]]:
    journalctl = _tool("journalctl")
    if not journalctl:
        return {}
    code, out = _run([journalctl, "-k", "-b", "--no-pager", "-q", "-o", "cat"], timeout=30)
    return parse_kernel_log(out) if code == 0 else {}


def _from_unbound(devices: list[Device]) -> dict[str, set[str]]:
    modinfo = _tool("modinfo")
    if not modinfo:
        return {}
    found: dict[str, set[str]] = {}
    for dev in devices:
        if dev.driver or not dev.module or dev.group not in _IMPORTANT:
            continue
        for module in dev.module.split():
            code, out = _run([modinfo, "-F", "firmware", module])
            wanted = [f for f in out.split() if f]
            if wanted and not any(firmware_exists(f) for f in wanted):
                found.setdefault(module, set()).update(wanted[:3])
    return found


def find_missing(devices: list[Device]) -> list[MissingFirmware]:
    """Eksik firmware'ler; aynı sürücü için tek kayıt."""
    # Çalışan sürücüler günlükte de "yüklenemedi" yazabilir (ör. iwlwifi önce en yeni
    # sürümü dener, bulamazsa eskisini yükler); aygıtı çalışan sürücü eksik sayılmaz.
    bound = {d.driver.replace("-", "_") for d in devices if d.driver}
    raw = {drv: files for drv, files in _from_log().items() if drv.replace("-", "_") not in bound}
    for drv, files in _from_unbound(devices).items():
        raw.setdefault(drv, set()).update(files)

    result: list[MissingFirmware] = []
    for drv, files in sorted(raw.items()):
        # Günlükte geçip sonradan kurulmuş dosyalar eksik sayılmaz (yeniden başlatma yeter)
        missing = sorted(f for f in files if not firmware_exists(f))
        loaded_later = not missing
        names = missing or sorted(files)
        pkg = ""
        for candidate in packages_for(names[0]):
            if _available(candidate):
                pkg = candidate
                break
        result.append(
            MissingFirmware(
                driver=drv,
                files=names,
                package=pkg,
                installed=loaded_later or bool(pkg and _installed(pkg)),
            )
        )
    return result
