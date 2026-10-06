"""Sohbet geçmişi.

Yerel SQLite'a kaydedilir; kullanıcı tüm geçmişi silebilir.
Veritabanı: ~/.local/share/linwas/chat_history.db
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from linwas.ai.base import Message

DEFAULT_DB = Path.home() / ".local" / "share" / "linwas" / "chat_history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
PRAGMA foreign_keys = ON;
"""

# Eski veritabanlarına sonradan eklenen sütunlar
_MIGRATIONS = (("messages", "model", "TEXT NOT NULL DEFAULT ''"),)

# Kullanıcı mesajına eklenen sistem bilgisi bu işaretten sonra gelir (manager.AISession)
CONTEXT_MARKER = "\n\n--- Sistem bilgim ---\n"


def display_text(content: str) -> str:
    """Mesajı ekranda göstermek için sistem bilgisi ekini atar."""
    return content.split(CONTEXT_MARKER, 1)[0]


@dataclass
class Conversation:
    provider: str
    model: str
    messages: list[Message] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    title: str = ""  # liste için: ilk kullanıcı mesajının başı


class ChatHistoryDB:
    def __init__(self, db_path: Path = DEFAULT_DB) -> None:
        self._path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            con.executescript(_SCHEMA)
            for table, column, decl in _MIGRATIONS:
                cols = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
                if column not in cols:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            yield con
            con.commit()
        finally:
            con.close()

    def save(self, conv: Conversation) -> None:
        """Konuşmayı kaydeder veya günceller."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as con:
            con.execute(
                "INSERT INTO conversations (id, provider, model, created_at, updated_at)"
                " VALUES (?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,"
                " provider=excluded.provider, model=excluded.model",
                (conv.id, conv.provider, conv.model, conv.created_at, now),
            )
            # Mevcut mesajları sil, yeniden ekle (basit yaklaşım)
            con.execute("DELETE FROM messages WHERE conversation_id=?", (conv.id,))
            for msg in conv.messages:
                _SQL = (
                    "INSERT INTO messages"
                    " (conversation_id, role, content, created_at, model) VALUES (?,?,?,?,?)"
                )
                con.execute(_SQL, (conv.id, msg.role, msg.content, now, msg.model))

    def load(self, conv_id: str) -> Conversation | None:
        """Konuşmayı yükler; bulunamazsa None döner."""
        with self._connect() as con:
            row = con.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
            if not row:
                return None
            msg_rows = con.execute(
                "SELECT role, content, model FROM messages WHERE conversation_id=? ORDER BY id",
                (conv_id,),
            ).fetchall()

        messages = [
            Message(role=r["role"], content=r["content"], model=r["model"]) for r in msg_rows
        ]
        return Conversation(
            id=row["id"],
            provider=row["provider"],
            model=row["model"],
            messages=messages,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list(self, limit: int = 50) -> list[Conversation]:
        """Son konuşmaları döner (mesajsız, başlık için)."""
        with self._connect() as con:
            rows = con.execute(
                "SELECT c.*, (SELECT m.content FROM messages m WHERE m.conversation_id = c.id"
                " AND m.role = 'user' ORDER BY m.id LIMIT 1) AS first_user"
                " FROM conversations c ORDER BY c.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            Conversation(
                id=r["id"],
                provider=r["provider"],
                model=r["model"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                title=_title(r["first_user"] or ""),
            )
            for r in rows
        ]

    def delete(self, conv_id: str) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM conversations WHERE id=?", (conv_id,))

    def clear_all(self) -> None:
        """Tüm geçmişi siler."""
        with self._connect() as con:
            con.execute("DELETE FROM conversations")


def _title(first_user_message: str, length: int = 60) -> str:
    text = " ".join(display_text(first_user_message).split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"
