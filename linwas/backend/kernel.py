# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Yeni donanım için yeni çekirdek önerisi (salt okunur).

- Ubuntu: HWE çekirdeği (`linux-generic-hwe-<sürüm>`, ör. linux-generic-hwe-22.04).
- Debian ve türevleri: depoda tanımlı `<kod adı>-backports` varsa oradaki daha yeni
  `linux-image-<mimari>`; kurulum root işlemi `kernel.install_backports` (`apt-get install -t`).
- Saf Debian'da backports tanımlı değilse resmi backports deposunu etkinleştirme önerilir
  (deb.debian.org; Debian arşiv anahtarı sistemde zaten var). Türevlerde (ör. Pardus) Debian
  deposu eklenmez.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEBIAN_MIRROR = "https://deb.debian.org/debian"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return r.returncode, r.stdout


def os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    fields = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                fields[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return fields


@dataclass
class KernelOffer:
    kind: str  # "hwe" | "backports" | "enable-backports"
    package: str
    version: str = ""
    suite: str = ""  # backports kod adı (ör. bookworm-backports)
    source_line: str = ""  # enable-backports için eklenecek depo satırı


@dataclass
class PolicyVersion:
    version: str
    suites: list[str]


def parse_policy_table(out: str) -> tuple[str, list[PolicyVersion]]:
    """`apt-cache policy <paket>` → (kurulu sürüm, [sürüm + geldiği suite'ler])."""
    installed = ""
    versions: list[PolicyVersion] = []
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Installed:"):
            value = stripped.split(":", 1)[1].strip()
            installed = "" if value == "(none)" else value
            continue
        # Sürüm satırı öncelikle biter ("     6.1.187-1 500", " *** 6.1.172-1 100")
        m = re.match(r"^\s+(?:\*\*\*\s+)?(\S+)\s+-?\d+$", line)
        if m:
            versions.append(PolicyVersion(m.group(1), []))
            continue
        # Kaynak satırı: "        500 http://adres suite/bileşen mimari Packages"
        m = re.match(r"^\s+-?\d+\s+\S+\s+(\S+?)/", line)
        if m and versions:
            versions[-1].suites.append(m.group(1))
    return installed, versions


def _newer(a: str, b: str) -> bool:
    if not b:
        return True
    code, _ = _run(["dpkg", "--compare-versions", a, "gt", b], timeout=10)
    return code == 0


def kernel_offer() -> KernelOffer | None:
    info = os_release()
    distro = info.get("ID", "")
    if distro == "ubuntu":
        package = f"linux-generic-hwe-{info.get('VERSION_ID', '')}"
        _, out = _run(["apt-cache", "policy", "--", package])
        installed, versions = parse_policy_table(out)
        if versions and not installed:
            return KernelOffer("hwe", package, versions[0].version)
        return None

    _, arch = _run(["dpkg", "--print-architecture"], timeout=10)
    package = f"linux-image-{arch.strip() or 'amd64'}"
    _, out = _run(["apt-cache", "policy", "--", package])
    installed, versions = parse_policy_table(out)
    for v in versions:
        suite = next((s for s in v.suites if s.endswith("-backports")), "")
        if suite and _newer(v.version, installed):
            return KernelOffer("backports", package, v.version, suite)
    codename = info.get("VERSION_CODENAME", "")
    has_backports = any(s.endswith("-backports") for v in versions for s in v.suites)
    if distro == "debian" and codename and not has_backports:
        suite = f"{codename}-backports"
        line = f"deb {DEBIAN_MIRROR} {suite} main contrib non-free non-free-firmware"
        return KernelOffer("enable-backports", package, "", suite, line)
    return None
