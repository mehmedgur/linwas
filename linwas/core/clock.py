"""Sistem saatinin doğru kalması (Windows ile çift açılış).

Windows anakart saatini (RTC) yerel saatte tutar. Linux uykudan uyanınca çekirdek RTC'yi UTC
sanar ve saat, saat dilimi farkı kadar (Türkiye'de 3 saat) kayar. Chrony'nin Debian varsayılanı
`makestep 1 3` saati yalnız açılıştaki ilk üç güncellemede atlatır; sonradan oluşan büyük farkı
haftalarca eritir.

Linwas üç yerden düzeltir (kararlar.md › Saat):
- güç servisi her açılışta `ensure()` çağırır: chrony ayarı yoksa yazar, saati eşitler;
- uyku kancası (packaging/linwas-clock-sleep.sh) uyanınca RTC'yi doğru saat ölçeğiyle okur;
- Sorun giderme'deki "Saati düzelt" root işlemi `clock.fix` aynı `ensure()`'i çalıştırır.

Qt'ye bağımlı değil; root yardımcısı ve güç servisi de kullanır.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

CHRONY_CONF = Path("/etc/chrony/conf.d/linwas-step.conf")
CHRONY_TEXT = (
    "# Linwas: büyük saat farkını (ör. uykudan uyanınca) her zaman hemen düzelt.\n"
    "# Silinirse Linwas güç servisi bir sonraki açılışta yeniden yazar.\n"
    "makestep 1 -1\n"
)
# Bu kadar saniyeden fazla sapma "saat yanlış" sayılır
WRONG_SECONDS = 60
_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=_ENV
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, ""
    return r.returncode, r.stdout


def parse_chrony_offset(out: str) -> float | None:
    """`chronyc tracking` → saniye (ileri +, geri −); okunamazsa None."""
    m = re.search(r"System time\s*:\s*([\d.]+) seconds (fast|slow)", out)
    if not m:
        return None
    value = float(m.group(1))
    return value if m.group(2) == "fast" else -value


def offset_seconds() -> float | None:
    """Saatin gerçek saatten farkı (chrony varsa); bilinmiyorsa None. Kullanıcı yetkisi yeter."""
    if not shutil.which("chronyc", path=_ENV["PATH"]):
        return None
    code, out = _run(["chronyc", "tracking"], timeout=10)
    return parse_chrony_offset(out) if code == 0 else None


def local_rtc() -> bool:
    code, out = _run(["timedatectl", "show", "-p", "LocalRTC", "--value"], timeout=10)
    return code == 0 and out.strip() == "yes"


# --- root gerektirenler (güç servisi, root yardımcısı) ---


def write_chrony_conf() -> bool:
    """Ayar dosyası yoksa ya da farklıysa yazar; değiştiyse True (chrony yeniden başlatılmalı)."""
    try:
        if CHRONY_CONF.read_text(encoding="utf-8") == CHRONY_TEXT:
            return False
    except OSError:
        pass
    CHRONY_CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHRONY_CONF.with_name(CHRONY_CONF.name + ".linwas-tmp")
    tmp.write_text(CHRONY_TEXT, encoding="utf-8")
    tmp.chmod(0o644)
    os.replace(tmp, CHRONY_CONF)
    return True


def ensure(wait_sync: bool = False) -> list[str]:
    """Saati doğru tutacak ayarı yapar ve saati eşitler. Yapılanların listesi döner (günlük için).

    Chrony varsa: ayar dosyası + gerekirse yeniden başlatma + `makestep`. Yoksa (Ubuntu'daki
    systemd-timesyncd): ağdan eşitleme açılır ve servis yeniden başlatılır (büyük farkı kendisi
    atlatır).
    """
    done: list[str] = []
    if shutil.which("chronyc", path=_ENV["PATH"]) and Path("/etc/chrony").is_dir():
        if write_chrony_conf():
            _run(["systemctl", "restart", "chrony"])
            done.append("chrony: makestep 1 -1")
        if wait_sync:
            # en çok ~30 sn: kaynak ölçümü gelince ayar gereği saat kendiliğinden atlar
            _run(["chronyc", "waitsync", "30", "1", "0", "1"], timeout=45)
        _run(["chronyc", "-a", "makestep"])
        done.append("chrony: makestep")
    elif shutil.which("timedatectl", path=_ENV["PATH"]):
        _run(["timedatectl", "set-ntp", "true"])
        _run(["systemctl", "restart", "systemd-timesyncd"])
        done.append("timesyncd: restart")
    return done
