"""Sistem ve donanım özeti (Hakkında sayfası için).

Yalnızca /proc ve /sys okunur; komut çalıştırmaz.

Qt'ye bağımlı değildir. `root` parametresi testlerde sahte bir dosya ağacı vermek içindir.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SystemInfo:
    kernel: str = ""
    architecture: str = ""
    uptime_seconds: int = 0
    cpu_model: str = ""
    cpu_cores: int = 0  # fiziksel çekirdek (bilinmiyorsa 0)
    cpu_threads: int = 0
    ram_bytes: int = 0
    board: str = ""
    disks: tuple[str, ...] = field(default_factory=tuple)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def parse_cpuinfo(text: str) -> tuple[str, int, int]:
    """/proc/cpuinfo'dan (model adı, fiziksel çekirdek, iş parçacığı) çıkarır."""
    model = ""
    threads = 0
    cores: set[tuple[str, str]] = set()
    physical = ""
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "model name" and not model:
            model = value
        elif key == "processor":
            threads += 1
        elif key == "physical id":
            physical = value
        elif key == "core id":
            cores.add((physical, value))
    return model, len(cores), threads


def parse_meminfo_total(text: str) -> int:
    """/proc/meminfo'daki MemTotal değerini bayt olarak döndürür (yoksa 0)."""
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return 0


def parse_uptime(text: str) -> int:
    """/proc/uptime'ın ilk alanını saniye olarak döndürür (yoksa 0)."""
    try:
        return int(float(text.split()[0]))
    except (IndexError, ValueError):
        return 0


def _board(root: Path) -> str:
    dmi = root / "sys/class/dmi/id"
    vendor, name = _read(dmi / "board_vendor"), _read(dmi / "board_name")
    return " ".join(part for part in (vendor, name) if part)


def _disks(root: Path) -> tuple[str, ...]:
    """Dönen olmayan/dönen fiziksel diskler (loop, ram, zram, dm hariç) ve model adları."""
    models: list[str] = []
    block = root / "sys/block"
    try:
        entries = sorted(block.iterdir())
    except OSError:
        return ()
    for entry in entries:
        if entry.name.startswith(("loop", "ram", "zram", "dm-", "sr", "md")):
            continue
        model = _read(entry / "device/model")
        if model:
            models.append(model)
    return tuple(models)


def read_system_info(root: Path = Path("/")) -> SystemInfo:
    cpu_model, cores, threads = parse_cpuinfo(_read(root / "proc/cpuinfo"))
    return SystemInfo(
        kernel=platform.release() if root == Path("/") else "",
        architecture=platform.machine() if root == Path("/") else "",
        uptime_seconds=parse_uptime(_read(root / "proc/uptime")),
        cpu_model=cpu_model,
        cpu_cores=cores,
        cpu_threads=threads,
        ram_bytes=parse_meminfo_total(_read(root / "proc/meminfo")),
        board=_board(root),
        disks=_disks(root),
    )
