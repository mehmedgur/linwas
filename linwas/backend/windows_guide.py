# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
""" "Windows'ta nasıl?" rehberi: Windows terimi → Linux karşılığı (data/windows_map.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_MAP_FILE = Path(__file__).resolve().parent.parent / "data" / "windows_map.json"

KINDS = ("setting", "program", "shortcut", "concept")


@dataclass
class GuideEntry:
    kind: str
    windows: list[str]
    text: dict[str, str]  # dil → açıklama
    action: dict[str, str] = field(default_factory=dict)  # page / settings / search


def _fold(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").casefold().strip()


def load(path: Path = _MAP_FILE) -> list[GuideEntry]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = []
    for e in data.get("entries", []):
        if isinstance(e, dict) and e.get("windows"):
            entries.append(
                GuideEntry(
                    kind=e.get("kind", "concept"),
                    windows=list(e["windows"]),
                    text={"tr": e.get("tr", ""), "en": e.get("en", "")},
                    action=dict(e.get("action") or {}),
                )
            )
    return entries


def search(query: str, entries: list[GuideEntry], kind: str = "") -> list[GuideEntry]:
    """Windows terimlerinde ve açıklamada arar; Windows teriminde eşleşenler önce."""
    q = _fold(query)
    pool = [e for e in entries if not kind or e.kind == kind]
    if not q:
        return pool
    by_term = [e for e in pool if any(q in _fold(w) for w in e.windows)]
    by_text = [e for e in pool if e not in by_term and any(q in _fold(t) for t in e.text.values())]
    return by_term + by_text
