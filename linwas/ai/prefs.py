"""AI tercihleri: son seçilen sağlayıcı ve sağlayıcı başına model.

Dosya: $XDG_CONFIG_HOME/linwas/ai.json (yoksa ~/.config/linwas/ai.json).
Anahtar burada tutulmaz (bkz. keystore).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "linwas" / "ai.json"


@dataclass
class AIPrefs:
    last_provider: str = ""
    models: dict[str, str] = field(default_factory=dict)  # sağlayıcı → son model
    panel_width: int = 340  # yan panel genişliği (piksel)
    panel_collapsed: bool = False  # yan panel daraltılmış mı


def load(path: Path | None = None) -> AIPrefs:
    try:
        data = json.loads((path or default_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AIPrefs()
    models = data.get("models")
    width = data.get("panel_width", 340)
    return AIPrefs(
        last_provider=str(data.get("last_provider", "")),
        models={str(k): str(v) for k, v in models.items()} if isinstance(models, dict) else {},
        panel_width=width if isinstance(width, int) and 200 <= width <= 1200 else 340,
        panel_collapsed=data.get("panel_collapsed") is True,
    )


def save(prefs: AIPrefs, path: Path | None = None) -> None:
    target = path or default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_provider": prefs.last_provider,
            "models": prefs.models,
            "panel_width": prefs.panel_width,
            "panel_collapsed": prefs.panel_collapsed,
        }
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # tercih kaydedilemezse uygulama çalışmaya devam eder


def update(path: Path | None = None, **changes: object) -> AIPrefs:
    """Dosyayı yeniden okuyup yalnızca verilen alanları değiştirir.

    Panel (model seçimi) ve yan şerit (genişlik) ayrı ayrı yazdığı için
    birbirlerinin değerlerini ezmemeleri gerekir.
    """
    current = load(path)
    for name, value in changes.items():
        if not hasattr(current, name):
            raise AttributeError(name)
        setattr(current, name, value)
    save(current, path)
    return current
