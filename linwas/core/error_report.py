# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Hata raporu: maskelenmiş rapor metni ve GitHub issue bağlantısı.

Rapor kişisel bilgi içermesin diye her parça sanitizer'dan geçer.
"""

from __future__ import annotations

import urllib.parse

from linwas import __homepage__
from linwas.core.sanitizer import sanitize

# Herkese açık yayın yeri henüz kararlaştırılmadı (bkz. karar belgesi › Açık konular);
# değişirse yalnızca linwas/__init__.py'deki __homepage__ güncellenir.
ISSUES_URL = f"{__homepage__}/issues/new"

# Tarayıcı/GitHub için güvenli URL uzunluğu
_MAX_BODY = 6000


def build_report(
    error: str,
    task_labels: list[str],
    version: str,
    system: str,
    desktop: str,
) -> str:
    lines = [
        "## Linwas",
        f"- Version: {version}",
        f"- System: {system}",
        f"- Desktop: {desktop}",
        "",
        "## Tasks",
        *[f"- {label}" for label in task_labels],
        "",
        "## Error",
        "```",
        error.strip() or "(no message)",
        "```",
    ]
    return sanitize("\n".join(lines))


def issue_url(title: str, body: str, base: str = ISSUES_URL) -> str:
    if len(body) > _MAX_BODY:
        body = body[:_MAX_BODY] + "\n…(truncated, attach the saved report)"
    query = urllib.parse.urlencode({"title": sanitize(title), "body": body})
    return f"{base}?{query}"
