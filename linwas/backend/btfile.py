# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Bluetooth ile dosya gönderme: masaüstünün kendi aracını başlatır. Qt'ye bağımlı değildir.

Aktarımı aracın kendi penceresi gösterir (karşı cihazda kabul gerekir); Linwas yalnızca aracı doğru
adres ve dosyalarla başlatır. Komut satırları araçların kaynak kodundan doğrulandı:
- GNOME: `bluetooth-sendto --device=ADRES DOSYA...` (gnome-bluetooth, sendto/main.c);
  Ubuntu 22.04'te `gnome-bluetooth` paketinde, 24.04'te `gnome-bluetooth-sendto` paketinde.
- Blueman: `blueman-sendto --device ADRES DOSYA...` (apps/blueman-sendto); `blueman` paketinde.
Dosya adları `--` sonrasına konur: "-" ile başlayan ad seçenek sayılmasın.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable

from linwas.backend import network

# Sırayla aranır; ilk bulunan kullanılır
TOOLS = ("bluetooth-sendto", "blueman-sendto")
# Dosya alabilen cihaz türleri (BlueZ "Icon" alanı); kulaklık, fare vb. dosya almaz
RECEIVER_ICONS = ("phone", "computer")


def available_tool() -> str | None:
    return next((tool for tool in TOOLS if shutil.which(tool)), None)


def can_receive(icon: str) -> bool:
    return icon in RECEIVER_ICONS


def valid_files(paths: Iterable[str]) -> list[str]:
    """Mutlak yollu, var olan düzenli dosyalar; yinelenenler atılır (sıra korunur)."""
    seen: list[str] = []
    for path in paths:
        if os.path.isabs(path) and os.path.isfile(path) and path not in seen:
            seen.append(path)
    return seen


def send_command(tool: str, mac: str, files: list[str]) -> list[str]:
    if tool == "blueman-sendto":
        return [tool, "--device", mac, "--", *files]
    return [tool, f"--device={mac}", "--", *files]


def send(
    mac: str,
    paths: Iterable[str],
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> tuple[bool, str]:
    """Aracı başlatır; (başarılı, kod): invalid address, no files, no tool ya da hata iletisi."""
    if not network._valid_mac(mac):
        return False, "invalid address"
    files = valid_files(paths)
    if not files:
        return False, "no files"
    tool = available_tool()
    if tool is None:
        return False, "no tool"
    try:
        proc = popen(
            send_command(tool, mac, files),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        return False, str(exc)
    # Araç kendi penceresiyle ayrı çalışır; bitince hayalet süreç kalmasın diye arka planda beklenir
    threading.Thread(target=proc.wait, name="linwas-btsend", daemon=True).start()
    return True, ""
