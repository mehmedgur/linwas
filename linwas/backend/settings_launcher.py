"""Sistem ayarlarını açma (Linwas'ın yapmadığı ayarlar için).

Yalnızca data/settings_map.json içindeki bilinen ayar uygulamaları açılabilir;
kullanıcı yetkisiyle çalışır, kuyruğa girmez, şifre istemez.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_MAP_FILE = Path(__file__).resolve().parent.parent / "data" / "settings_map.json"


def load_map(path: Path = _MAP_FILE) -> dict[str, dict[str, list[str]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def command_for(item_id: str, desktop: str, mapping: dict | None = None) -> list[str] | None:
    """Ayar öğesini açan komut; masaüstünde yoksa ana ayar ekranı, o da yoksa None."""
    mapping = load_map() if mapping is None else mapping
    for key in (item_id, "all"):
        cmd = mapping.get(key, {}).get(desktop)
        if cmd and shutil.which(cmd[0]):
            return list(cmd)
    return None


def open_settings(item_id: str, desktop: str) -> bool:
    cmd = command_for(item_id, desktop)
    if not cmd:
        return False
    try:
        subprocess.Popen(
            cmd,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    return True
