"""Dosya türleri için varsayılan uygulama: çift tıklanan .deb paketi Linwas'ta açılsın.

Kullanıcıya özel (`xdg-mime`, ~/.config/mimeapps.list; root gerekmez). Önceki varsayılan uygulama
ayarlara yazılır; kullanıcı Ayarlar'dan kapatınca ona geri dönülür. Yalnızca paket kuruluysa
(masaüstü dosyası varsa) yapılır.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

INSTALLED_DESKTOP_FILE = Path("/usr/share/applications/linwas.desktop")
LINWAS_DESKTOP_ID = INSTALLED_DESKTOP_FILE.name
# shared-mime-info: asıl tür ve eski adları
DEB_MIME_TYPES = (
    "application/vnd.debian.binary-package",
    "application/x-deb",
    "application/x-debian-package",
)
_RE_DESKTOP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.desktop$")


def valid_desktop_id(value: str) -> bool:
    return bool(_RE_DESKTOP_ID.match(value))


def _xdg_mime(*args: str) -> tuple[int, str]:
    if not shutil.which("xdg-mime"):
        return 127, ""
    try:
        r = subprocess.run(
            ["xdg-mime", *args], capture_output=True, text=True, timeout=15, shell=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout.strip()


def default_for(mime: str) -> str:
    """Bu türün şu anki varsayılan uygulaması (masaüstü dosyası adı); yoksa ""."""
    code, out = _xdg_mime("query", "default", mime)
    return out if code == 0 and valid_desktop_id(out) else ""


def linwas_opens_debs() -> bool:
    return default_for(DEB_MIME_TYPES[0]) == LINWAS_DESKTOP_ID


def make_linwas_deb_handler() -> tuple[bool, str]:
    """Linwas'ı .deb için varsayılan yapar. (başarılı mı, önceki uygulama) döner."""
    if not INSTALLED_DESKTOP_FILE.is_file():
        return False, ""
    previous = default_for(DEB_MIME_TYPES[0])
    if previous == LINWAS_DESKTOP_ID:
        previous = ""
    code, _ = _xdg_mime("default", LINWAS_DESKTOP_ID, *DEB_MIME_TYPES)
    return code == 0, previous


def restore_deb_handler(previous: str) -> bool:
    """Önceki varsayılan uygulamaya döner; bilinmiyorsa sistemin seçimine bırakılır."""
    if previous and valid_desktop_id(previous):
        return _xdg_mime("default", previous, *DEB_MIME_TYPES)[0] == 0
    return _remove_user_default(DEB_MIME_TYPES)


def _mimeapps_list() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "mimeapps.list"


def _remove_user_default(mimes: tuple[str, ...]) -> bool:
    """Kullanıcının mimeapps.list'inde [Default Applications] altındaki Linwas satırlarını siler
    (xdg-mime'da "varsayılanı kaldır" komutu yok)."""
    path = _mimeapps_list()
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return True
    out, section = [], ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
        key, sep, value = stripped.partition("=")
        if (
            section == "[Default Applications]"
            and sep
            and key in mimes
            and value.split(";")[0] == LINWAS_DESKTOP_ID
        ):
            continue
        out.append(line)
    try:
        path.write_text("".join(out), encoding="utf-8")
    except OSError:
        return False
    return True
