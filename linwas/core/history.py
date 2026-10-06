"""İşlem geçmişi: tamamlanan görevler SQLite'a kaydedilir.

Veritabanı ~/.local/share/linwas/history.db konumundadır ve kullanıcı
sahipliğindedir; root helper erişmez.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".local" / "share" / "linwas" / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    task_label  TEXT NOT NULL,
    step_labels TEXT NOT NULL,   -- JSON list
    result      TEXT NOT NULL,   -- "success" | "failure" | "partial"
    rollback_id TEXT             -- NULL if no rollback record
);
"""


@dataclass
class HistoryEntry:
    task_label: str
    step_labels: list[str]
    result: str  # "success" | "failure" | "partial"
    rollback_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HistoryDB:
    def __init__(self, db_path: Path = DEFAULT_DB) -> None:
        self._path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        try:
            con.executescript(_SCHEMA)
            yield con
            con.commit()
        finally:
            con.close()

    def add(self, entry: HistoryEntry) -> None:
        """Geçmişe kayıt ekler."""
        with self._connect() as con:
            con.execute(
                "INSERT INTO history (id, timestamp, task_label, step_labels, result, rollback_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.timestamp,
                    entry.task_label,
                    json.dumps(entry.step_labels, ensure_ascii=False),
                    entry.result,
                    entry.rollback_id,
                ),
            )

    def get(self, entry_id: str) -> HistoryEntry | None:
        """ID'ye göre kayıt döner; bulunamazsa None."""
        with self._connect() as con:
            row = con.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def list(self, limit: int = 100) -> list[HistoryEntry]:
        """En son kayıtları zaman sırasına göre azalan olarak döner."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM history ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def clear(self) -> None:
        """Tüm geçmişi siler."""
        with self._connect() as con:
            con.execute("DELETE FROM history")


def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=row["id"],
        timestamp=row["timestamp"],
        task_label=row["task_label"],
        step_labels=json.loads(row["step_labels"]),
        result=row["result"],
        rollback_id=row["rollback_id"],
    )
