# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sürücü ve firmware algılama (salt okunur).

GPU, ağ/Wi-Fi ve firmware güncellemelerini üç kategoride döner.
Hata durumunda boş liste döner — exception asla dışarıya çıkmaz.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DriverCategory(Enum):
    GPU = "gpu"
    NETWORK = "network"
    PRINTER = "printer"
    FIRMWARE = "firmware"


@dataclass
class DriverCandidate:
    package: str
    device_name: str  # okunabilir cihaz adı
    current_driver: str  # etkin kernel modülü; "" = sürücü yok
    category: DriverCategory
    description: str  # kullanıcıya sade açıklama
    driver_type: str  # "proprietary" | "open-source" | "firmware"
    recommended: bool
    installed: bool
    needs_reboot: bool  # True: kurulum sonrası yeniden başlatma gerekir
    # Sürüm seçenekleri (NVIDIA); boşsa yalnızca bu paket önerilir
    options: list = field(default_factory=list)  # list[driver_options.DriverOption]


# --- Yardımcılar ---


def _run(cmd: list[str], timeout: int = 20) -> str:
    # Çıktılar İngilizce ayrıştırılır (Pardus Türkçe çıktı verir: "Kurulu:" vb.)
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def dpkg_installed(pkg: str) -> bool:
    out = _run(["dpkg-query", "-W", "-f=${Status}", pkg], timeout=5)
    return "install ok installed" in out


# --- lspci -k ayrıştırıcı ---


@dataclass
class _PciDevice:
    pci_id: str
    class_name: str  # "VGA compatible controller", "Network controller" vb.
    device_name: str  # tam cihaz adı
    current_driver: str
    modules: list[str] = field(default_factory=list)


def _parse_lspci_k() -> list[_PciDevice]:
    """lspci -k çıktısını ayrıştırır; cihaz bloklarını döner."""
    output = _run(["lspci", "-k"])
    if not output:
        return []

    devices: list[_PciDevice] = []
    current: _PciDevice | None = None

    # Cihaz başlık satırı: "01:00.0 VGA compatible controller: NVIDIA Corp..."
    _HEADER = re.compile(r"^([0-9a-f:.]+)\s+([^:]+):\s+(.+)$", re.IGNORECASE)

    for raw in output.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        if not raw[0].isspace():
            # Yeni cihaz bloğu
            m = _HEADER.match(stripped)
            if m:
                if current:
                    devices.append(current)
                current = _PciDevice(
                    pci_id=m.group(1),
                    class_name=m.group(2).strip(),
                    device_name=m.group(3).strip(),
                    current_driver="",
                )
        elif current:
            if stripped.startswith("Kernel driver in use:"):
                current.current_driver = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Kernel modules:"):
                raw_mods = stripped.split(":", 1)[1]
                current.modules = [m.strip() for m in raw_mods.split(",") if m.strip()]

    if current:
        devices.append(current)
    return devices


# --- GPU algılama ---

_NVIDIA = re.compile(r"nvidia|geforce|quadro|tesla|rtx|gtx", re.IGNORECASE)
_AMD = re.compile(r"\bamd\b|radeon|rx \d+|vega|navi|polaris", re.IGNORECASE)
_INTEL_GPU = re.compile(r"intel.*(graphics|iris|uhd|hd graphics|arc)", re.IGNORECASE)


def _gpu_candidates(dev: _PciDevice) -> list[DriverCandidate]:
    name = dev.device_name
    results: list[DriverCandidate] = []

    if _NVIDIA.search(name):
        # Seçenekler depodan okunur (Ubuntu ve Debian/Pardus'ta paket adları farklı)
        from linwas.backend.driver_options import nvidia_options

        options = nvidia_options()
        installed_pkg = next((o.package for o in options if o.installed and o.package), "")
        best = next((o.package for o in options if o.recommended), "")
        if options and (best or installed_pkg):
            active = dev.current_driver.startswith("nvidia")
            results.append(
                DriverCandidate(
                    package=installed_pkg or best,
                    device_name=name,
                    current_driver=dev.current_driver or "(none)",
                    category=DriverCategory.GPU,
                    description=(
                        "NVIDIA proprietary driver — better performance and CUDA support."
                        if installed_pkg
                        else "NVIDIA proprietary driver — recommended for full performance."
                    ),
                    driver_type="proprietary",
                    recommended=True,
                    installed=bool(installed_pkg),
                    needs_reboot=not active,
                    options=options,
                )
            )
        elif dev.current_driver in ("nvidia", "nvidia_current"):
            # Proprietary zaten etkin
            results.append(
                DriverCandidate(
                    package=installed_pkg or "nvidia-driver-550",
                    device_name=name,
                    current_driver=dev.current_driver,
                    category=DriverCategory.GPU,
                    description="NVIDIA proprietary driver — better performance and CUDA support.",
                    driver_type="proprietary",
                    recommended=True,
                    installed=True,
                    needs_reboot=False,
                )
            )
        elif dev.current_driver in ("nouveau", ""):
            # Açık kaynak sürücü etkin ya da hiç sürücü yok
            target = installed_pkg or "nvidia-driver-550"
            results.append(
                DriverCandidate(
                    package=target,
                    device_name=name,
                    current_driver=dev.current_driver or "(none)",
                    category=DriverCategory.GPU,
                    description="NVIDIA proprietary driver — recommended for full performance.",
                    driver_type="proprietary",
                    recommended=True,
                    installed=bool(installed_pkg),
                    needs_reboot=True,
                )
            )
            # Açık kaynak alternatif (Turing+ GPU için)
            results.append(
                DriverCandidate(
                    package="nvidia-open-kernel-dkms",
                    device_name=name,
                    current_driver=dev.current_driver or "(none)",
                    category=DriverCategory.GPU,
                    description="NVIDIA open-source kernel modules (Turing+ only, experimental).",
                    driver_type="open-source",
                    recommended=False,
                    installed=dpkg_installed("nvidia-open-kernel-dkms"),
                    needs_reboot=True,
                )
            )

    elif _AMD.search(name):
        # amdgpu/radeon çekirdekte hazır gelir; eksik olabilenler firmware ve Mesa bileşenleri
        results += [
            _package_candidate(
                "firmware-amd-graphics",
                name,
                dev.current_driver,
                DriverCategory.GPU,
                "AMD GPU firmware — improves stability and performance.",
                "firmware",
                needs_reboot=True,
            ),
            _package_candidate(
                "mesa-vulkan-drivers",
                name,
                dev.current_driver,
                DriverCategory.GPU,
                "Vulkan graphics for AMD and Intel — needed by most games (and Proton).",
                "open-source",
            ),
            _package_candidate(
                "mesa-va-drivers",
                name,
                dev.current_driver,
                DriverCategory.GPU,
                "AMD video acceleration — smoother video with less CPU use.",
                "open-source",
            ),
        ]

    elif _INTEL_GPU.search(name) or "intel" in name.lower():
        results += [
            _package_candidate(
                "intel-media-va-driver",
                name,
                dev.current_driver,
                DriverCategory.GPU,
                "Intel media driver — hardware video decode/encode acceleration.",
                "open-source",
            ),
            _package_candidate(
                "mesa-vulkan-drivers",
                name,
                dev.current_driver,
                DriverCategory.GPU,
                "Vulkan graphics for AMD and Intel — needed by most games (and Proton).",
                "open-source",
            ),
        ]

    return results


def _package_candidate(
    package: str,
    device: str,
    current: str,
    category: DriverCategory,
    description: str,
    driver_type: str,
    needs_reboot: bool = False,
) -> DriverCandidate:
    installed = dpkg_installed(package)
    return DriverCandidate(
        package=package,
        device_name=device,
        current_driver=current,
        category=category,
        description=description,
        driver_type=driver_type,
        recommended=not installed,
        installed=installed,
        needs_reboot=needs_reboot and not installed,
    )


# --- İşlemci mikrokodu ---


def _cpu_vendor(cpuinfo: Path = Path("/proc/cpuinfo")) -> str:
    try:
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("vendor_id"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def microcode_candidates() -> list[DriverCandidate]:
    """İşlemci üreticisinin güvenlik ve kararlılık düzeltmeleri (açılışta yüklenir)."""
    package = {"GenuineIntel": "intel-microcode", "AuthenticAMD": "amd64-microcode"}.get(
        _cpu_vendor(), ""
    )
    if not package:
        return []
    return [
        _package_candidate(
            package,
            "Processor (CPU)",
            "",
            DriverCategory.FIRMWARE,
            "Processor microcode — security and stability fixes from the CPU maker.",
            "firmware",
            needs_reboot=True,
        )
    ]


def available_in_repo(packages: list[str]) -> set[str]:
    """Depoda kurulabilir (aday sürümü olan) ya da zaten kurulu paketler."""
    from linwas.backend.featured import parse_policy

    if not packages:
        return set()
    policy = parse_policy(_run(["apt-cache", "policy", "--", *packages], timeout=30))
    return {name for name, (installed, candidate) in policy.items() if installed or candidate}


# --- Ağ/Wi-Fi algılama ---

_BROADCOM = re.compile(r"broadcom|bcm4|bcm2", re.IGNORECASE)
_REALTEK_NET = re.compile(r"realtek", re.IGNORECASE)
_INTEL_WIFI = re.compile(r"intel.*(wi.?fi|wireless|ax\d|ac\d|n \d)", re.IGNORECASE)
_MEDIATEK = re.compile(r"mediatek|mt\d{4}", re.IGNORECASE)

_NETWORK_CLASSES = re.compile(r"network controller|ethernet controller|wireless", re.IGNORECASE)


def _network_candidates(dev: _PciDevice) -> list[DriverCandidate]:
    if not _NETWORK_CLASSES.search(dev.class_name):
        return []

    name = dev.device_name
    results: list[DriverCandidate] = []

    if _BROADCOM.search(name):
        # Broadcom: firmware veya STA sürücüsü
        fw_installed = dpkg_installed("firmware-brcm80211")
        sta_installed = dpkg_installed("broadcom-sta-dkms")
        if not fw_installed:
            results.append(
                DriverCandidate(
                    package="firmware-brcm80211",
                    device_name=name,
                    current_driver=dev.current_driver,
                    category=DriverCategory.NETWORK,
                    description="Broadcom Wi-Fi firmware — required for wireless to work.",
                    driver_type="firmware",
                    recommended=True,
                    installed=False,
                    needs_reboot=True,
                )
            )
        if not sta_installed and not fw_installed:
            results.append(
                DriverCandidate(
                    package="broadcom-sta-dkms",
                    device_name=name,
                    current_driver=dev.current_driver,
                    category=DriverCategory.NETWORK,
                    description="Broadcom STA proprietary driver — alternative if firmware fails.",
                    driver_type="proprietary",
                    recommended=False,
                    installed=False,
                    needs_reboot=True,
                )
            )
        if fw_installed or sta_installed:
            pkg = "broadcom-sta-dkms" if sta_installed else "firmware-brcm80211"
            results.append(
                DriverCandidate(
                    package=pkg,
                    device_name=name,
                    current_driver=dev.current_driver,
                    category=DriverCategory.NETWORK,
                    description="Broadcom Wi-Fi driver is installed.",
                    driver_type="firmware" if not sta_installed else "proprietary",
                    recommended=True,
                    installed=True,
                    needs_reboot=False,
                )
            )

    elif _REALTEK_NET.search(name):
        fw_installed = dpkg_installed("firmware-realtek")
        results.append(
            DriverCandidate(
                package="firmware-realtek",
                device_name=name,
                current_driver=dev.current_driver,
                category=DriverCategory.NETWORK,
                description="Realtek network firmware — required for some Realtek cards.",
                driver_type="firmware",
                recommended=not fw_installed,
                installed=fw_installed,
                needs_reboot=not fw_installed,
            )
        )

    elif _INTEL_WIFI.search(name):
        fw_installed = dpkg_installed("firmware-iwlwifi")
        if not fw_installed:
            results.append(
                DriverCandidate(
                    package="firmware-iwlwifi",
                    device_name=name,
                    current_driver=dev.current_driver,
                    category=DriverCategory.NETWORK,
                    description="Intel Wi-Fi firmware — required for some Intel wireless cards.",
                    driver_type="firmware",
                    recommended=True,
                    installed=False,
                    needs_reboot=True,
                )
            )

    elif _MEDIATEK.search(name):
        fw_installed = dpkg_installed("firmware-linux-nonfree")
        results.append(
            DriverCandidate(
                package="firmware-linux-nonfree",
                device_name=name,
                current_driver=dev.current_driver,
                category=DriverCategory.NETWORK,
                description="MediaTek Wi-Fi firmware — required for wireless to work.",
                driver_type="firmware",
                recommended=not fw_installed,
                installed=fw_installed,
                needs_reboot=not fw_installed,
            )
        )

    return results


# --- Yazıcı ve tarayıcı ---


def _printer_candidates() -> list[DriverCandidate]:
    from linwas.backend.devices import list_usb, printer_suggestions

    results = []
    for s in printer_suggestions(list_usb()):
        installed = dpkg_installed(s.package)
        results.append(
            DriverCandidate(
                package=s.package,
                device_name=s.device,
                current_driver="",
                category=DriverCategory.PRINTER,
                description=(
                    "Lets the computer use printers and scanners that work without a driver "
                    "over USB (IPP-over-USB)."
                    if s.reason == "ipp-usb"
                    else "Printer driver for this brand, from your system's software sources."
                ),
                driver_type="open-source",
                recommended=not installed,
                installed=installed,
                needs_reboot=False,
            )
        )
    return results


# --- Firmware güncellemeleri (fwupd) ---


def _fwupd_candidates() -> list[DriverCandidate]:
    """fwupd aracılığıyla güncellenebilir firmware sayısını döner."""
    if not _run(["which", "fwupdmgr"], timeout=3):
        # fwupd kurulu değil — kurulum öner
        return [
            DriverCandidate(
                package="fwupd",
                device_name="Firmware Update Tool",
                current_driver="",
                category=DriverCategory.FIRMWARE,
                description="fwupd — hardware firmware updates (BIOS, SSD, dock, etc.).",
                driver_type="open-source",
                recommended=True,
                installed=False,
                needs_reboot=False,
            )
        ]

    # fwupd var; güncellemeler JSON'dan sayılır (metin çıktısı dile ve sürüme göre değişir)
    from linwas.backend.firmware import list_updates

    count = len(list_updates())
    if count <= 0:
        return []

    return [
        DriverCandidate(
            package="__fwupd_update__",
            device_name=f"{count} device(s)",
            current_driver="",
            category=DriverCategory.FIRMWARE,
            description=(
                f"{count} firmware update(s) available via fwupd (BIOS, SSD, dock firmware, etc.)."
            ),
            driver_type="firmware",
            recommended=True,
            installed=False,
            needs_reboot=True,
        )
    ]


# --- Ana API ---


def list_drivers() -> list[DriverCandidate]:
    """Tüm sürücü adaylarını döner; hata durumunda boş liste."""
    try:
        devices = _parse_lspci_k()
        candidates: list[DriverCandidate] = []

        gpu_classes = re.compile(r"vga|3d controller|display controller", re.IGNORECASE)

        for dev in devices:
            if gpu_classes.search(dev.class_name):
                candidates.extend(_gpu_candidates(dev))
            else:
                candidates.extend(_network_candidates(dev))

        candidates.extend(_printer_candidates())
        candidates.extend(microcode_candidates())

        # Paket adları dağıtıma göre değişir (ör. Ubuntu'da firmware-* yok, linux-firmware
        # içinde gelir): depoda olmayan öneri gösterilmez
        names = sorted({c.package for c in candidates if not c.options})
        available = available_in_repo(names)
        candidates = [c for c in candidates if c.options or c.package in available]
        # Aynı paket birden çok aygıt için önerildiyse (ör. Mesa) bir kez gösterilir
        unique: dict[str, DriverCandidate] = {}
        for c in candidates:
            unique.setdefault(c.package, c)
        candidates = list(unique.values())

        candidates.extend(_fwupd_candidates())

        # Sıralama: önerilen önce, kurulmamış önce
        return sorted(candidates, key=lambda d: (not d.recommended, d.installed, d.package))
    except Exception:
        return []
