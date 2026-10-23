"""Linwas'ın kullanıcı adına tuttuğu veriler: listeleme, silme, ayarları dışa/içe aktarma.

API anahtarları sistem anahtarlığındadır; dışa aktarılmaz ve buradan silinmez.
Geri alma kayıtları root'a aittir (/var/lib/linwas/rollback); Yedekler ve geri alma
sayfasından yönetilir.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from linwas.core import app_settings

EXPORT_FORMAT = "linwas-settings"
EXPORT_VERSION = 1


def data_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "linwas"


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "linwas"


def log_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "linwas"


@dataclass
class DataItem:
    key: str  # "history" | "chats" | "usage" | "notifications" | "drivers" | "log"
    path: Path

    @property
    def size(self) -> int:
        try:
            if self.path.is_dir():
                return sum(p.stat().st_size for p in self.path.rglob("*") if p.is_file())
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def exists(self) -> bool:
        return self.path.exists()


def items() -> list[DataItem]:
    d = data_dir()
    return [
        DataItem("history", d / "history.db"),
        DataItem("chats", d / "chat_history.db"),
        DataItem("usage", d / "ai_usage.db"),
        DataItem("notifications", d / "notify_state.json"),
        DataItem("drivers", d / "driver_changes.json"),
        DataItem("log", log_dir()),
    ]


def delete(key: str) -> bool:
    """Tek bir veri öğesini siler (veritabanları yeniden boş oluşturulur)."""
    item = next((i for i in items() if i.key == key), None)
    if item is None:
        return False
    try:
        if item.path.is_dir():
            for p in item.path.glob("*.log*"):
                p.unlink(missing_ok=True)
        else:
            item.path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def delete_all() -> bool:
    return all(delete(i.key) for i in items())


def rollback_record_count() -> int | None:
    """Geri alma kaydı sayısı (okunamazsa None)."""
    from linwas.core.rollback import list_records

    try:
        return len(list_records())
    except OSError:
        return None


# --- Ayarları dışa / içe aktarma ---


def export_settings(target: Path) -> None:
    """Linwas ayarları + AI tercihleri + aylık sınırlar (anahtarlar hariç) tek JSON dosyasına."""
    from linwas.ai import prefs
    from linwas.ai.manager import ALL_PROVIDERS
    from linwas.ai.usage import UsageDB

    usage = UsageDB()
    data = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "settings": asdict(app_settings.load()),
        "ai_prefs": asdict(prefs.load()),
        "ai_limits": {p.provider_id: usage.get(p.provider_id).limit for p in ALL_PROVIDERS},
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ImportError_(ValueError):  # noqa: N801 - yerleşik ImportError ile karışmasın
    """Dosya Linwas ayar dosyası değil ya da okunamadı."""


def import_settings(source: Path) -> app_settings.AppSettings:
    """Dosyadaki ayarları doğrulayıp kaydeder; yeni ayarları döner."""
    from linwas.ai import prefs
    from linwas.ai.usage import UsageDB

    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImportError_(str(exc)) from exc
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise ImportError_("not a Linwas settings file")
    current = app_settings.load()
    imported = app_settings.from_dict(data.get("settings") or {})
    # Bu bilgisayara ait durum bilgileri taşınmaz
    imported.onboarding_done = current.onboarding_done
    imported.exe_handler_set = current.exe_handler_set
    app_settings.save(imported)

    ai = data.get("ai_prefs")
    if isinstance(ai, dict):
        loaded = prefs.load()
        if isinstance(ai.get("last_provider"), str):
            loaded.last_provider = ai["last_provider"]
        if isinstance(ai.get("models"), dict):
            loaded.models = {str(k): str(v) for k, v in ai["models"].items()}
        prefs.save(loaded)
    limits = data.get("ai_limits")
    if isinstance(limits, dict):
        usage = UsageDB()
        for provider, limit in limits.items():
            if isinstance(limit, int) and 0 <= limit <= 100_000_000:
                usage.set_limit(str(provider), limit)
    return imported


def reset_settings() -> app_settings.AppSettings:
    """Linwas ayarlarını varsayılana döndürür (ilk açılış bilgileri korunur)."""
    current = app_settings.load()
    fresh = app_settings.AppSettings(
        onboarding_done=current.onboarding_done, exe_handler_set=current.exe_handler_set
    )
    app_settings.save(fresh)
    return fresh
