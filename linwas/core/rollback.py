# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Yedek ve geri alma kaydı.

Root helper, riskli bir görevi çalıştırmadan önce değiştirilecek dosyaların
kopyalarını ve kurulan/kaldırılan paketlerin listesini kaydeder. Bu kayıt
daha sonra değişiklikleri geri almak için kullanılır.

Kayıtlar /var/lib/linwas/rollback/ altında saklanır (root sahipliğinde).
Bu modül kayıt yapısını ve serileştirmeyi tanımlar; okuma/yazma işlemleri
hem root helper hem de kullanıcı alanı tarafından kullanılabilir.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROLLBACK_DIR = Path("/var/lib/linwas/rollback")


@dataclass
class FileBackup:
    """Tek bir dosya yedeği.

    backup_path boşsa dosya işlemden önce yoktu; geri almada silinir.
    """

    original_path: str
    backup_path: str


@dataclass
class RollbackRecord:
    """Bir görev için alınan geri alma kaydı."""

    task_label: str
    file_backups: list[FileBackup] = field(default_factory=list)
    # Kurulacak paketler (geri almada kaldırılır)
    packages_to_install: list[str] = field(default_factory=list)
    # Kaldırılacak paketler (geri almada yeniden kurulur)
    packages_to_remove: list[str] = field(default_factory=list)
    # Kaldırılan Flatpak uygulamaları ve snap'ler (geri almada yeniden kurulur)
    flatpaks_removed: list[str] = field(default_factory=list)
    snaps_removed: list[str] = field(default_factory=list)
    # snaps_removed içinden classic kipte kurulması gerekenler
    snaps_classic: list[str] = field(default_factory=list)
    # Kurulan Flatpak uygulamaları ve snap'ler (geri almada kaldırılır)
    flatpaks_installed: list[str] = field(default_factory=list)
    snaps_installed: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> RollbackRecord:
        d = json.loads(text)
        backups = [FileBackup(**b) for b in d.pop("file_backups", [])]
        # Bilinmeyen alanlar (ör. daha yeni sürümün kaydı) yok sayılır
        known = set(cls.__dataclass_fields__) - {"file_backups"}
        record = cls(**{k: v for k, v in d.items() if k in known})
        record.file_backups = backups
        return record

    @property
    def backup_dir(self) -> Path:
        return ROLLBACK_DIR / self.id


def record_path(record_id: str) -> Path:
    return ROLLBACK_DIR / record_id / "record.json"


def save_record(record: RollbackRecord, base_dir: Path = ROLLBACK_DIR) -> Path:
    """Kaydı diske yazar; kayıt dizinini oluşturur. Kayıt dosyasının yolunu döner."""
    dest = base_dir / record.id / "record.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(record.to_json(), encoding="utf-8")
    return dest


def load_record(record_id: str, base_dir: Path = ROLLBACK_DIR) -> RollbackRecord:
    """Kaydı diskten okur. Kayıt yoksa FileNotFoundError fırlatır."""
    path = base_dir / record_id / "record.json"
    return RollbackRecord.from_json(path.read_text(encoding="utf-8"))


def records_since(timestamp: str, base_dir: Path = ROLLBACK_DIR) -> list[RollbackRecord]:
    """Verilen ISO zamandan (dahil) sonra oluşturulan kayıtları döner."""
    return [r for r in list_records(base_dir) if r.timestamp >= timestamp]


def now_iso() -> str:
    """Kayıt zaman damgasıyla karşılaştırılabilir şimdiki zaman."""
    return datetime.now(timezone.utc).isoformat()


def list_records(base_dir: Path = ROLLBACK_DIR) -> list[RollbackRecord]:
    """Mevcut tüm geri alma kayıtlarını döner; zaman sırasına göre azalan."""
    records: list[RollbackRecord] = []
    if not base_dir.exists():
        return records
    for child in base_dir.iterdir():
        meta = child / "record.json"
        if meta.is_file():
            try:
                records.append(RollbackRecord.from_json(meta.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    records.sort(key=lambda r: r.timestamp, reverse=True)
    return records


def undo_ops(record: RollbackRecord) -> list[tuple[str, dict[str, str]]]:
    """Kaydı geri almak için gereken işlem listesini (op_id, params) döner.

    Bu liste TaskStep nesnelerine dönüştürülüp kuyruğa eklenebilir.
    """
    ops: list[tuple[str, dict[str, str]]] = []

    # Dosyaları işlem öncesi hâline döndür (helper kaydı kendi dizininden okur)
    if record.file_backups:
        ops.append(("rollback.restore_files", {"record_id": record.id}))

    # Kurulmuş programları kaldır (kritik paket korumalı, artık gerekmeyenlerle birlikte)
    for pkg in record.packages_to_install:
        ops.append(("app.remove_apt", {"name": pkg}))
    for app_id in record.flatpaks_installed:
        ops.append(("app.remove_flatpak", {"app_id": app_id}))
    for snap in record.snaps_installed:
        ops.append(("app.remove_snap", {"name": snap}))

    # Kaldırılmış paketleri yeniden kur
    for pkg in record.packages_to_remove:
        ops.append(("package.install", {"name": pkg}))

    for app_id in record.flatpaks_removed:
        ops.append(("flatpak.install", {"app_id": app_id}))

    for snap in record.snaps_removed:
        op = "snap.install_classic" if snap in record.snaps_classic else "snap.install"
        ops.append((op, {"name": snap}))

    return ops
