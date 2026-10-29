# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Donanım özeti, yazıcılar ve tarayıcılar (salt okunur, root gerekmez).

- İşlemci: `lscpu`; bellek: /proc/meminfo; ekran kartı: `lspci -mm`; diskler: `lsblk`
- Kurulu yazıcılar: `lpstat -p -d` (CUPS)
- Takılı ama kurulmamış USB yazıcılar: USB arayüz sınıfı 07 (Printer)
- Tarayıcılar: `scanimage -L` (SANE)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

USB_DEVICES = Path("/sys/bus/usb/devices")
MEMINFO = Path("/proc/meminfo")

# Sorun giderme için önerilen paketler (Debian/Ubuntu depolarında doğrulandı)
PRINTER_DRIVER_PACKAGE = "printer-driver-all"
SCANNER_PACKAGES = ("sane-utils", "sane-airscan", "ipp-usb")


def _run(cmd: list[str], timeout: int = 15) -> str:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


# --- Donanım özeti ---


@dataclass
class Disk:
    name: str
    size: str
    model: str
    ssd: bool


@dataclass
class HardwareSummary:
    cpu: str = ""
    cpu_cores: int = 0
    memory_bytes: int = 0
    gpus: list[str] = field(default_factory=list)
    disks: list[Disk] = field(default_factory=list)


def parse_lscpu(output: str) -> tuple[str, int]:
    """(model adı, mantıksal işlemci sayısı)."""
    model, cores = "", 0
    for line in output.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "Model name" and not model:
            model = value.strip()
        elif key.strip() == "CPU(s)" and value.strip().isdigit():
            cores = int(value.strip())
    return model, cores


def parse_meminfo(text: str) -> int:
    m = re.search(r"^MemTotal:\s+(\d+)\s+kB", text, re.MULTILINE)
    return int(m.group(1)) * 1024 if m else 0


def parse_lspci_gpus(output: str) -> list[str]:
    """`lspci -mm` satırlarından ekran kartlarını döner (VGA / 3D / Display)."""
    gpus: list[str] = []
    for line in output.splitlines():
        parts = re.findall(r'"([^"]*)"', line)
        if len(parts) >= 3 and re.search(r"VGA|3D|Display", parts[0]):
            gpus.append(f"{parts[1]} {parts[2]}".strip())
    return gpus


def parse_lsblk_disks(output: str) -> list[Disk]:
    """`lsblk -J -d -o NAME,SIZE,MODEL,ROTA,TYPE` → fiziksel diskler."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    disks: list[Disk] = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk" or str(dev.get("name", "")).startswith(("loop", "zram")):
            continue
        disks.append(
            Disk(
                name=dev.get("name", ""),
                size=dev.get("size") or "",
                model=(dev.get("model") or "").strip(),
                ssd=dev.get("rota") in (False, "0", 0),
            )
        )
    return disks


def hardware_summary() -> HardwareSummary:
    cpu, cores = parse_lscpu(_run(["lscpu"]))
    try:
        memory = parse_meminfo(MEMINFO.read_text(encoding="utf-8"))
    except OSError:
        memory = 0
    return HardwareSummary(
        cpu=cpu,
        cpu_cores=cores,
        memory_bytes=memory,
        gpus=parse_lspci_gpus(_run(["lspci", "-mm"])),
        disks=parse_lsblk_disks(_run(["lsblk", "-J", "-d", "-o", "NAME,SIZE,MODEL,ROTA,TYPE"])),
    )


# --- Yazıcılar ---


@dataclass
class Printer:
    name: str
    enabled: bool
    is_default: bool = False


def parse_lpstat(output: str) -> list[Printer]:
    """`lpstat -p -d` (LANG=C) çıktısı.

    "printer NAME is idle.  enabled since ..." / "printer NAME disabled since ..."
    "system default destination: NAME"
    """
    printers: list[Printer] = []
    default = ""
    for line in output.splitlines():
        m = re.match(r"^printer (\S+) (.*)$", line)
        if m:
            printers.append(Printer(name=m.group(1), enabled="disabled" not in m.group(2)))
            continue
        m = re.match(r"^system default destination: (\S+)", line)
        if m:
            default = m.group(1)
    for p in printers:
        p.is_default = p.name == default
    return printers


def list_printers() -> list[Printer]:
    return parse_lpstat(_run(["lpstat", "-p", "-d"]))


# --- Yazıcı ayrıntıları (kullanıcı yetkisiyle; CUPS komutları) ---

# CUPS test sayfası (Debian 12 / Ubuntu 22.04 cups paketinde; kullanıcı makinesinde doğrulandı)
TEST_PAGES = (
    Path("/usr/share/cups/data/default-testpage.pdf"),
    Path("/usr/share/cups/data/testprint"),
)


@dataclass
class Supply:
    name: str
    level: int  # 0–100
    color: str = ""


@dataclass
class PrinterDetails:
    name: str
    model: str = ""
    location: str = ""
    connection: str = ""  # usb | network | other
    uri: str = ""
    supplies: list[Supply] = field(default_factory=list)
    jobs: int = 0


def parse_lpstat_v(output: str) -> dict[str, str]:
    """`lpstat -v`: "device for NAME: URI" → {ad: uri}."""
    uris = {}
    for line in output.splitlines():
        m = re.match(r"^device for ([^:]+): (\S+)", line.strip())
        if m:
            uris[m.group(1)] = m.group(2)
    return uris


def connection_kind(uri: str) -> str:
    scheme = uri.split(":", 1)[0].lower()
    if scheme in ("usb", "hp", "ippusb"):
        return "usb"
    if scheme in ("ipp", "ipps", "http", "https", "socket", "lpd", "dnssd", "implicitclass", "smb"):
        return "network"
    return "other"


def parse_lpoptions(output: str) -> dict[str, str]:
    """`lpoptions -p NAME`: boşlukla ayrılmış anahtar=değer (tırnaklı/kaçışlı değerler)."""
    import shlex

    try:
        parts = shlex.split(output)
    except ValueError:
        return {}
    return dict(p.split("=", 1) for p in parts if "=" in p)


def parse_supplies(options: dict[str, str]) -> list[Supply]:
    names = options.get("marker-names", "")
    levels = options.get("marker-levels", "")
    colors = options.get("marker-colors", "")
    if not names or not levels:
        return []
    name_list = [n.strip() for n in names.split(",")]
    level_list = levels.split(",")
    color_list = colors.split(",") if colors else []
    supplies = []
    for i, name in enumerate(name_list):
        try:
            level = int(level_list[i])
        except (IndexError, ValueError):
            continue
        if level < 0:  # bilinmiyor
            continue
        color = color_list[i].strip() if i < len(color_list) else ""
        supplies.append(Supply(name=name, level=min(level, 100), color=color))
    return supplies


def printer_details(printers: list[Printer]) -> list[PrinterDetails]:
    uris = parse_lpstat_v(_run(["lpstat", "-v"]))
    result = []
    for p in printers:
        opts = parse_lpoptions(_run(["lpoptions", "-p", p.name]))
        jobs = [ln for ln in _run(["lpstat", "-o", p.name]).splitlines() if ln.strip()]
        uri = uris.get(p.name, "")
        result.append(
            PrinterDetails(
                name=p.name,
                model=opts.get("printer-make-and-model", ""),
                location=opts.get("printer-location", ""),
                connection=connection_kind(uri) if uri else "",
                uri=uri,
                supplies=parse_supplies(opts),
                jobs=len(jobs),
            )
        )
    return result


def print_test_page(name: str) -> bool:
    page = next((p for p in TEST_PAGES if p.is_file()), None)
    if page is None:
        return False
    try:
        r = subprocess.run(
            ["lp", "-d", name, "-t", "Linwas test", "--", str(page)],
            capture_output=True,
            timeout=30,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def set_default_printer(name: str) -> bool:
    """Kullanıcının varsayılan yazıcısı (~/.cups/lpoptions; root gerekmez)."""
    try:
        r = subprocess.run(["lpoptions", "-d", name], capture_output=True, timeout=15, shell=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def list_jobs(name: str) -> list[str]:
    return [ln.strip() for ln in _run(["lpstat", "-o", name]).splitlines() if ln.strip()]


def cancel_jobs(name: str) -> bool:
    """Kullanıcının bu yazıcıdaki kendi işlerini iptal eder."""
    try:
        r = subprocess.run(["cancel", "-a", name], capture_output=True, timeout=15, shell=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def scan_app_command() -> list[str] | None:
    import shutil

    for cmd in ("simple-scan", "skanlite", "xsane"):
        if shutil.which(cmd):
            return [cmd]
    return None


def detect_usb_printers(devices_dir: Path = USB_DEVICES) -> list[str]:
    """Takılı USB yazıcıların adları (arayüz sınıfı 07 = Printer)."""
    names: list[str] = []
    if not devices_dir.is_dir():
        return names
    for iface in devices_dir.iterdir():
        try:
            if (iface / "bInterfaceClass").read_text().strip() != "07":
                continue
            # Arayüz klasörü "1-2:1.0" biçimindedir; aygıt klasörü ":"den önceki kısımdır
            device = devices_dir / iface.name.split(":")[0]
            parts = []
            for attr in ("manufacturer", "product"):
                f = device / attr
                if f.exists():
                    parts.append(f.read_text().strip())
            name = " ".join(parts) or iface.name
        except OSError:
            continue
        if name not in names:
            names.append(name)
    return names


# --- Tarayıcılar ---


def parse_scanimage_list(output: str) -> list[str]:
    """`scanimage -L`: "device `epson2:net:1.2.3.4' is a Epson XP-245 flatbed scanner"."""
    scanners: list[str] = []
    for line in output.splitlines():
        m = re.match(r"^device [`'](.+?)' is an? (.+)$", line.strip())
        if m:
            scanners.append(m.group(2))
    return scanners


def list_scanners() -> list[str]:
    # Ağ taraması birkaç saniye sürebilir
    return parse_scanimage_list(_run(["scanimage", "-L"], timeout=30))


def printer_settings_command(desktop: str) -> list[str] | None:
    """Sistemin yazıcı ayarlarını açan komut; bulunamazsa None.

    GNOME: Ayarlar › Yazıcılar (`gnome-control-center --list` ile doğrulandı).
    Diğerleri: system-config-printer.
    """
    import shutil

    if desktop == "gnome" and shutil.which("gnome-control-center"):
        return ["gnome-control-center", "printers"]
    if shutil.which("system-config-printer"):
        return ["system-config-printer"]
    return None
