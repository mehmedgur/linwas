"""Hazırda bekletme kurulabilir mi: ön koşul denetimi (kullanıcı yetkisiyle, yalnızca okur).

Kurulumu root helper'ın `hibernate.setup` işlemi yapar (core/hibernate.py, core/helper.py).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from linwas.core import hibernate

# Kurulum engelleri (arayüz metinleri power_texts.setup_problem_text'te)
#   lockdown: Secure Boot çekirdek kilidi · kernel: çekirdek desteklemiyor · fs: dosya sistemi
#   btrfs_tools: btrfs-progs eski · bootloader: GRUB yok · initramfs: initramfs-tools yok
#   space: yetersiz boş alan · manual: /swapfile elle oluşturulmuş


@dataclass
class SetupCheck:
    installed: bool = False  # Linwas kurmuş (fstab işareti ya da GRUB dosyası var)
    reboot_needed: bool = False  # kuruldu ama çalışan çekirdek henüz resume_offset'i bilmiyor
    problems: list[str] = field(default_factory=list)
    fstype: str = ""
    ram_gb: int = 0
    recommended_gb: int = 0
    minimum_gb: int = 0
    free_gb: int = 0
    disk_swap_gb: int = 0  # mevcut disk swap'ı (zram hariç)

    @property
    def possible(self) -> bool:
        return not self.installed and not self.problems


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _out(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _btrfs_progs_ok() -> bool:
    """`mkswapfile` ve `map-swapfile` btrfs-progs 6.1 ile geldi."""
    m = re.search(r"v(\d+)\.(\d+)", _out(["btrfs", "--version"]))
    return bool(m and (int(m.group(1)), int(m.group(2))) >= (6, 1))


def _mem_total_kb() -> int:
    m = re.search(r"^MemTotal:\s+(\d+)", _read(Path("/proc/meminfo")), re.M)
    return int(m.group(1)) if m else 0


def check() -> SetupCheck:
    result = SetupCheck()
    fstab = _read(hibernate.FSTAB)
    result.installed = hibernate.has_fstab_entry(fstab) or hibernate.GRUB_DROPIN.exists()
    if result.installed:
        result.reboot_needed = not hibernate.cmdline_resume_offset(_read(Path("/proc/cmdline")))

    mem_kb = _mem_total_kb()
    result.ram_gb = hibernate.recommended_size_gb(mem_kb)
    result.recommended_gb = result.ram_gb
    result.minimum_gb = hibernate.minimum_size_gb(mem_kb)
    swaps = hibernate.parse_swaps(_read(Path("/proc/swaps")))
    result.disk_swap_gb = hibernate.disk_swap_kb(swaps) // (1024 * 1024)
    if result.installed:
        return result

    problems = result.problems
    if "disk" not in _read(Path("/sys/power/state")).split():
        problems.append("kernel")
    lockdown = re.search(r"\[(\w+)\]", _read(Path("/sys/kernel/security/lockdown")))
    if lockdown and lockdown.group(1) != "none":
        problems.append("lockdown")
    result.fstype = _out(["findmnt", "-no", "FSTYPE", "/"]).strip()
    if result.fstype not in hibernate.SUPPORTED_FS:
        problems.append("fs")
    elif result.fstype == "btrfs" and not _btrfs_progs_ok():
        problems.append("btrfs_tools")
    if not Path("/etc/default/grub").is_file() or not (
        shutil.which("update-grub") or shutil.which("grub-mkconfig")
    ):
        problems.append("bootloader")
    if not shutil.which("update-initramfs"):
        problems.append("initramfs")
    if hibernate.SWAPFILE.exists() or hibernate.other_swapfile_entry(fstab):
        problems.append("manual")
    try:
        result.free_gb = shutil.disk_usage("/").free // (1024**3)
    except OSError:
        result.free_gb = 0
    if result.free_gb < result.minimum_gb + hibernate.SPARE_GB:
        problems.append("space")
    return result
