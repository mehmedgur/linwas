"""Seçilmiş model listesi (data/ai_models.json).

Model kimlikleri sağlayıcının canlı listesiyle karşılaştırılır; yalnızca gerçekten
var olanlar gösterilir. Böylece listede eskiyen bir ad kullanıcıya hiç çıkmaz.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "ai_models.json"

# Rol anahtarları; arayüz bunları çevirir
ROLES = ("main", "fast", "hard")


@dataclass(frozen=True)
class CuratedModel:
    id: str
    label: str
    role: str  # ROLES'tan biri


def load_curated(provider_id: str, path: Path = _CATALOG_FILE) -> list[CuratedModel]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get(provider_id, [])
    return [
        CuratedModel(str(e["id"]), str(e.get("label") or e["id"]), str(e.get("role", "")))
        for e in entries
        if isinstance(e, dict) and e.get("id")
    ]


def available_curated(
    provider_id: str, live: list[str], path: Path = _CATALOG_FILE
) -> list[CuratedModel]:
    """Seçilmiş modellerden canlı listede olanlar (katalog sırasıyla)."""
    live_set = set(live)
    return [m for m in load_curated(provider_id, path) if m.id in live_set]
