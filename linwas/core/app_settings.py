"""Linwas'ın kendi ayarları: tema, pencere kapatma, dil.

Dosya: $XDG_CONFIG_HOME/linwas/settings.json (yoksa ~/.config/linwas/settings.json).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

THEMES = ("system", "light", "dark", "high_contrast")
CLOSE_ACTIONS = ("auto", "tray", "quit")  # auto: tepsi varsa tepsiye, yoksa kapat
LANGUAGES = ("tr", "en")
ERROR_CONSENT = ("ask", "yes", "no")  # hata kayıtlarını yardımcıya gönderme izni


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "linwas" / "settings.json"


@dataclass
class AppSettings:
    theme: str = "system"
    close_action: str = "auto"
    language: str = "tr"
    send_errors_to_ai: str = "ask"
    onboarding_done: bool = False
    exe_handler_set: bool = False  # .exe/.msi varsayılan uygulaması bir kez Linwas yapıldı


def load(path: Path | None = None) -> AppSettings:
    try:
        data = json.loads((path or default_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    s = AppSettings()
    if data.get("theme") in THEMES:
        s.theme = data["theme"]
    if data.get("close_action") in CLOSE_ACTIONS:
        s.close_action = data["close_action"]
    if data.get("language") in LANGUAGES:
        s.language = data["language"]
    s.onboarding_done = data.get("onboarding_done") is True
    s.exe_handler_set = data.get("exe_handler_set") is True
    if data.get("send_errors_to_ai") in ERROR_CONSENT:
        s.send_errors_to_ai = data["send_errors_to_ai"]
    return s


def save(settings: AppSettings, path: Path | None = None) -> None:
    target = path or default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except OSError:
        pass
