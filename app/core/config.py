from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    telegram_bot_token: str = ""
    database_url: str = "sqlite:///./interview.db"
    llm_provider: str = "openai"              # "openai" | "gigachat"
    llm_api_key: str = ""                     # OpenAI: пусто → StaticPromptEngine
    llm_model: str = "gpt-4o-mini"            # openai: gpt-4o-mini; gigachat: GigaChat
    llm_timeout: int = 30                     # секунды (только для OpenAI)
    llm_gigachat_credentials: str = ""        # GigaChat: Authorization Key из Sber Studio
    llm_cloudru_api_key: str = ""             # Cloud.ru Foundation Models: API ключ
    llm_cloudru_model: str = "Qwen/Qwen3.6-35B-A3B"  # модель из каталога Cloud.ru
    # Telegram user_id(s) с доступом к /researcher меню.
    # Формат: "123456789" или "123456789,987654321" (через запятую).
    # При пустой строке researcher-режим недоступен никому.
    researcher_telegram_ids: str = ""

    # ── Security: web admin auth (HTTP Basic Auth) ────────────────────────────
    # При пустом ADMIN_PASSWORD web-admin доступен без пароля (dev-mode);
    # при старте uvicorn выводится предупреждение в лог.
    admin_username: str = "researcher"
    admin_password: str = ""

    # ── Security: GigaChat timeout (аналог llm_timeout для OpenAI) ───────────
    llm_gigachat_timeout: int = 30

    # ── Security: input limits ────────────────────────────────────────────────
    max_message_length: int = 2000     # символов; сообщения длиннее — отклоняются

    # ── Security: Telegram rate limiting (sliding window) ─────────────────────
    rate_limit_messages: int = 10      # сообщений за rate_limit_window_seconds
    rate_limit_callbacks: int = 20     # callback'ов за rate_limit_window_seconds
    rate_limit_window_seconds: int = 60

    # ── Telegram Bot API base URL ──────────────────────────────────────────────
    # По умолчанию — официальный API Telegram.
    # Для обхода блокировок (напр. через Cloudflare Worker) задай:
    #   TELEGRAM_BASE_URL=https://your-worker.workers.dev/bot
    telegram_base_url: str = "https://api.telegram.org/bot"


settings = Settings()
