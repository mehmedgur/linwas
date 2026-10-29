# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Hibrit grafik (PRIME): iki ekran kartlı bilgisayarlarda güçlü kartı programa göre kullanma.

Varsayılan "Dengeli": tümleşik kart masaüstünü çizer, kullanıcının seçtiği programlar güçlü
kartla açılır. Bunun için programın menü kısayolu kullanıcının kendi uygulama klasörüne
(~/.local/share/applications, aynı dosya adıyla — sistemdekinin önüne geçer) kopyalanır:
- `PrefersNonDefaultGPU=true` (Desktop Entry Specification 1.4; GNOME switcheroo-control ile
  güçlü kartta başlatır),
- her `Exec=` satırının başına ortam değişkenleri:
  NVIDIA kapalı kaynak sürücü: `__NV_PRIME_RENDER_OFFLOAD=1`, `__GLX_VENDOR_LIBRARY_NAME=nvidia`,
  `__VK_LAYER_NV_optimus=NVIDIA_only` (NVIDIA "PRIME Render Offload" belgesi);
  diğerleri (Mesa: amdgpu, nouveau, i915): `DRI_PRIME=1`.
Linwas'ın yazdığı dosyalar `X-Linwas-GPU=true` ile işaretlenir; yalnızca bunlar silinir.

Ubuntu'da `prime-select` (nvidia-prime) varsa kip de seçilebilir: nvidia (Performans),
on-demand (Dengeli), intel (Tasarruf); root işlemi `prime.select`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from linwas.backend.devices import Device

MARK = "X-Linwas-GPU=true"
NVIDIA_ENV = {
    "__NV_PRIME_RENDER_OFFLOAD": "1",
    "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
    "__VK_LAYER_NV_optimus": "NVIDIA_only",
}
MESA_ENV = {"DRI_PRIME": "1"}
_BACKUP = ".linwas-orig"


@dataclass
class HybridInfo:
    integrated: Device
    discrete: Device
    env: dict[str, str]
    prime_select: bool  # Ubuntu nvidia-prime kuruluysa
    mode: str  # prime-select query: "nvidia" | "on-demand" | "intel" | ""


@dataclass
class DesktopApp:
    app_id: str  # dosya adı (ör. org.gnome.Calculator.desktop)
    name: str
    icon: str
    path: Path  # okunduğu dosya
    gpu: bool  # Linwas güçlü kart kısayolu var mı


def detect(devices: list[Device]) -> HybridInfo | None:
    gpus = [d for d in devices if d.group == "display"]
    if len(gpus) < 2:
        return None
    integrated = next((d for d in gpus if d.vendor == "8086"), gpus[0])
    discrete = next((d for d in gpus if d is not integrated), None)
    if discrete is None:
        return None
    env = NVIDIA_ENV if discrete.driver == "nvidia" else MESA_ENV
    prime = shutil.which("prime-select") is not None
    mode = ""
    if prime:
        try:
            out = subprocess.run(
                ["prime-select", "query"], capture_output=True, text=True, timeout=10
            ).stdout
            mode = out.strip()
        except (OSError, subprocess.TimeoutExpired):
            mode = ""
    return HybridInfo(integrated, discrete, env, prime, mode)


# --- Menü kısayolları ---


def user_apps_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "applications"


def _data_dirs() -> list[Path]:
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(d) / "applications" for d in dirs.split(":") if d]


def _entry(text: str) -> dict[str, str]:
    """[Desktop Entry] bölümünün anahtarları (yerelleştirilmiş adlar dahil)."""
    values: dict[str, str] = {}
    in_entry = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_entry = s == "[Desktop Entry]"
            continue
        if in_entry and "=" in s and not s.startswith("#"):
            key, _, value = s.partition("=")
            values.setdefault(key.strip(), value.strip())
    return values


def _localized_name(entry: dict[str, str], lang: str) -> str:
    return entry.get(f"Name[{lang}]") or entry.get("Name", "")


def list_apps(lang: str = "tr") -> list[DesktopApp]:
    """Menüde görünen uygulamalar; kullanıcı klasörü sistemdekinin önüne geçer."""
    seen: dict[str, DesktopApp] = {}
    for folder in [user_apps_dir(), *_data_dirs()]:
        try:
            files = sorted(folder.glob("*.desktop"))
        except OSError:
            continue
        for path in files:
            if path.name in seen:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            entry = _entry(text)
            if entry.get("Type") != "Application" or not entry.get("Exec"):
                seen[path.name] = None  # type: ignore[assignment]  # gizli; alttaki de sayılmasın
                continue
            if entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true":
                seen[path.name] = None  # type: ignore[assignment]
                continue
            seen[path.name] = DesktopApp(
                app_id=path.name,
                name=_localized_name(entry, lang) or path.stem,
                icon=entry.get("Icon", ""),
                path=path,
                gpu=MARK in text,
            )
    apps = [a for a in seen.values() if a is not None]
    return sorted(apps, key=lambda a: a.name.lower())


def gpu_text(original: str, env: dict[str, str]) -> str:
    """Kısayol metnine güçlü kart ayarlarını ekler (Exec önekleri + işaretler)."""
    prefix = "env " + " ".join(f"{k}={v}" for k, v in env.items()) + " "
    out: list[str] = []
    in_entry = False
    for line in original.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_entry = s == "[Desktop Entry]"
            out.append(line)
            if in_entry:
                out.append("PrefersNonDefaultGPU=true")
                out.append(MARK)
            continue
        if in_entry and (s.startswith("PrefersNonDefaultGPU=") or s == MARK):
            continue
        if s.startswith("Exec=") and not s.startswith("Exec=" + prefix):
            line = "Exec=" + prefix + s[len("Exec=") :]
        out.append(line)
    return "\n".join(out) + "\n"


def enable(app: DesktopApp, env: dict[str, str]) -> None:
    """Programı güçlü kartla açılacak şekilde kullanıcı kısayolu yazar."""
    text = app.path.read_text(encoding="utf-8", errors="replace")
    target = user_apps_dir() / app.app_id
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and MARK not in text:
        # Kullanıcının kendi kısayolu: kapatınca geri gelsin diye saklanır (menü okumaz)
        target.replace(target.with_name(target.name + _BACKUP))
    target.write_text(gpu_text(text, env), encoding="utf-8")


def disable(app: DesktopApp) -> bool:
    """Linwas'ın yazdığı kısayolu siler (sistemdeki asıl kısayol yeniden geçerli olur)."""
    target = user_apps_dir() / app.app_id
    try:
        if MARK not in target.read_text(encoding="utf-8", errors="replace"):
            return False
        target.unlink()
        backup = target.with_name(target.name + _BACKUP)
        if backup.exists():
            backup.replace(target)
    except OSError:
        return False
    return True
