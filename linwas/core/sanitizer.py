# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Hassas verileri maskeleme: API anahtarları, şifreler, URL parametreleri.

Loglar ve hata raporları kullanıcıya gösterilmeden veya AI'a gönderilmeden önce
bu modülden geçirilir.
"""

from __future__ import annotations

import re

# (desen, değiştirme) çiftleri; sırayla uygulanır
_RULES: list[tuple[re.Pattern[str], str]] = [
    # Bearer token: "Authorization: Bearer <token>" veya "Bearer <token>"
    (
        re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
        r"\1[MASKED]",
    ),
    # API anahtarı anahtar=değer kalıpları (key, token, secret, apikey...)
    (
        re.compile(
            r"((?:api[_\-]?key|api[_\-]?secret|access[_\-]?token|secret[_\-]?key"
            r"|auth[_\-]?token|password|passwd|pwd)\s*[=:]\s*)[^\s&\"']+",
            re.IGNORECASE,
        ),
        r"\1[MASKED]",
    ),
    # URL'de ?key= veya &key= parametresi (Gemini API imzası için)
    (
        re.compile(r"([?&]key=)[^&\s\"']+", re.IGNORECASE),
        r"\1[MASKED]",
    ),
    # Authorization başlığı değeri
    (
        re.compile(r"(Authorization:\s*)[^\r\n]+", re.IGNORECASE),
        r"\1[MASKED]",
    ),
    # JSON içinde "key": "value" kalıbı (API anahtar alanları için)
    (
        re.compile(
            r'("(?:api_key|apiKey|api_secret|access_token|secret_key'
            r'|auth_token|password|passwd)"\s*:\s*")[^"]+(")',
            re.IGNORECASE,
        ),
        r"\1[MASKED]\2",
    ),
]


# Kişisel bilgiler (hata raporu ve AI'a giden metinler için)
_RULES += [
    # Ev klasörü yolundaki kullanıcı adı
    (re.compile(r"(/home/|/run/media/|/media/)[^/\s'\"]+"), r"\1[USER]"),
    # E-posta adresi
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # MAC adresi
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"), "[MAC]"),
    # IPv4 adresi (127.0.0.1 hariç)
    (re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
]


def _identity_words() -> list[str]:
    """O anki kullanıcı adı ve bilgisayar adı (kısa, sık kelimeye benzeyenler hariç)."""
    import getpass
    import socket

    words = []
    for get in (getpass.getuser, socket.gethostname):
        try:
            value = get()
        except Exception:
            continue
        if value and len(value) >= 3 and value.lower() not in ("root", "localhost", "user"):
            words.append(value)
    return words


def sanitize(text: str) -> str:
    """Metindeki hassas verileri maskeler ve temizlenmiş metni döner."""
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    for word in _identity_words():
        text = re.sub(rf"\b{re.escape(word)}\b", "[USER]", text)
    return text
