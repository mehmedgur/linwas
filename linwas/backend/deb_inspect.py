# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
""".deb risk analizi (kurulmadan önce, root gerekmez).

`dpkg-deb -f` (kontrol alanları), `-I` (bakımcı betikleri) ve `-c` (dosya listesi)
ile paketin ne yapacağı çıkarılır. Sonuç sade dille gösterilir; kurulum yine
kuyruk + onay üzerinden root helper ile yapılır (deb.install).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Kurulumda root olarak çalışan bakımcı betikleri
_SCRIPTS = ("preinst", "postinst", "prerm", "postrm")

# Dosya yolu → risk nedeni (önek eşleşmesi; yollar "./" olmadan)
_PATH_REASONS: tuple[tuple[str, str], ...] = (
    ("etc/apt/sources.list.d/", "repo"),
    ("etc/apt/trusted.gpg", "repo"),
    ("usr/share/keyrings/", "repo"),
    ("etc/sudoers", "sensitive"),
    ("etc/cron", "sensitive"),
    ("etc/pam.d/", "sensitive"),
    ("etc/security/", "sensitive"),
    ("boot/", "sensitive"),
    ("lib/modules/", "sensitive"),
    ("usr/lib/modules/", "sensitive"),
    ("root/", "sensitive"),
    ("home/", "sensitive"),
    ("etc/systemd/system/", "service"),
    ("lib/systemd/system/", "service"),
    ("usr/lib/systemd/system/", "service"),
)

HIGH_REASONS = {"repo", "sensitive", "arch"}
MEDIUM_REASONS = {"scripts", "service"}


@dataclass
class DebInfo:
    path: str
    package: str = ""
    version: str = ""
    architecture: str = ""
    maintainer: str = ""
    description: str = ""
    depends: str = ""
    scripts: list[str] = field(default_factory=list)
    file_count: int = 0
    flagged_files: dict[str, list[str]] = field(default_factory=dict)  # neden → yollar
    reasons: list[str] = field(default_factory=list)  # "scripts", "repo", "service"...
    installed_version: str = ""
    repo_version: str = ""  # aynı paket depoda varsa aday sürüm
    error: str = ""

    @property
    def risk(self) -> str:
        """ "high" | "medium" | "low"."""
        if HIGH_REASONS & set(self.reasons):
            return "high"
        if MEDIUM_REASONS & set(self.reasons):
            return "medium"
        return "low"


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False, env=env
        )
        return r.returncode, r.stdout if r.returncode == 0 else r.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def parse_fields(text: str) -> dict[str, str]:
    """`dpkg-deb -f` çıktısı (RFC822 biçimi; devam satırları birleştirilir)."""
    fields: dict[str, str] = {}
    key = ""
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and key:
            fields[key] += "\n" + line.strip()
        elif ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            fields[key] = value.strip()
    return fields


def parse_info_scripts(text: str) -> list[str]:
    """`dpkg-deb -I` çıktısındaki kontrol arşivi üyelerinden bakımcı betikleri."""
    found = []
    for line in text.splitlines():
        parts = line.split()
        # " 1234 bytes,    20 lines   *  postinst   #!/bin/sh"
        for name in _SCRIPTS:
            if name in parts and name not in found:
                found.append(name)
    return found


def parse_contents(text: str) -> list[str]:
    """`dpkg-deb -c` (tar listesi) → dosya yolları ("./" olmadan, klasörler hariç)."""
    paths = []
    for line in text.splitlines():
        m = re.match(r"^\S+\s+\S+\s+\d+\s+\S+\s+\S+\s+\.?/?(.*?)(?: -> .*)?$", line)
        if m and m.group(1) and not m.group(1).endswith("/"):
            paths.append(m.group(1))
    return paths


def flag_paths(paths: list[str]) -> dict[str, list[str]]:
    flagged: dict[str, list[str]] = {}
    for path in paths:
        for prefix, reason in _PATH_REASONS:
            if path.startswith(prefix):
                flagged.setdefault(reason, []).append("/" + path)
                break
    return flagged


def _policy_candidate(package: str) -> tuple[str, str]:
    """(kurulu sürüm, depodaki aday sürüm); yoksa boş."""
    code, out = _run(["apt-cache", "policy", "--", package], timeout=30)
    if code != 0:
        return "", ""
    installed = candidate = ""
    for line in out.splitlines():
        key, _, value = line.strip().partition(":")
        if key == "Installed" and value.strip() != "(none)":
            installed = value.strip()
        elif key == "Candidate" and value.strip() != "(none)":
            candidate = value.strip()
    return installed, candidate


def inspect(path: str | Path) -> DebInfo:
    info = DebInfo(path=str(path))
    p = Path(path)
    if p.suffix != ".deb" or not p.is_file():
        info.error = "not a .deb file"
        return info

    code, out = _run(["dpkg-deb", "-f", str(p)])
    if code != 0:
        info.error = out.strip() or "dpkg-deb failed"
        return info
    f = parse_fields(out)
    info.package = f.get("Package", "")
    info.version = f.get("Version", "")
    info.architecture = f.get("Architecture", "")
    info.maintainer = f.get("Maintainer", "")
    info.description = f.get("Description", "").split("\n", 1)[0]
    info.depends = ", ".join(x for x in (f.get("Pre-Depends", ""), f.get("Depends", "")) if x)

    info.scripts = parse_info_scripts(_run(["dpkg-deb", "-I", str(p)])[1])
    paths = parse_contents(_run(["dpkg-deb", "-c", str(p)])[1])
    info.file_count = len(paths)
    info.flagged_files = flag_paths(paths)

    reasons = list(info.flagged_files)
    if info.scripts:
        reasons.append("scripts")
    native = _run(["dpkg", "--print-architecture"])[1].strip()
    if info.architecture not in ("all", native, ""):
        reasons.append("arch")
    info.reasons = reasons

    if info.package:
        info.installed_version, info.repo_version = _policy_candidate(info.package)
    return info
