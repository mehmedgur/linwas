"""Aygıt Yöneticisi: PCI ve USB aygıtları, sürücüleri ve durumları (salt okunur, root gerekmez).

- PCI: `lspci -vmmnnk` (ad, sınıf, kimlik, Driver/Module satırları)
- USB: /sys/bus/usb/devices (üretici/ürün adı, kimlik, arayüz sınıfları, bağlı sürücüler)
- Yazıcı/tarayıcı sürücü önerisi: takılı USB aygıtının üretici kimliğine göre paket
  (Debian 12 ve Ubuntu 22.04 depolarındaki paketler).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

USB_DEVICES = Path("/sys/bus/usb/devices")

# Görünen grup kimlikleri (arayüzde çevrilir); sıra gösterim sırasıdır
GROUPS = (
    "display",
    "network",
    "bluetooth",
    "audio",
    "camera",
    "printer",
    "storage",
    "input",
    "usb",
    "system",
    "other",
)

# Sürücüsüz kalması sorun sayılan gruplar (ör. köprü/denetleyici gibi sistem aygıtları sayılmaz)
_IMPORTANT = {"display", "network", "bluetooth", "audio", "camera", "storage"}


@dataclass
class Device:
    name: str
    group: str
    bus: str  # "pci" | "usb"
    ids: str  # "10de:1f95"
    driver: str = ""  # bağlı çekirdek sürücüsü
    module: str = ""  # kullanılabilir modül (bağlı değilse)
    vendor: str = ""

    @property
    def problem(self) -> bool:
        return not self.driver and self.group in _IMPORTANT


def _run(cmd: list[str], timeout: int = 15) -> str:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout


# --- PCI ---


def _pci_group(cls: str) -> str:
    c = cls.lower()
    if any(k in c for k in ("vga", "3d controller", "display")):
        return "display"
    if any(k in c for k in ("network", "ethernet", "wireless")):
        return "network"
    if "audio" in c or "multimedia" in c:
        return "audio"
    if any(k in c for k in ("sata", "raid", "non-volatile", "nvme", "ide", "mass storage", "scsi")):
        return "storage"
    if "usb" in c:
        return "usb"
    system = ("bridge", "smbus", "communication", "signal processing", "memory", "serial bus")
    if any(k in c for k in system):
        return "system"
    return "other"


def _strip_id(text: str) -> tuple[str, str]:
    """ "NVIDIA Corporation [10de]" → ("NVIDIA Corporation", "10de")."""
    m = re.match(r"^(.*?)\s*\[([0-9a-f]{4})\]$", text.strip())
    return (m.group(1), m.group(2)) if m else (text.strip(), "")


def parse_lspci_vmm(out: str) -> list[Device]:
    devices = []
    for block in out.strip().split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fields.setdefault(key.strip(), value.strip())
        if "Slot" not in fields:
            continue
        cls, _ = _strip_id(fields.get("Class", ""))
        vendor, vid = _strip_id(fields.get("Vendor", ""))
        name, did = _strip_id(fields.get("Device", ""))
        devices.append(
            Device(
                name=f"{vendor} {name}".strip(),
                group=_pci_group(cls),
                bus="pci",
                ids=f"{vid}:{did}",
                driver=fields.get("Driver", ""),
                module=fields.get("Module", ""),
                vendor=vid,
            )
        )
    return devices


# --- USB ---


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _usb_group(classes: set[str], name: str) -> str:
    lname = name.lower()
    if "e0" in classes or "bluetooth" in lname:
        return "bluetooth"
    if "0e" in classes or "camera" in lname or "webcam" in lname:
        return "camera"
    # 07 = yazıcı; 06 (Still Imaging) telefon/fotoğraf makinesi de olabilir, yalnızca adında
    # tarayıcı geçiyorsa yazıcı/tarayıcı sayılır
    if "07" in classes or "scanner" in lname or "printer" in lname:
        return "printer"
    if "01" in classes:
        return "audio"
    if "08" in classes:
        return "storage"
    if "03" in classes:
        return "input"
    if "02" in classes or "0a" in classes or "wlan" in lname or "wireless" in lname:
        return "network"
    if "09" in classes:
        return "usb"
    return "other"


@dataclass
class UsbDevice(Device):
    interfaces: list[tuple[str, str, str]] = field(default_factory=list)  # (sınıf, alt, protokol)


def parse_lsusb(out: str) -> dict[str, str]:
    """`lsusb` → {"8087:0033": "Intel Corp. AX211 Bluetooth"} (sysfs'te adı olmayanlar için)."""
    names = {}
    for line in out.splitlines():
        m = re.match(r"^Bus \d+ Device \d+: ID ([0-9a-f]{4}:[0-9a-f]{4})\s*(.*)$", line.strip())
        if m and m.group(2):
            names[m.group(1)] = m.group(2)
    return names


def list_usb(devices_dir: Path = USB_DEVICES) -> list[UsbDevice]:
    result: list[UsbDevice] = []
    if not devices_dir.is_dir():
        return result
    lsusb: dict[str, str] | None = None
    for dev in sorted(devices_dir.iterdir()):
        if ":" in dev.name or dev.name.startswith("usb"):
            continue  # arayüzler ve kök hub'lar
        vid, pid = _read(dev / "idVendor"), _read(dev / "idProduct")
        if not vid:
            continue
        interfaces, drivers = [], []
        for intf in sorted(devices_dir.glob(f"{dev.name}:*")):
            interfaces.append(
                (
                    _read(intf / "bInterfaceClass").lower(),
                    _read(intf / "bInterfaceSubClass").lower(),
                    _read(intf / "bInterfaceProtocol").lower(),
                )
            )
            link = intf / "driver"
            if link.is_symlink():
                drivers.append(os.path.basename(os.readlink(link)))
        name = " ".join(x for x in (_read(dev / "manufacturer"), _read(dev / "product")) if x)
        if not name:
            if lsusb is None:
                lsusb = parse_lsusb(_run(["lsusb"]))
            name = lsusb.get(f"{vid}:{pid}", f"USB {vid}:{pid}")
        classes = {c for c, _, _ in interfaces}
        result.append(
            UsbDevice(
                name=name,
                group=_usb_group(classes, name),
                bus="usb",
                ids=f"{vid}:{pid}",
                driver=", ".join(dict.fromkeys(d for d in drivers if d != "usbfs")),
                vendor=vid,
                interfaces=interfaces,
            )
        )
    return result


def list_devices() -> list[Device]:
    """Bütün aygıtlar: sorunlular önce, sonra gruba ve ada göre."""
    devices: list[Device] = parse_lspci_vmm(_run(["lspci", "-vmmnnk"]))
    devices += list_usb()
    order = {g: i for i, g in enumerate(GROUPS)}
    return sorted(devices, key=lambda d: (not d.problem, order.get(d.group, 99), d.name.lower()))


# --- Yazıcı / tarayıcı sürücü önerisi ---

# USB üretici kimliği → (ad, yazıcı paketi, tarayıcı paketi)
_VENDOR_PACKAGES: dict[str, tuple[str, str, str]] = {
    "03f0": ("HP", "hplip", "hplip"),
    "04b8": ("Epson", "printer-driver-escpr", ""),
    "04f9": ("Brother", "printer-driver-brlaser", ""),
    "04a9": ("Canon", "printer-driver-gutenprint", ""),
    "04e8": ("Samsung", "printer-driver-splix", ""),
}
IPP_USB_PACKAGE = "ipp-usb"  # IPP-over-USB (sürücüsüz) yazıcılar ve tarayıcılar


@dataclass
class PrinterDriverSuggestion:
    device: str
    package: str
    reason: str  # "vendor" | "ipp-usb"


def printer_suggestions(usb: list[UsbDevice]) -> list[PrinterDriverSuggestion]:
    """Takılı yazıcı/tarayıcılar için önerilen paketler (kurulu olup olmadığı ayrıca denetlenir)."""
    result: list[PrinterDriverSuggestion] = []
    for dev in usb:
        printer_if = [i for i in dev.interfaces if i[0] == "07"]
        if not printer_if and dev.group != "printer":
            continue
        # IPP-over-USB: yazıcı arayüzü, alt sınıf 01, protokol 04
        if any(sub == "01" and proto == "04" for _, sub, proto in printer_if):
            result.append(PrinterDriverSuggestion(dev.name, IPP_USB_PACKAGE, "ipp-usb"))
        info = _VENDOR_PACKAGES.get(dev.vendor)
        if info:
            pkg = info[1] if printer_if else (info[2] or info[1])
            if pkg:
                result.append(PrinterDriverSuggestion(dev.name, pkg, "vendor"))
    seen: set[str] = set()
    unique = []
    for s in result:
        if s.package not in seen:
            seen.add(s.package)
            unique.append(s)
    return unique
