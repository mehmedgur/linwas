# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Gemini sağlayıcısı.

Doğrudan Google Generative Language API kullanır (resmi SDK bağımlılığı yok).
Anahtar URL parametresiyle gönderilir; loglarda maskelenir.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from linwas.ai.base import AIError, AIProvider, AIResponse, Message, extract_task_suggestion
from linwas.core.sanitizer import sanitize

_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _url(path: str, api_key: str) -> str:
    """API anahtarını URL parametresi olarak ekler."""
    sep = "&" if "?" in path else "?"
    return f"{_BASE}/{path}{sep}key={api_key}"


def _get(path: str, api_key: str) -> dict[str, Any]:
    url = _url(path, api_key)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise AIError(f"HTTP {exc.code}: {sanitize(body[:300])}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Bağlantı hatası: {exc.reason}") from exc


def _post(path: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = _url(path, api_key)
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise AIError(f"HTTP {exc.code}: {sanitize(body[:300])}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Bağlantı hatası: {exc.reason}") from exc


class GeminiProvider(AIProvider):
    """Google Gemini sağlayıcısı."""

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Gemini"

    def list_models(self, api_key: str) -> list[str]:
        # Liste sayfalı gelir (models.list: pageSize, pageToken, nextPageToken)
        models: list[dict[str, Any]] = []
        token = ""
        for _ in range(20):  # sonsuz döngü koruması
            path = "models?pageSize=1000"
            if token:
                path += "&pageToken=" + urllib.parse.quote(token, safe="")
            data = _get(path, api_key)
            models.extend(data.get("models", []))
            token = data.get("nextPageToken", "")
            if not token:
                break
        # Yalnızca generateContent destekleyen modeller
        result = []
        for m in models:
            name = m.get("name", "")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods:
                # "models/gemini-1.5-pro" → "gemini-1.5-pro"
                short = name.split("/")[-1] if "/" in name else name
                result.append(short)
        return sorted(result)

    def supports_vision(self, model: str, api_key: str) -> bool:
        # Gemini 1.5 ve üzeri görsel destekler
        return "gemini-1.5" in model or "gemini-2" in model or "flash" in model

    def chat(
        self,
        messages: list[Message],
        model: str,
        api_key: str,
        *,
        max_tokens: int = 2048,
    ) -> AIResponse:
        # Gemini API: system instruction ayrı, kullanıcı/model mesajlar "contents" listesinde
        system_parts = [m for m in messages if m.role == "system"]
        chat_messages = [m for m in messages if m.role != "system"]

        contents = []
        for msg in chat_messages:
            parts: list[dict[str, Any]] = []
            if msg.images and self.supports_vision(model, api_key):
                for img in msg.images:
                    b64 = base64.b64encode(img).decode()
                    parts.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
            parts.append({"text": msg.content})
            role = "user" if msg.role == "user" else "model"
            contents.append({"role": role, "parts": parts})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        if system_parts:
            system_text = "\n\n".join(m.content for m in system_parts)
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        data = _post(f"models/{model}:generateContent", payload, api_key)

        candidates = data.get("candidates", [])
        raw_text = ""
        if candidates:
            parts_out = candidates[0].get("content", {}).get("parts", [])
            raw_text = "".join(p.get("text", "") for p in parts_out)

        usage = data.get("usageMetadata", {})
        text, suggestion = extract_task_suggestion(raw_text)
        return AIResponse(
            text=text,
            task_suggestion=suggestion,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            model=model,
        )


GEMINI = GeminiProvider()
