# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Aylık token kullanım sayacı.

Her sağlayıcı için ayrı aylık limit ve kullanım takibi.
Veritabanı: ~/.local/share/linwas/ai_usage.db
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".local" / "share" / "linwas" / "ai_usage.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    year_month  TEXT NOT NULL,  -- "2026-10" biçiminde
    input_tok   INTEGER NOT NULL DEFAULT 0,
    output_tok  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS limits (
    provider    TEXT PRIMARY KEY,
    monthly_limit INTEGER NOT NULL DEFAULT 0  -- 0 = sınırsız
);
"""


def _this_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@dataclass
class MonthlyUsage:
    provider: str
    year_month: str
    input_tokens: int
    output_tokens: int
    limit: int  # 0 = sınırsız

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def limit_reached(self) -> bool:
        return self.limit > 0 and self.total >= self.limit


class UsageDB:
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

    def record(self, provider: str, input_tokens: int, output_tokens: int) -> None:
        """Kullanımı kayıt altına alır; mevcut satırı günceller veya yeni satır ekler."""
        month = _this_month()
        with self._connect() as con:
            row = con.execute(
                "SELECT id FROM usage WHERE provider=? AND year_month=?", (provider, month)
            ).fetchone()
            if row:
                con.execute(
                    "UPDATE usage SET input_tok=input_tok+?, output_tok=output_tok+? WHERE id=?",
                    (input_tokens, output_tokens, row["id"]),
                )
            else:
                _SQL = (
                    "INSERT INTO usage"
                    " (provider, year_month, input_tok, output_tok) VALUES (?,?,?,?)"
                )
                con.execute(_SQL, (provider, month, input_tokens, output_tokens))

    def get(self, provider: str, year_month: str | None = None) -> MonthlyUsage:
        """Belirtilen ay için kullanımı döner; yoksa sıfırlı nesne döner."""
        month = year_month or _this_month()
        with self._connect() as con:
            row = con.execute(
                "SELECT input_tok, output_tok FROM usage WHERE provider=? AND year_month=?",
                (provider, month),
            ).fetchone()
            limit_row = con.execute(
                "SELECT monthly_limit FROM limits WHERE provider=?", (provider,)
            ).fetchone()

        input_tok = row["input_tok"] if row else 0
        output_tok = row["output_tok"] if row else 0
        limit = limit_row["monthly_limit"] if limit_row else 0
        return MonthlyUsage(provider, month, input_tok, output_tok, limit)

    def set_limit(self, provider: str, monthly_limit: int) -> None:
        """Aylık token limitini ayarlar (0 = sınırsız)."""
        with self._connect() as con:
            con.execute(
                "INSERT INTO limits (provider, monthly_limit) VALUES (?,?)"
                " ON CONFLICT(provider) DO UPDATE SET monthly_limit=excluded.monthly_limit",
                (provider, monthly_limit),
            )

    def all_months(self, provider: str) -> list[MonthlyUsage]:
        """Sağlayıcının tüm aylık kullanım geçmişini döner."""
        with self._connect() as con:
            _SQL = (
                "SELECT year_month, input_tok, output_tok FROM usage"
                " WHERE provider=? ORDER BY year_month DESC"
            )
            rows = con.execute(_SQL, (provider,)).fetchall()
            limit_row = con.execute(
                "SELECT monthly_limit FROM limits WHERE provider=?", (provider,)
            ).fetchone()
        limit = limit_row["monthly_limit"] if limit_row else 0
        return [
            MonthlyUsage(provider, r["year_month"], r["input_tok"], r["output_tok"], limit)
            for r in rows
        ]
