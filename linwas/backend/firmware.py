# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Firmware (fwupd) ayrıntıları: aygıtlar, güncellemeler, sürüm notları, geçmiş (salt okunur).

`fwupdmgr get-devices|get-updates|get-history --json` kullanıcı yetkisiyle okunur. Güncelleme ve
bilgi yenileme root helper işlemleriyle yapılır (`firmware.refresh`, `firmware.update_device`).
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field


def available() -> bool:
    return shutil.which("fwupdmgr") is not None


def _json(args: list[str], timeout: int = 60) -> dict:
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        r = subprocess.run(
            ["fwupdmgr", *args, "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def plain_text(markup: str) -> str:
    """fwupd sürüm notları (basit HTML: <p>, <li>) → düz metin."""
    text = re.sub(r"<li>", "• ", markup or "")
    text = re.sub(r"</(p|li|ul|ol)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [html.unescape(x).strip() for x in text.splitlines()]
    return "\n".join(x for x in lines if x)


@dataclass
class Release:
    version: str
    summary: str = ""
    notes: str = ""
    urgency: str = ""  # "low" | "medium" | "high" | "critical" | ""


@dataclass
class FirmwareDevice:
    device_id: str
    name: str
    vendor: str = ""
    version: str = ""
    flags: list[str] = field(default_factory=list)
    update_error: str = ""
    releases: list[Release] = field(default_factory=list)  # yalnızca güncellemelerde

    @property
    def updatable(self) -> bool:
        return "updatable" in self.flags or "updatable-hidden" in self.flags

    @property
    def needs_reboot(self) -> bool:
        return "needs-reboot" in self.flags

    @property
    def requires_ac(self) -> bool:
        return "require-ac" in self.flags


def _device(raw: dict) -> FirmwareDevice | None:
    if not isinstance(raw, dict) or not raw.get("DeviceId") or not raw.get("Name"):
        return None
    releases = []
    for rel in raw.get("Releases") or []:
        if isinstance(rel, dict) and rel.get("Version"):
            releases.append(
                Release(
                    version=str(rel["Version"]),
                    summary=str(rel.get("Summary") or ""),
                    notes=plain_text(str(rel.get("Description") or "")),
                    urgency=str(rel.get("Urgency") or ""),
                )
            )
    return FirmwareDevice(
        device_id=str(raw["DeviceId"]),
        name=str(raw["Name"]),
        vendor=str(raw.get("Vendor") or ""),
        version=str(raw.get("Version") or ""),
        flags=[str(f) for f in raw.get("Flags") or []],
        update_error=str(raw.get("UpdateError") or ""),
        releases=releases,
    )


def parse_devices(data: dict) -> list[FirmwareDevice]:
    return [d for d in (_device(x) for x in data.get("Devices") or []) if d]


def list_devices() -> list[FirmwareDevice]:
    """Sürümü bilinen aygıtlar (güncellenebilir olanlar önce)."""
    devices = [d for d in parse_devices(_json(["get-devices"])) if d.version]
    return sorted(devices, key=lambda d: (not d.updatable, d.name.lower()))


def list_updates() -> list[FirmwareDevice]:
    """Güncellemesi olan aygıtlar; `releases[0]` en yeni sürüm."""
    return [d for d in parse_devices(_json(["get-updates"])) if d.releases]


def list_history() -> list[FirmwareDevice]:
    """Daha önce yapılan firmware güncellemeleri (yoksa boş liste)."""
    return parse_devices(_json(["get-history"]))
