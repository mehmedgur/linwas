# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Windows programlarını Bottles ile çalıştırma (kullanıcı yetkisiyle; kabuk kullanılmaz).

Linwas, Flatpak Bottles'ı resmi komut satırı aracıyla (`bottles-cli`) arka planda yönetir:
https://docs.usebottles.com/advanced/cli
Her program kendi şişesinde (Wine ortamı) çalışır. Linwas'ın oluşturduğu şişeler
~/.local/share/linwas/bottles.json kaydında tutulur; yalnızca bunlar listelenir/silinir.

Flatpak Bottles'ın ev klasörüne erişim izni yoktur; kurulum dosyasının klasörü yalnızca o
çalıştırma için salt okunur açılır (`flatpak run --filesystem=<klasör>:ro`).

Bottles beğenilmezse ENABLED = False yapılır; Linwas dağıtım Wine'ına (backend/wine.py) döner.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ENABLED = True

APP_ID = "com.usebottles.bottles"
ENVIRONMENTS = ("application", "gaming")
SHORTCUT_PREFIX = "linwas-bottle-"


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def registry_path() -> Path:
    return _data_home() / "linwas" / "bottles.json"


def bottles_dir() -> Path:
    """Flatpak Bottles'ın şişeleri tuttuğu klasör."""
    return Path.home() / ".var" / "app" / APP_ID / "data" / "bottles" / "bottles"


def applications_dir() -> Path:
    return _data_home() / "applications"


# --- Kurulu mu? ---


def flatpak_available() -> bool:
    return shutil.which("flatpak") is not None


def bottles_available() -> bool:
    if not flatpak_available():
        return False
    try:
        r = subprocess.run(
            ["flatpak", "info", APP_ID], capture_output=True, timeout=15, shell=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


# --- Komutlar (argv listeleri; QProcess ya da subprocess ile kabuksuz çalıştırılır) ---


def _cli(*args: str, read_dir: str = "") -> list[str]:
    argv = ["flatpak", "run"]
    if read_dir:
        argv.append(f"--filesystem={read_dir}:ro")
    return [*argv, "--command=bottles-cli", APP_ID, *args]


def new_command(bottle: str, environment: str = "application") -> list[str]:
    env = environment if environment in ENVIRONMENTS else "application"
    return _cli("new", "--bottle-name", bottle, "--environment", env, "--arch", "win64")


def run_exe_command(bottle: str, exe: str | Path) -> list[str]:
    path = Path(exe).resolve()
    return _cli("run", "-b", bottle, "-e", str(path), read_dir=str(path.parent))


def run_program_command(bottle: str, program: str, read_dir: str = "") -> list[str]:
    return _cli("run", "-b", bottle, "-p", program, read_dir=read_dir)


def add_program_command(bottle: str, name: str, exe: str | Path) -> list[str]:
    path = Path(exe).resolve()
    return _cli("add", "-b", bottle, "-n", name, "-p", str(path), read_dir=str(path.parent))


def programs_command(bottle: str) -> list[str]:
    return _cli("--json", "programs", "-b", bottle)


def uninstaller_command(bottle: str) -> list[str]:
    return _cli("tools", "uninstaller", "-b", bottle)


def parse_programs(out: str) -> list[dict]:
    """`--json programs` çıktısı → program sözlükleri (en azından "name" alanı olanlar)."""
    start = out.find("[")
    if start < 0:
        return []
    try:
        data = json.loads(out[start:])
    except json.JSONDecodeError:
        return []
    return [p for p in data if isinstance(p, dict) and isinstance(p.get("name"), str)]


def list_programs(bottle: str, timeout: int = 60) -> list[dict]:
    try:
        r = subprocess.run(
            programs_command(bottle), capture_output=True, text=True, timeout=timeout, shell=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_programs(r.stdout) if r.returncode == 0 else []


# --- Şişe kaydı ---


def slug(name: str) -> str:
    """Şişe adı: küçük harf, rakam ve tire (Bottles klasör adı da bununla aynı olur)."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")
    text = re.sub(r"[^a-z0-9]+", "-", name.translate(table).lower()).strip("-")
    return text[:40].strip("-") or "program"


@dataclass
class Bottle:
    id: str  # Bottles'taki şişe adı
    name: str  # kullanıcıya gösterilen ad
    environment: str = "application"
    reason: str = ""  # "risk" ise yüksek riskli dosya için açıldı
    created: str = ""
    read_dir: str = ""  # kurulmadan doğrudan açılan programın klasörü
    programs: list[dict] = field(default_factory=list)


def load_registry() -> dict[str, dict]:
    try:
        data = json.loads(registry_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _save_registry(data: dict[str, dict]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def new_bottle_id(name: str) -> str:
    """Kayıtta ve Bottles klasöründe olmayan yeni şişe adı."""
    base = slug(name)
    taken = set(load_registry())
    candidate, n = base, 2
    while candidate in taken or (bottles_dir() / candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def register(bottle: Bottle) -> None:
    data = load_registry()
    data[bottle.id] = {
        "name": bottle.name,
        "environment": bottle.environment,
        "reason": bottle.reason,
        "created": bottle.created or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_dir": bottle.read_dir,
    }
    _save_registry(data)


def set_read_dir(bottle_id: str, read_dir: str) -> None:
    data = load_registry()
    if bottle_id in data:
        data[bottle_id]["read_dir"] = read_dir
        _save_registry(data)


def list_bottles() -> list[Bottle]:
    """Linwas'ın oluşturduğu ve hâlâ var olan şişeler (ada göre sıralı)."""
    result = []
    for bottle_id, meta in load_registry().items():
        if not (bottles_dir() / bottle_id).is_dir():
            continue
        result.append(
            Bottle(
                id=bottle_id,
                name=meta.get("name") or bottle_id,
                environment=meta.get("environment", "application"),
                reason=meta.get("reason", ""),
                created=meta.get("created", ""),
                read_dir=meta.get("read_dir", ""),
            )
        )
    return sorted(result, key=lambda b: b.name.lower())


def remove_bottle(bottle_id: str) -> bool:
    """Şişeyi, menü kısayollarını ve kaydını siler. Yalnızca Linwas'ın kaydındaki şişeler."""
    data = load_registry()
    if bottle_id not in data or not bottle_id or "/" in bottle_id or bottle_id.startswith("."):
        return False
    path = bottles_dir() / bottle_id
    if path.exists() and path.resolve().parent != bottles_dir().resolve():
        return False
    for file in shortcut_files(bottle_id):
        file.unlink(missing_ok=True)
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        return False
    del data[bottle_id]
    _save_registry(data)
    return True


# --- Menü kısayolları (.desktop) ---


def _exec_quote(arg: str) -> str:
    """Desktop Entry belirtimine göre Exec argümanı (gerekirse çift tırnak + kaçış)."""
    arg = arg.replace("%", "%%")
    if not re.search(r"[\s\"'\\`$<>~|&;*?#()]", arg):
        return arg
    escaped = re.sub(r'(["`$\\])', r"\\\1", arg)
    # .desktop değerlerinde ters eğik çizgi bir kez daha kaçırılır
    return '"' + escaped.replace("\\", "\\\\") + '"'


def _value(text: str) -> str:
    return text.replace("\n", " ").replace("\r", " ").strip()


def shortcut_path(bottle_id: str, program: str) -> Path:
    return applications_dir() / f"{SHORTCUT_PREFIX}{bottle_id}--{slug(program)}.desktop"


def write_shortcut(bottle_id: str, program: str, read_dir: str = "") -> Path:
    argv = run_program_command(bottle_id, program, read_dir)
    text = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_value(program)}\n"
        f"Exec={' '.join(_exec_quote(a) for a in argv)}\n"
        "Icon=application-x-ms-dos-executable\n"
        "Categories=Wine;\n"
        f"X-Linwas-Bottle={bottle_id}\n"
        f"X-Linwas-Program={_value(program)}\n"
    )
    path = shortcut_path(bottle_id, program)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def shortcut_files(bottle_id: str) -> list[Path]:
    directory = applications_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{SHORTCUT_PREFIX}{bottle_id}--*.desktop"))


def has_shortcut(bottle_id: str, program: str) -> bool:
    return shortcut_path(bottle_id, program).is_file()
