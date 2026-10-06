"""Sorun Giderme: tek tıkla tarama (salt okunur, root gerekmez).

Her kontrol bir CheckResult döner; arayüz sorunlu olanları çözüm düğmeleriyle gösterir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class CheckResult:
    id: str  # "disk", "internet", "packages", "services", "sound", "printing", "updates"
    ok: bool
    detail: str = ""  # teknik ayrıntı (İngilizce/ham); arayüz başlığı kendisi çevirir


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C", "LC_ALL": "C"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def check_disk(path: str = "/", min_free_ratio: float = 0.1) -> CheckResult:
    usage = shutil.disk_usage(path)
    free_gb = usage.free / 1024**3
    ok = usage.free / usage.total >= min_free_ratio and free_gb >= 2
    return CheckResult("disk", ok, f"{free_gb:.1f} GB free")


def check_internet() -> CheckResult:
    # nmcli networking connectivity: none / portal / limited / full / unknown
    code, out = _run(["nmcli", "networking", "connectivity", "check"])
    if code == 127:
        return CheckResult("internet", True, "nmcli not available")
    return CheckResult("internet", out.strip() == "full", out.strip())


def check_packages() -> CheckResult:
    # dpkg --audit yarım kalmış/bozuk paketleri listeler; çıktı boşsa sorun yok
    code, out = _run(["dpkg", "--audit"])
    return CheckResult("packages", code == 0 and not out, out[:300])


def check_services() -> CheckResult:
    code, out = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    units = [line.split()[0] for line in out.splitlines() if line.strip()]
    return CheckResult("services", code == 0 and not units, ", ".join(units[:5]))


def check_sound() -> CheckResult:
    # PipeWire/PulseAudio sunucusu yanıt veriyor mu
    code, out = _run(["pactl", "info"])
    if code == 127:
        return CheckResult("sound", True, "pactl not available")
    return CheckResult("sound", code == 0, "" if code == 0 else out[:200])


def check_printing() -> CheckResult:
    code, out = _run(["systemctl", "is-active", "cups"])
    if out in ("inactive", "unknown") and code != 0:
        # CUPS kurulu değil ya da soket ile isteğe bağlı başlıyor: sorun sayılmaz
        return CheckResult("printing", True, out)
    return CheckResult("printing", out == "active", out)


def check_updates() -> CheckResult:
    from linwas.backend.packages import count_upgradable

    total, security = count_upgradable()
    return CheckResult("updates", security == 0, f"{total} updates, {security} security")


CHECKS: tuple[Callable[[], CheckResult], ...] = (
    check_internet,
    check_disk,
    check_packages,
    check_services,
    check_sound,
    check_printing,
    check_updates,
)


def run_all() -> list[CheckResult]:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # bir kontrolün hatası taramayı durdurmasın
            results.append(CheckResult(check.__name__.removeprefix("check_"), True, str(exc)))
    return results


def restart_sound() -> bool:
    """Kullanıcı ses servislerini yeniden başlatır (systemd --user, root gerekmez)."""
    return (
        _run(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"])[0]
        == 0
    )
