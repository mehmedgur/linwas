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


def sanitize(text: str) -> str:
    """Metindeki hassas verileri maskeler ve temizlenmiş metni döner."""
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
