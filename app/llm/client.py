import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Провайдер-агностичный интерфейс к LLM chat completions.

    Формат messages — OpenAI-совместимый:
        [{"role": "user"|"assistant", "content": "..."}]

    Реализации: OpenAILLMClient, GigaChatLLMClient.
    Добавление нового провайдера = новый класс в этом файле,
    без изменений LLMPromptEngine.
    """

    def complete(self, system: str, messages: list[dict[str, str]]) -> str: ...


class OpenAILLMClient:
    """Реализация LLMClient поверх OpenAI chat completions API.

    Синхронный вызов — PTB выполняет хэндлеры в пуле потоков,
    asyncio event loop не блокируется.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: int = 30) -> None:
        import openai  # lazy import: не загружается, если провайдер не выбран
        # trust_env=False отключает чтение системного прокси (тот же workaround,
        # что и в _HTTPXRequestNoProxy для Telegram-клиента).
        self._client = openai.OpenAI(
            api_key=api_key,
            timeout=timeout,
            http_client=httpx.Client(trust_env=False),
        )
        self._model = model

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return response.choices[0].message.content.strip()


class CloudRuLLMClient:
    """Реализация LLMClient поверх Cloud.ru Foundation Models API.

    API совместим с OpenAI (base_url: https://foundation-models.api.cloud.ru/v1).
    Поддерживает любую модель из каталога Cloud.ru Foundation Models,
    например: Qwen/Qwen3.6-35B-A3B, GigaChat-2-Max и др.

    api_key — ключ из личного кабинета Cloud.ru (раздел Foundation Models → API ключи).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "Qwen/Qwen3.6-35B-A3B",
        timeout: int = 30,
    ) -> None:
        import openai  # lazy import
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url="https://foundation-models.api.cloud.ru/v1",
            timeout=timeout,
            http_client=httpx.Client(trust_env=False),
        )
        self._model = model

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}] + messages,
            max_tokens=2500,
            temperature=0.5,
            top_p=0.95,
        )
        return response.choices[0].message.content.strip()


class GigaChatLLMClient:
    """Реализация LLMClient поверх GigaChat API (Sber).

    credentials — Authorization Key из developers.sber.ru/studio.
    verify_ssl_certs=False нужен при самоподписанном сертификате Sber (типично для Windows).

    Для смены провайдера достаточно передать GigaChatLLMClient вместо OpenAILLMClient
    в LLMPromptEngine — движок не меняется.
    """

    def __init__(
        self,
        credentials: str,
        model: str = "GigaChat",
        verify_ssl_certs: bool = False,
        timeout: int = 30,
    ) -> None:
        self._credentials = credentials
        self._model = model
        self._verify_ssl = verify_ssl_certs
        self._timeout = timeout

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        # Lazy imports: gigachat загружается только если провайдер выбран.
        from gigachat import GigaChat  # type: ignore[import]
        from gigachat.models import Chat, Messages, MessagesRole  # type: ignore[import]

        gc_messages: list[Messages] = [
            Messages(role=MessagesRole.SYSTEM, content=system)
        ]
        for msg in messages:
            role = (
                MessagesRole.ASSISTANT
                if msg["role"] == "assistant"
                else MessagesRole.USER
            )
            gc_messages.append(Messages(role=role, content=msg["content"]))

        with GigaChat(
            credentials=self._credentials,
            verify_ssl_certs=self._verify_ssl,
            timeout=self._timeout,
        ) as giga:
            response = giga.chat(Chat(model=self._model, messages=gc_messages))
            return response.choices[0].message.content.strip()
