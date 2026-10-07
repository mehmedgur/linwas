"""Masaüstü bildirimleri (freedesktop Notifications D-Bus arayüzü, `gdbus` ile; kabuksuz).

Gönderme `gdbus call … Notify` (gdbus(1) belgesindeki örnekle aynı biçim); bildirimdeki
düğmeye basılması `gdbus monitor` çıktısındaki ActionInvoked sinyalinden okunur.
Argümanlar GVariant metni olarak verilir; dizeler tırnaklanıp kaçırılır.
"""

from __future__ import annotations

import re
import shutil

DEST = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"


def available() -> bool:
    return shutil.which("gdbus") is not None


def gvariant_string(text: str) -> str:
    """Python dizesi → GVariant dize sabiti ('…', ters eğik çizgi ve tırnak kaçırılır)."""
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def notify_command(
    summary: str,
    body: str,
    actions: list[tuple[str, str]] | None = None,
    icon: str = "linwas",
    timeout_ms: int = -1,
) -> list[str]:
    """Notify çağrısı; `actions`: [(anahtar, düğme metni)] ("default" = bildirime tıklama)."""
    flat = []
    for key, label in actions or []:
        flat += [gvariant_string(key), gvariant_string(label)]
    return [
        "gdbus",
        "call",
        "--session",
        "--dest",
        DEST,
        "--object-path",
        PATH,
        "--method",
        f"{DEST}.Notify",
        gvariant_string("Linwas"),
        "uint32 0",
        gvariant_string(icon),
        gvariant_string(summary),
        gvariant_string(body),
        f"@as [{', '.join(flat)}]",
        "@a{sv} {}",
        str(int(timeout_ms)),
    ]


def monitor_command() -> list[str]:
    return ["gdbus", "monitor", "--session", "--dest", DEST]


def parse_notify_id(out: str) -> int:
    """`(uint32 7,)` → 7 (okunamazsa 0)."""
    m = re.search(r"uint32\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def parse_action(line: str) -> tuple[int, str] | None:
    """`… ActionInvoked (uint32 7, 'default')` → (7, "default")."""
    m = re.search(r"ActionInvoked \(uint32 (\d+), '([^']*)'\)", line)
    return (int(m.group(1)), m.group(2)) if m else None
