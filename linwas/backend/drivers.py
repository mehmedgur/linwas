"""Sürücü ve firmware algılama (salt okunur).

GPU, ağ/Wi-Fi ve firmware güncellemelerini üç kategoride döner.
Hata durumunda boş liste döner — exception asla dışarıya çıkmaz.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum


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
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _dpkg_installed(pkg: str) -> bool:
    out = _run(["dpkg-query", "-W", "-f=${Status}", pkg], timeout=5)
    return "install ok installed" in out


def _dpkg_installed_any(*pkgs: str) -> tuple[str, bool]:
    """İlk kurulu paketi döner; yoksa ilk paketi False ile döner."""
    for p in pkgs:
        if _dpkg_installed(p):
            return p, True
    return pkgs[0], False


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
                    installed=_dpkg_installed("nvidia-open-kernel-dkms"),
                    needs_reboot=True,
                )
            )

    elif _AMD.search(name):
        pkg, inst = _dpkg_installed_any("firmware-amd-graphics", "amd64-microcode")
        results.append(
            DriverCandidate(
                package="firmware-amd-graphics",
                device_name=name,
                current_driver=dev.current_driver,
                category=DriverCategory.GPU,
                description="AMD GPU firmware — improves stability and performance.",
                driver_type="firmware",
                recommended=not _dpkg_installed("firmware-amd-graphics"),
                installed=_dpkg_installed("firmware-amd-graphics"),
                needs_reboot=True,
            )
        )

    elif _INTEL_GPU.search(name):
        # Intel GPU genelde kutudan çalışır; bilgi kartı göster
        results.append(
            DriverCandidate(
                package="intel-media-va-driver",
                device_name=name,
                current_driver=dev.current_driver,
                category=DriverCategory.GPU,
                description="Intel media driver — hardware video decode/encode acceleration.",
                driver_type="open-source",
                recommended=not _dpkg_installed("intel-media-va-driver"),
                installed=_dpkg_installed("intel-media-va-driver"),
                needs_reboot=False,
            )
        )

    return results


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
        fw_installed = _dpkg_installed("firmware-brcm80211")
        sta_installed = _dpkg_installed("broadcom-sta-dkms")
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
        fw_installed = _dpkg_installed("firmware-realtek")
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
        fw_installed = _dpkg_installed("firmware-iwlwifi")
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
        fw_installed = _dpkg_installed("firmware-linux-nonfree")
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
        installed = _dpkg_installed(s.package)
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

    # fwupd var; güncellemeleri sorgula
    output = _run(["fwupdmgr", "get-updates", "--no-unreported-check"], timeout=30)
    if not output:
        return []

    # Güncelleme bulunamadıysa boş liste
    if "No updates available" in output or "nothing to update" in output.lower():
        return []

    # Kaç cihaz güncellenebilir?
    count = output.count("• ")
    if count == 0:
        count = output.count("\n  ") // 3  # kaba tahmin
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
        candidates.extend(_fwupd_candidates())

        # Sıralama: önerilen önce, kurulmamış önce
        return sorted(candidates, key=lambda d: (not d.recommended, d.installed, d.package))
    except Exception:
        return []
