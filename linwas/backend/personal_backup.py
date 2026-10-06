"""Kişisel dosya yedeği: kullanıcı klasörlerini harici diske / USB'ye kopyalar.

Kullanıcı yetkisiyle çalışır (root yok). Kopyalama `rsync` ile yapılır;
FAT/exFAT disklerde sahiplik/izin kopyalanamadığı için -a yerine -rt kullanılır.
Yedekler hedefte "Linwas-Yedek/<tarih-saat>/<klasör>" altında durur.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BACKUP_DIR_NAME = "Linwas-Yedek"

# xdg-user-dir anahtarları (xdg-user-dirs)
USER_DIR_KEYS = ("DOCUMENTS", "PICTURES", "MUSIC", "VIDEOS", "DESKTOP", "DOWNLOAD")


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


@dataclass
class SourceFolder:
    key: str  # ör. DOCUMENTS
    path: Path


def user_folders() -> list[SourceFolder]:
    """Kullanıcının standart klasörleri (yerelleştirilmiş adlarıyla, var olanlar)."""
    home = Path.home()
    folders: list[SourceFolder] = []
    for key in USER_DIR_KEYS:
        out = _run(["xdg-user-dir", key]).strip()
        path = Path(out) if out else None
        # xdg-user-dir tanımsız klasörde ev klasörünü döndürür
        if path and path != home and path.is_dir():
            folders.append(SourceFolder(key, path))
    return folders


@dataclass
class Destination:
    mountpoint: Path
    label: str
    size: str
    fstype: str


def parse_lsblk_removable(output: str) -> list[Destination]:
    """`lsblk -J -o NAME,MOUNTPOINT,LABEL,SIZE,FSTYPE,RM,HOTPLUG` → takılı harici diskler."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    found: list[Destination] = []

    def walk(devs: list[dict], removable: bool) -> None:
        for dev in devs:
            rm = removable or dev.get("rm") in (True, "1") or dev.get("hotplug") in (True, "1")
            mount = dev.get("mountpoint")
            if rm and mount and mount.startswith(("/media/", "/run/media/")):
                found.append(
                    Destination(
                        mountpoint=Path(mount),
                        label=dev.get("label") or Path(mount).name,
                        size=dev.get("size") or "",
                        fstype=dev.get("fstype") or "",
                    )
                )
            walk(dev.get("children") or [], rm)

    walk(data.get("blockdevices", []), False)
    return found


def list_destinations() -> list[Destination]:
    out = _run(["lsblk", "-J", "-o", "NAME,MOUNTPOINT,LABEL,SIZE,FSTYPE,RM,HOTPLUG"])
    return parse_lsblk_removable(out)


def free_bytes(path: Path) -> int:
    try:
        st = os.statvfs(path)
    except OSError:
        return 0
    return st.f_bavail * st.f_frsize


def folder_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


@dataclass
class BackupSet:
    path: Path
    created: datetime
    folders: list[str]


def list_backups(destination: Path) -> list[BackupSet]:
    """Hedefteki önceki yedekler, yeniden eskiye."""
    base = destination / BACKUP_DIR_NAME
    sets: list[BackupSet] = []
    if not base.is_dir():
        return sets
    for d in base.iterdir():
        try:
            created = datetime.strptime(d.name, "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            continue
        if d.is_dir():
            sets.append(BackupSet(d, created, sorted(p.name for p in d.iterdir() if p.is_dir())))
    sets.sort(key=lambda s: s.created, reverse=True)
    return sets


_RE_PROGRESS = re.compile(r"\s(\d{1,3})%\s")


def parse_progress(line: str) -> int | None:
    """`rsync --info=progress2` satırındaki toplam yüzde."""
    m = _RE_PROGRESS.search(" " + line + " ")
    return int(m.group(1)) if m else None


def rsync_command(source: Path, target: Path) -> list[str]:
    # Kaynak sonunda "/" yok: klasörün kendisi hedefin içine kopyalanır
    return ["rsync", "-rt", "--info=progress2", "--", str(source), str(target) + "/"]


def run_backup(
    sources: list[Path],
    destination: Path,
    on_progress: Callable[[int, int, int], None] | None = None,
    now: datetime | None = None,
) -> tuple[bool, Path, str]:
    """Klasörleri yedekler. on_progress(klasör sırası, klasör sayısı, yüzde).

    Döner: (başarılı, yedek klasörü, hata metni)
    """
    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    target = destination / BACKUP_DIR_NAME / stamp
    try:
        target.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        return False, target, str(exc)

    for i, src in enumerate(sources):
        try:
            proc = subprocess.Popen(
                rsync_command(src, target),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
        except FileNotFoundError:
            return False, target, "rsync bulunamadı"
        assert proc.stdout is not None
        # progress2 satırları "\r" ile güncellenir
        buf = ""
        while True:
            ch = proc.stdout.read(1)
            if not ch:
                break
            if ch in "\r\n":
                pct = parse_progress(buf)
                if pct is not None and on_progress:
                    on_progress(i, len(sources), pct)
                buf = ""
            else:
                buf += ch
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().strip() if proc.stderr else ""
            return False, target, err or f"rsync kodu {proc.returncode}"
        if on_progress:
            on_progress(i, len(sources), 100)
    return True, target, ""


# --- Geri yükleme ---

RESTORE_DIR_NAME = "Linwas-Geri-Yukleme"


def restore_targets(backup: BackupSet, mode: str) -> list[tuple[Path, Path]]:
    """(kaynak klasör, hedef üst klasör) çiftleri.

    mode="separate": ~/Linwas-Geri-Yukleme/<yedek-adı>/ altına (hiçbir şeye dokunmaz)
    mode="original": aynı adlı kullanıcı klasörüne (ör. Belgeler); hiç eşleşmezse ev klasörü
    """
    home = Path.home()
    if mode == "separate":
        parent = home / RESTORE_DIR_NAME / backup.path.name
        return [(backup.path / name, parent) for name in backup.folders]
    by_name = {f.path.name: f.path.parent for f in user_folders()}
    return [(backup.path / name, by_name.get(name, home)) for name in backup.folders]


def run_restore(
    backup: BackupSet,
    mode: str,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> tuple[bool, Path, str]:
    """Yedeği bilgisayara kopyalar. Var olan dosyaların üzerine yazılmaz (--ignore-existing).

    Döner: (başarılı, açılacak klasör, hata)
    """
    pairs = restore_targets(backup, mode)
    shown = pairs[0][1] if pairs else Path.home()
    for i, (src, parent) in enumerate(pairs):
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return False, shown, str(exc)
        cmd = [
            "rsync",
            "-rt",
            "--ignore-existing",
            "--info=progress2",
            "--",
            str(src),
            f"{parent}/",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False
            )
        except FileNotFoundError:
            return False, shown, "rsync bulunamadı"
        assert proc.stdout is not None
        buf = ""
        while ch := proc.stdout.read(1):
            if ch in "\r\n":
                pct = parse_progress(buf)
                if pct is not None and on_progress:
                    on_progress(i, len(pairs), pct)
                buf = ""
            else:
                buf += ch
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().strip() if proc.stderr else ""
            return False, shown, err or f"rsync kodu {proc.returncode}"
    return True, shown, ""
