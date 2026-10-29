# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sürücü sürüm seçenekleri, sürücü değişikliği geçmişi ve Secure Boot (salt okunur).

- NVIDIA seçenekleri depodan okunur (paket adları dağıtıma göre değişir):
  Ubuntu: nvidia-driver-<sürüm>[-open]; Debian/Pardus: nvidia-driver, nvidia-tesla-<n>-driver,
  nvidia-legacy-<n>xx-driver. Önerilen: `ubuntu-drivers devices` ya da `nvidia-detect`.
- Açık kaynak sürücüye (nouveau) dönmek için root işlemi `driver.remove_nvidia` kullanılır.
- Secure Boot: `mokutil --sb-state`; DKMS imza anahtarı Ubuntu'da
  /var/lib/shim-signed/mok/MOK.der, Debian'da /var/lib/dkms/mok.pub. Kayıt root işlemi
  `secureboot.enroll_mok` ile (tek kullanımlık şifre yeniden başlatmadaki mavi ekranda yazılır).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from linwas.backend.featured import parse_policy

NOUVEAU = ""  # açık kaynak sürücü seçeneğinin paket adı (kaldırma ile geçilir)
MOK_KEYS = (Path("/var/lib/shim-signed/mok/MOK.der"), Path("/var/lib/dkms/mok.pub"))

_NVIDIA_NAME = re.compile(
    r"^(nvidia-driver(-\d+(-open)?)?|nvidia-tesla-\d+-driver|nvidia-legacy-\d+xx-driver)$"
)


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return r.returncode, r.stdout + r.stderr


# --- NVIDIA seçenekleri ---


@dataclass
class DriverOption:
    package: str  # NOUVEAU ("") = açık kaynak sürücü
    version: str = ""
    installed: bool = False
    recommended: bool = False
    open_kernel: bool = False  # NVIDIA açık çekirdek modülleri (-open)

    @property
    def proprietary(self) -> bool:
        return bool(self.package)


def parse_ubuntu_drivers(out: str) -> str:
    """`ubuntu-drivers devices` → önerilen NVIDIA paketi."""
    for line in out.splitlines():
        m = re.match(r"^\s*driver\s*:\s*(\S+).*\brecommended\b", line)
        if m and m.group(1).startswith("nvidia-driver"):
            return m.group(1)
    return ""


def parse_nvidia_detect(out: str) -> str:
    """`nvidia-detect` → önerilen paket ("…recommended to install the <paket> package.")."""
    m = re.search(r"recommended to install the\s+(\S+)\s+package", out)
    return m.group(1) if m else ""


def _series(name: str) -> int:
    m = re.search(r"(\d+)", name)
    return int(m.group(1)) if m else 0


def nvidia_options() -> list[DriverOption]:
    """Bu sistemde kurulabilir NVIDIA sürücüleri + açık kaynak seçenek (önerilen işaretli)."""
    _, out = _run(["apt-cache", "pkgnames", "nvidia-"])
    names = sorted({n.strip() for n in out.splitlines() if _NVIDIA_NAME.match(n.strip())})
    pol = _run(["apt-cache", "policy", "--", *names])[1] if names else ""
    policy = parse_policy(pol)
    versions: dict[str, str] = {}
    if names:
        current = ""
        for line in pol.splitlines():
            if line and not line[0].isspace() and line.rstrip().endswith(":"):
                current = line.rstrip()[:-1]
            elif line.strip().startswith("Candidate:") and current:
                versions[current] = line.split(":", 1)[1].strip()

    recommended = parse_ubuntu_drivers(_run(["ubuntu-drivers", "devices"], timeout=60)[1])
    if not recommended:
        recommended = parse_nvidia_detect(_run(["nvidia-detect"])[1])
    options: list[DriverOption] = []
    for name in names:
        installed, candidate = policy.get(name, (False, False))
        if not candidate and not installed:
            continue
        options.append(
            DriverOption(
                package=name,
                version=versions.get(name, ""),
                installed=installed,
                open_kernel=name.endswith("-open"),
            )
        )
    if not recommended:
        # Yoksa: Debian'da "nvidia-driver", Ubuntu'da en yeni kapalı kaynak seri
        plain = [o for o in options if not o.open_kernel]
        if any(o.package == "nvidia-driver" for o in plain):
            recommended = "nvidia-driver"
        elif plain:
            recommended = max(plain, key=lambda o: _series(o.package)).package
    for option in options:
        option.recommended = option.package == recommended
    options.sort(key=lambda o: (not o.recommended, -_series(o.package), o.open_kernel))
    options.append(DriverOption(package=NOUVEAU, installed=not any(o.installed for o in options)))
    return options


def newer_series(options: list[DriverOption]) -> tuple[int, int]:
    """(kurulu NVIDIA serisi, depodaki daha yeni seri); yeni yoksa ikincisi 0.

    Yalnızca seri numaralı paketler karşılaştırılır (Ubuntu `nvidia-driver-<n>`); Debian/Pardus
    `nvidia-driver` tek pakettir, yeni sürümü normal güncellemeyle gelir. Eski kartlara özel
    (legacy/tesla) paketler önerilmez.
    """
    numbered = [
        o
        for o in options
        if o.package
        and _series(o.package)
        and not (o.open_kernel or o.package.endswith("-open"))
        and "legacy" not in o.package
        and "tesla" not in o.package
    ]
    current = max((_series(o.package) for o in numbered if o.installed), default=0)
    if not current:
        return 0, 0
    newer = max((_series(o.package) for o in numbered if _series(o.package) > current), default=0)
    return current, newer


# --- Sürücü değişikliği geçmişi ("Önceki sürücüye dön") ---


def _changes_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "linwas" / "driver_changes.json"


@dataclass
class DriverChange:
    device: str  # aygıt adı (lspci)
    previous: str  # önceki paket ("" = açık kaynak)
    new: str
    time: str = ""


def load_changes() -> list[DriverChange]:
    try:
        data = json.loads(_changes_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    known = DriverChange.__dataclass_fields__
    return [
        DriverChange(**{k: v for k, v in d.items() if k in known})
        for d in data
        if isinstance(d, dict) and "device" in d
    ]


def record_change(device: str, previous: str, new: str) -> None:
    changes = load_changes()[-49:]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    changes.append(DriverChange(device, previous, new, now))
    path = _changes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(c) for c in changes], indent=2), encoding="utf-8")


def last_change(device: str) -> DriverChange | None:
    return next((c for c in reversed(load_changes()) if c.device == device), None)


# --- Secure Boot ---


def secure_boot_enabled() -> bool:
    _, out = _run(["mokutil", "--sb-state"], timeout=10)
    return "SecureBoot enabled" in out


def mok_key() -> Path | None:
    return next((p for p in MOK_KEYS if p.is_file()), None)


def mok_enrolled(key: Path | None = None) -> bool | None:
    """Anahtar kayıtlı mı (anahtar yoksa ya da okunamazsa None)."""
    key = key or mok_key()
    if key is None:
        return None
    _, out = _run(["mokutil", "--test-key", str(key)], timeout=10)
    if "is already enrolled" in out:
        return True
    if "is not enrolled" in out:
        return False
    return None


def new_mok_password() -> str:
    """Yeniden başlatmada yazılacak 8 haneli tek kullanımlık şifre."""
    return "".join(secrets.choice("0123456789") for _ in range(8))
