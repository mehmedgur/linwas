"""AI sağlayıcı yöneticisi.

Yapılandırılmış sağlayıcıları ve modelleri tutar;
sohbet gönderme, kullanım kaydetme ve geçmiş yönetimini koordine eder.
"""

from __future__ import annotations

from linwas.ai.base import AIError, AIProvider, AIResponse, Message
from linwas.ai.chat_history import CONTEXT_MARKER, ChatHistoryDB, Conversation
from linwas.ai.context import build_context, build_system_prompt
from linwas.ai.gemini import GEMINI
from linwas.ai.keystore import get_key
from linwas.ai.openai_compat import CHATGPT, DEEPSEEK
from linwas.ai.usage import UsageDB

ALL_PROVIDERS: list[AIProvider] = [GEMINI, CHATGPT, DEEPSEEK]


def available_providers() -> list[AIProvider]:
    """API anahtarı kayıtlı olan sağlayıcıları döner."""
    return [p for p in ALL_PROVIDERS if get_key(p.provider_id)]


def get_provider(provider_id: str) -> AIProvider | None:
    return next((p for p in ALL_PROVIDERS if p.provider_id == provider_id), None)


class AISession:
    """Tek bir sohbet oturumu: sağlayıcı, model, mesaj geçmişi."""

    def __init__(
        self,
        provider: AIProvider,
        model: str,
        usage_db: UsageDB | None = None,
        history_db: ChatHistoryDB | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._usage = usage_db or UsageDB()
        self._history_db = history_db or ChatHistoryDB()
        self._conversation = Conversation(
            provider=provider.provider_id,
            model=model,
        )
        # Sistem istemi her zaman ilk mesaj
        system_msg = Message(role="system", content=build_system_prompt())
        self._conversation.messages.append(system_msg)

    @classmethod
    def resume(
        cls,
        conversation: Conversation,
        provider: AIProvider,
        model: str,
        usage_db: UsageDB | None = None,
        history_db: ChatHistoryDB | None = None,
    ) -> AISession:
        """Kayıtlı bir sohbeti sürdürür; sonraki yanıtlar verilen modelden gelir."""
        session = cls(provider, model, usage_db, history_db)
        if conversation.messages and conversation.messages[0].role == "system":
            # Kayıtlı sistem istemi yerine güncel olanı kullan
            conversation.messages[0] = session._conversation.messages[0]
        else:
            conversation.messages.insert(0, session._conversation.messages[0])
        session._conversation = conversation
        session.switch(provider, model)
        return session

    def switch(self, provider: AIProvider, model: str) -> None:
        """Sohbet geçmişini koruyarak sağlayıcı/model değiştirir."""
        self._provider = provider
        self._model = model
        self._conversation.provider = provider.provider_id
        self._conversation.model = model

    @property
    def messages(self) -> list[Message]:
        """Sistem istemi hariç mesajlar."""
        return [m for m in self._conversation.messages if m.role != "system"]

    @property
    def provider(self) -> AIProvider:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def conversation_id(self) -> str:
        return self._conversation.id

    def send(
        self,
        text: str,
        images: list[bytes] | None = None,
        include_system_context: bool = False,
    ) -> AIResponse:
        """Kullanıcı mesajını gönderir, yanıt döner.

        include_system_context=True ise sistem bilgisi mesaja eklenir.
        """
        api_key = get_key(self._provider.provider_id)
        if not api_key:
            raise AIError(f"{self._provider.display_name} için API anahtarı bulunamadı")

        usage = self._usage.get(self._provider.provider_id)
        if usage.limit_reached:
            raise AIError(
                f"Aylık token limiti aşıldı ({usage.total:,} / {usage.limit:,}). "
                "Ayarlardan limiti artırabilirsiniz."
            )

        content = text
        from linwas.core import app_settings

        # Ayarlar › Yapay zekâ › "sistem bilgisi eklenebilsin" kapalıysa eklenmez
        if include_system_context and app_settings.load().ai_allow_system_info:
            context = build_context()
            content = f"{text}{CONTEXT_MARKER}{context}"

        user_msg = Message(
            role="user",
            content=content,
            images=images or [],
        )
        self._conversation.messages.append(user_msg)

        response = self._provider.chat(
            self._conversation.messages,
            self._model,
            api_key,
        )

        assistant_msg = Message(
            role="assistant", content=response.text, model=response.model or self._model
        )
        self._conversation.messages.append(assistant_msg)

        # Kullanım kaydet
        self._usage.record(
            self._provider.provider_id,
            response.input_tokens,
            response.output_tokens,
        )

        # Geçmiş kaydet (Ayarlar › Yapay zekâ › "Saklama" kapalıysa kaydedilmez)
        from linwas.core import app_settings

        if app_settings.load().ai_retention != "never":
            self._history_db.save(self._conversation)

        return response

    def clear(self) -> None:
        """Sohbet geçmişini temizler (sistem istemi kalır)."""
        system = self._conversation.messages[:1]
        self._conversation.messages = system
