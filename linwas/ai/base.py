"""AI altyapısı: ortak veri sınıfları ve soyut sağlayıcı arayüzü.

Her AI sağlayıcısı (Gemini, ChatGPT, DeepSeek) bu sınıfları uygular.
Qt'ye bağımlı değildir.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    """Tek bir sohbet mesajı."""

    role: str  # "system" | "user" | "assistant"
    content: str
    images: list[bytes] = field(default_factory=list)  # görsel ekleri (JPEG/PNG bayt)


@dataclass
class TaskSuggestion:
    """AI'ın önerdiği Linwas görevi.

    UI bu nesneyi karta dönüştürür; kullanıcı "Kuyruğa ekle" butonuna basınca
    TaskStep oluşturulup kuyruğa eklenir.
    """

    op_id: str
    params: dict[str, str]
    label: str  # kullanıcıya gösterilecek kısa açıklama


@dataclass
class AIResponse:
    """Sağlayıcıdan gelen yanıt."""

    text: str
    task_suggestion: TaskSuggestion | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class AIError(Exception):
    """AI sağlayıcısı hatası (ağ, kimlik doğrulama, limit vb.)."""


# Yanıt metnindeki görev önerisi etiketi kalıbı:
# <linwas_task op_id="package.install" params='{"name":"vlc"}'>VLC kur</linwas_task>
_TASK_TAG = re.compile(
    r'<linwas_task\s+op_id="([^"]+)"\s+params=\'([^\']+)\'>([^<]*)</linwas_task>',
    re.DOTALL,
)


def extract_task_suggestion(text: str) -> tuple[str, TaskSuggestion | None]:
    """Yanıt metninden görev önerisini ayıklar; temizlenmiş metin ve öneriyi döner."""
    import json

    m = _TASK_TAG.search(text)
    if not m:
        return text, None

    op_id = m.group(1).strip()
    params_str = m.group(2).strip()
    label = m.group(3).strip()

    try:
        params = json.loads(params_str)
        if not isinstance(params, dict):
            raise ValueError("params dict olmalı")
        # Tüm değerler string olmalı
        params = {str(k): str(v) for k, v in params.items()}
    except (json.JSONDecodeError, ValueError):
        return text, None

    clean_text = _TASK_TAG.sub("", text).rstrip()
    return clean_text, TaskSuggestion(op_id=op_id, params=params, label=label)


class AIProvider(ABC):
    """Soyut AI sağlayıcısı."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Benzersiz sağlayıcı kimliği: 'chatgpt' | 'gemini' | 'deepseek'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Kullanıcıya gösterilecek ad."""

    @abstractmethod
    def list_models(self, api_key: str) -> list[str]:
        """Kullanılabilir model listesini döner. Token harcamaz.

        Başarısız olursa AIError fırlatır.
        """

    @abstractmethod
    def supports_vision(self, model: str, api_key: str) -> bool:
        """Belirtilen modelin görsel girdi destekleyip desteklemediğini döner."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        model: str,
        api_key: str,
        *,
        max_tokens: int = 2048,
    ) -> AIResponse:
        """Mesaj dizisini gönderir, yanıt döner.

        Başarısız olursa AIError fırlatır.
        """
