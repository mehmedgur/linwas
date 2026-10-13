"""Linwas'ın kendi ayarları: tema, pencere kapatma, dil, arka plan ve bildirimler, yapay zekâ.

Dosya: $XDG_CONFIG_HOME/linwas/settings.json (yoksa ~/.config/linwas/settings.json).
Değişiklikler anında kaydedilir (Ayarlar sayfasında "Kaydet" düğmesi yok).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

THEMES = ("system", "light", "dark", "high_contrast")
# Linwas'ın kendi düzeni: macOS havası (varsayılan) ya da Windows görünümü
UI_STYLES = ("macos", "windows")
# ask: pencere kapatılınca her seferinde sor (varsayılan); "auto" eski ayar dosyalarından
# gelir, "ask" ile aynı davranır. tray: arka planda çalışmaya devam et (tepsi varsa simgeyle);
# quit: Linwas'ı kapat.
CLOSE_ACTIONS = ("auto", "ask", "tray", "quit")
LANGUAGES = ("tr", "en")
ERROR_CONSENT = ("ask", "yes", "no")  # hata kayıtlarını yardımcıya gönderme izni
# AI sohbetlerini saklama süresi: hiç, 7 gün, 30 gün, her zaman
AI_RETENTION = ("never", "7", "30", "forever")

_CLOCK = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "linwas" / "settings.json"


@dataclass
class AppSettings:
    theme: str = "system"
    ui_style: str = "macos"
    accent_color: str = ""  # Linwas vurgu rengi "#rrggbb"; boş = düzenin varsayılanı
    close_action: str = "ask"
    language: str = "tr"
    send_errors_to_ai: str = "ask"
    onboarding_done: bool = False
    exe_handler_set: bool = False  # .exe/.msi varsayılan uygulaması bir kez Linwas yapıldı
    # Bildirimler ve başlangıç
    autostart: bool = True  # oturum açılınca arka planda başla
    notify_updates: bool = True
    notify_restart: bool = True
    notify_autoupdate: bool = True
    notify_devices: bool = True
    quiet_hours: bool = False
    quiet_start: str = "22:00"
    quiet_end: str = "08:00"
    # Yapay zekâ
    ai_retention: str = "forever"
    ai_allow_system_info: bool = True
    # Gelişmiş (teknik) ayarlar
    show_details: bool = False  # görev penceresinde komut çıktısı baştan açık
    debug_log: bool = False  # ayrıntılı günlük dosyası

    @property
    def ask_on_close(self) -> bool:
        """Pencere kapatılınca küçültme / tamamen kapatma sorulur mu."""
        return self.close_action in ("auto", "ask")

    @property
    def keep_running(self) -> bool:
        """Pencere kapatılınca arka planda çalışmaya devam edilir mi."""
        return self.close_action != "quit"


_CHOICES = {
    "theme": THEMES,
    "ui_style": UI_STYLES,
    "close_action": CLOSE_ACTIONS,
    "language": LANGUAGES,
    "send_errors_to_ai": ERROR_CONSENT,
    "ai_retention": AI_RETENTION,
}


def from_dict(data: dict) -> AppSettings:
    """Doğrulanmış ayarlar; geçersiz ya da eksik alanlar varsayılan kalır."""
    s = AppSettings()
    for f in fields(AppSettings):
        value = data.get(f.name)
        default = getattr(s, f.name)
        if f.name in _CHOICES:
            if value in _CHOICES[f.name]:
                setattr(s, f.name, value)
        elif isinstance(default, bool):
            if isinstance(value, bool):
                setattr(s, f.name, value)
        elif f.name == "accent_color":
            if isinstance(value, str) and (value == "" or _HEX_COLOR.match(value)):
                setattr(s, f.name, value.lower())
        elif (
            f.name in ("quiet_start", "quiet_end")
            and isinstance(value, str)
            and _CLOCK.match(value)
        ):
            setattr(s, f.name, value)
    return s


def load(path: Path | None = None) -> AppSettings:
    try:
        data = json.loads((path or default_path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    return from_dict(data) if isinstance(data, dict) else AppSettings()


def save(settings: AppSettings, path: Path | None = None) -> None:
    target = path or default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    except OSError:
        pass


def in_quiet_hours(settings: AppSettings, hhmm: str) -> bool:
    """Saat (SS:DD) sessiz saatler içinde mi; gece yarısını aşan aralık desteklenir."""
    if not settings.quiet_hours:
        return False
    start, end = settings.quiet_start, settings.quiet_end
    if start == end:
        return False
    if start < end:
        return start <= hhmm < end
    return hhmm >= start or hhmm < end
