"""Sürücü sağlık kontrolü (salt okunur, root gerekmez; yalnızca "Denetle" ile çalışır).

Kurulu sürücü gerçekten çalışıyor mu:
- NVIDIA: paket kurulu ama modül yüklü değil (DKMS derlenmemiş, Secure Boot anahtarı,
  yeniden başlatma bekleniyor, nouveau hâlâ yüklü); yüklü modül ile kurulu modül sürümü
  farklı (güncellemeden sonra yeniden başlatılmamış).
- DKMS: bir modül çalışan çekirdek için kurulmamış (çoğunlukla çekirdek başlık paketi eksik).
- Çizim: masaüstünü hangi kartın çizdiği (`glxinfo -B`); yazılımla çizim (llvmpipe) sorun.

Modül adları dağıtıma göre değişir: Ubuntu `nvidia`, Debian/Pardus DKMS `nvidia-current`
(yüklenince yine `nvidia` adıyla görünür). `dkms` ve `modinfo` /usr/sbin altındadır.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from linwas.backend.devices import Device

SYS_MODULE = Path("/sys/module")
_SBIN = ("/usr/sbin", "/sbin")
_NVIDIA_MODULES = ("nvidia", "nvidia-current")
_SOFTWARE_RENDERERS = ("llvmpipe", "softpipe", "swrast")


@dataclass
class HealthItem:
    key: str  # kimlik (arayüz metni buna göre seçilir)
    ok: bool
    # Düzeltme: "" | "reboot" | "rebuild_modules" | "secure_boot" | "ask_ai"
    fix: str = ""
    # Metne eklenecek değerler (sürüm, çizen kart adı, modül listesi…)
    values: dict[str, str] = field(default_factory=dict)
    # Düzeltmede kurulacak paket (ör. çekirdek başlıkları); boşsa yok
    package: str = ""


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for d in _SBIN:
        path = os.path.join(d, name)
        if os.access(path, os.X_OK):
            return path
    return ""


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout


# --- Ayrıştırıcılar (birim testleri için ayrı) ---


def parse_dkms_status(out: str) -> list[tuple[str, str, str]]:
    """`dkms status` → [(modül, çekirdek, durum)].

    Biçimler: "nvidia-current/535.261.03, 6.1.0-48-amd64, x86_64: installed" (dkms 3) ve
    "nvidia, 535.183, 5.15.0-1-generic, x86_64: installed" (eski dkms).
    Çekirdeksiz satır ("…: added") çekirdeği boş döner.
    """
    result = []
    for line in out.splitlines():
        left, sep, status = line.rpartition(":")
        if not sep:
            continue
        parts = [p.strip() for p in left.split(",")]
        if not parts or not parts[0]:
            continue
        module = parts[0].split("/")[0]
        kernel = ""
        for p in parts[1:]:
            if re.match(r"^\d+\.\d+", p) and "-" in p:
                kernel = p
                break
        result.append((module, kernel, status.strip().split(" ")[0]))
    return result


def parse_renderer(out: str) -> str:
    """`glxinfo -B` → "OpenGL renderer string" değeri."""
    m = re.search(r"OpenGL renderer string:\s*(.+)", out)
    return m.group(1).strip() if m else ""


# --- Denetimler ---


def _module_loaded(name: str) -> bool:
    return (SYS_MODULE / name).is_dir()


def _loaded_version(name: str) -> str:
    try:
        return (SYS_MODULE / name / "version").read_text().strip()
    except OSError:
        return ""


def _installed_nvidia_version() -> str:
    """Çalışan çekirdek için kurulu NVIDIA modülünün sürümü; yoksa ""."""
    modinfo = _tool("modinfo")
    if not modinfo:
        return ""
    for name in _NVIDIA_MODULES:
        code, out = _run([modinfo, "-F", "version", name])
        if code == 0 and out.strip():
            return out.strip()
    return ""


def _nvidia_package_installed() -> bool:
    # Ubuntu nvidia-driver-<n>, Debian/Pardus nvidia-driver (+ tesla/legacy sürümleri)
    code, out = _run(["dpkg-query", "-W", "-f=${Package} ${Status}\n", "nvidia-*driver*"])
    return any(line.endswith("install ok installed") for line in out.splitlines())


def headers_package() -> str:
    """Çalışan çekirdeğin başlık paketi adı (Debian ve Ubuntu: linux-headers-<uname -r>)."""
    return f"linux-headers-{os.uname().release}"


def _package_installed(pkg: str) -> bool:
    code, out = _run(["dpkg-query", "-W", "-f=${Status}", pkg], timeout=5)
    return "install ok installed" in out


def _package_available(pkg: str) -> bool:
    code, out = _run(["apt-cache", "policy", pkg])
    m = re.search(r"Candidate:\s*(\S+)", out)
    return bool(m and m.group(1) != "(none)")


def check_dkms() -> HealthItem | None:
    dkms = _tool("dkms")
    if not dkms:
        return None
    code, out = _run([dkms, "status"], timeout=30)
    entries = parse_dkms_status(out)
    if not entries:
        return None
    running = os.uname().release
    modules = sorted({m for m, _, _ in entries})
    missing = [
        m
        for m in modules
        if not any(mm == m and k == running and s == "installed" for mm, k, s in entries)
    ]
    if not missing:
        return HealthItem("dkms_ok", True, values={"modules": ", ".join(modules)})
    pkg = headers_package()
    need_headers = not _package_installed(pkg) and _package_available(pkg)
    return HealthItem(
        "dkms_missing",
        False,
        fix="rebuild_modules",
        values={"modules": ", ".join(missing), "kernel": running},
        package=pkg if need_headers else "",
    )


def check_nvidia(devices: list[Device], secure_boot: bool, mok: bool | None) -> HealthItem | None:
    has_nvidia = any(d.group == "display" and d.vendor == "10de" for d in devices)
    if not has_nvidia or not _nvidia_package_installed():
        return None
    installed = _installed_nvidia_version()
    if _module_loaded("nvidia"):
        loaded = _loaded_version("nvidia")
        if installed and loaded and installed != loaded:
            return HealthItem(
                "nvidia_mismatch",
                False,
                fix="reboot",
                values={"loaded": loaded, "installed": installed},
            )
        return HealthItem("nvidia_ok", True, values={"version": loaded or installed})
    # Paket kurulu, modül yüklü değil
    if not installed:
        return None  # DKMS denetimi aynı sorunu düzeltmesiyle birlikte gösterir
    if secure_boot and mok is False:
        return HealthItem("nvidia_secure_boot", False, fix="secure_boot")
    if _module_loaded("nouveau"):
        return HealthItem("nvidia_nouveau", False, fix="reboot")
    return HealthItem("nvidia_not_loaded", False, fix="reboot", values={"version": installed})


def check_renderer() -> HealthItem | None:
    glxinfo = _tool("glxinfo")
    if not glxinfo or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    code, out = _run([glxinfo, "-B"])
    renderer = parse_renderer(out)
    if not renderer:
        return None
    if any(s in renderer.lower() for s in _SOFTWARE_RENDERERS):
        return HealthItem("render_software", False, fix="ask_ai", values={"renderer": renderer})
    return HealthItem("render_ok", True, values={"renderer": renderer})


def check_all(devices: list[Device], secure_boot: bool, mok: bool | None) -> list[HealthItem]:
    """Bütün denetimler; sorunlar önce."""
    items = [
        check_nvidia(devices, secure_boot, mok),
        check_dkms(),
        check_renderer(),
    ]
    found = [i for i in items if i is not None]
    return sorted(found, key=lambda i: i.ok)
