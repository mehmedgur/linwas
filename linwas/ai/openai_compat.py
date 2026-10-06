"""ChatGPT ve DeepSeek sağlayıcısı (OpenAI uyumlu API).

Her iki sağlayıcı da aynı OpenAI uyumlu arayüzü kullandığından tek istemci yeterli.
HTTP: yalnızca standart kütüphane (urllib). Harici bağımlılık yok.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from linwas.ai.base import AIError, AIProvider, AIResponse, Message, extract_task_suggestion
from linwas.core.sanitizer import sanitize


def _post(url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        safe_body = sanitize(body)
        raise AIError(f"HTTP {exc.code}: {safe_body[:300]}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Bağlantı hatası: {exc.reason}") from exc


def _get(url: str, api_key: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise AIError(f"HTTP {exc.code}: {sanitize(body[:300])}", status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise AIError(f"Bağlantı hatası: {exc.reason}") from exc


class OpenAICompatProvider(AIProvider):
    """OpenAI uyumlu API sağlayıcısı (ChatGPT veya DeepSeek)."""

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        base_url: str,
    ) -> None:
        self._id = provider_id
        self._name = display_name
        self._base_url = base_url.rstrip("/")

    @property
    def provider_id(self) -> str:
        return self._id

    @property
    def display_name(self) -> str:
        return self._name

    def list_models(self, api_key: str) -> list[str]:
        data = _get(f"{self._base_url}/models", api_key)
        models = data.get("data", [])
        ids = [m["id"] for m in models if isinstance(m, dict) and "id" in m]
        # Sohbet modellerini önce göster; embeddings/tts vb. filtrele
        chat = [m for m in ids if not any(x in m for x in ("embed", "tts", "whisper", "dall"))]
        return sorted(chat) or sorted(ids)

    def supports_vision(self, model: str, api_key: str) -> bool:
        # DeepSeek için model bilgisinden input_modalities kontrol et
        if self._id == "deepseek":
            try:
                data = _get(f"{self._base_url}/models/{model}", api_key)
                modalities = data.get("input_modalities", [])
                return "image" in modalities
            except AIError:
                return False
        # ChatGPT: gpt-4o ve türevleri görsel destekler
        return "vision" in model or "4o" in model or "gpt-4" in model.lower()

    def chat(
        self,
        messages: list[Message],
        model: str,
        api_key: str,
        *,
        max_tokens: int = 2048,
    ) -> AIResponse:
        payload_messages = []
        for msg in messages:
            if msg.images and self.supports_vision(model, api_key):
                content: Any = [{"type": "text", "text": msg.content}]
                for img in msg.images:
                    b64 = base64.b64encode(img).decode()
                    content.append(
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    )
            else:
                content = msg.content
            payload_messages.append({"role": msg.role, "content": content})

        payload = {
            "model": model,
            "messages": payload_messages,
            "max_tokens": max_tokens,
        }
        data = _post(f"{self._base_url}/chat/completions", payload, api_key)

        choice = data.get("choices", [{}])[0]
        raw_text = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})

        text, suggestion = extract_task_suggestion(raw_text)
        return AIResponse(
            text=text,
            task_suggestion=suggestion,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=model,
        )


# Hazır sağlayıcı örnekleri
CHATGPT = OpenAICompatProvider(
    provider_id="chatgpt",
    display_name="ChatGPT",
    base_url="https://api.openai.com/v1",
)

DEEPSEEK = OpenAICompatProvider(
    provider_id="deepseek",
    display_name="DeepSeek",
    base_url="https://api.deepseek.com",
)
