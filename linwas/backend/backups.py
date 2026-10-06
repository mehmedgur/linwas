"""Yedek ve geri alma kaydı sorgulama.

Timeshift anlık görüntüleri ve Linwas değişiklik yedeklerini birleşik listeler.
Salt okunur; silme/geri yükleme whitelist üzerinden root helper yapar.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from linwas.core.rollback import RollbackRecord, list_records


@dataclass
class TimeshiftSnapshot:
    name: str  # ör. "2026-10-06_12-00-01"
    tag: str  # "O" (manual/ondemand), "B" (boot), "H" (hourly) vb.
    date: str  # okunabilir tarih
    device: str  # ör. "/dev/sda2"
    size_mb: float


@dataclass
class BackupEntry:
    """Birleşik yedek kaydı: Timeshift veya Linwas rollback."""

    id: str
    label: str
    date: str
    source: str  # "timeshift" | "linwas"
    size_mb: float
    details: str  # hangi işlem için alındı


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.stdout + r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def timeshift_available() -> bool:
    try:
        subprocess.run(["which", "timeshift"], capture_output=True, shell=False, timeout=3)
        return Path("/usr/bin/timeshift").exists() or Path("/usr/sbin/timeshift").exists()
    except Exception:
        return False


def list_timeshift_snapshots() -> list[TimeshiftSnapshot]:
    """Timeshift anlık görüntülerini döner; timeshift yoksa boş liste."""
    out = _run(["timeshift", "--list"])
    if not out:
        return []

    snapshots: list[TimeshiftSnapshot] = []
    # Örnek satır: "1  |  2026-10-06_12-00-01  |  O  |  Just Now  |  /dev/sda2  |  1.2 GB"
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        # İlk alan sıra numarası olmalı
        if not parts[0].strip().isdigit():
            continue
        name = parts[1].strip() if len(parts) > 1 else ""
        tag = parts[2].strip() if len(parts) > 2 else ""
        date = parts[3].strip() if len(parts) > 3 else ""
        device = parts[4].strip() if len(parts) > 4 else ""
        size_str = parts[5].strip() if len(parts) > 5 else "0"

        size_mb = _parse_size(size_str)
        snapshots.append(
            TimeshiftSnapshot(name=name, tag=tag, date=date, device=device, size_mb=size_mb)
        )
    return snapshots


def _parse_size(s: str) -> float:
    """'1.2 GB' → 1228.8, '500 MB' → 500, '0' → 0."""
    s = s.strip()
    m = re.match(r"([\d.]+)\s*(GB|MB|KB|B)?", s, re.IGNORECASE)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = (m.group(2) or "MB").upper()
    return {"GB": val * 1024, "MB": val, "KB": val / 1024, "B": val / (1024 * 1024)}.get(unit, val)


def list_linwas_records() -> list[RollbackRecord]:
    """Linwas değişiklik yedeklerini döner."""
    return list_records()


def combined_backups() -> list[BackupEntry]:
    """Timeshift + Linwas yedeklerini birleşik, tarih sırasına göre azalan liste."""
    entries: list[BackupEntry] = []

    for snap in list_timeshift_snapshots():
        entries.append(
            BackupEntry(
                id=f"timeshift:{snap.name}",
                label=f"System Snapshot ({snap.tag})",
                date=snap.date,
                source="timeshift",
                size_mb=snap.size_mb,
                details=f"Device: {snap.device}",
            )
        )

    for rec in list_linwas_records():
        pkg_count = len(rec.packages_to_install) + len(rec.packages_to_remove)
        file_count = len(rec.file_backups)
        details_parts = []
        if pkg_count:
            details_parts.append(f"{pkg_count} package change(s)")
        if file_count:
            details_parts.append(f"{file_count} file(s)")
        entries.append(
            BackupEntry(
                id=f"linwas:{rec.id}",
                label=rec.task_label,
                date=rec.timestamp[:16].replace("T", " "),
                source="linwas",
                size_mb=0.0,
                details=", ".join(details_parts) or "Quick rollback record",
            )
        )

    return entries
