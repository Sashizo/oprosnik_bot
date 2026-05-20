import logging
import os
import sys

# ── Proxy workaround (Windows only) ──────────────────────────────────────────
# На Windows-машине системный прокси может быть SOCKS4 (socks4://127.0.0.1:...),
# который httpx не поддерживает — клиент падает с "Unknown scheme for proxy URL".
#
# NO_PROXY=* говорит httpx обойти прокси для всех хостов.
# setdefault: если пользователь уже задал NO_PROXY в окружении — не перебиваем.
# Применяем только на Windows; на Linux/Mac системный прокси не мешает.
# Должно стоять ДО любых импортов, создающих HTTP-клиенты (gigachat, openai).
if sys.platform == "win32":
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("no_proxy", "*")
# ─────────────────────────────────────────────────────────────────────────────

from app.core.config import settings
from app.bot.adapter import build_application
from app.db.database import build_engine, build_session_factory, init_db
from app.db.repository import SQLiteSessionStore
from app.services.prompt_engine import PromptEngine, StaticPromptEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_engine(settings, study=None) -> PromptEngine:
    """Выбирает Prompt Engine на основе конфига.

    Приоритет:
      1. LLM_PROVIDER=gigachat + LLM_GIGACHAT_CREDENTIALS задан → GigaChatLLMClient
      2. LLM_PROVIDER=openai  + LLM_API_KEY задан             → OpenAILLMClient
      3. Иначе                                                 → StaticPromptEngine

    study передаётся в engine как источник правды по вопросам.
    При study=None — legacy-режим (interview_script.py).

    Провайдерные пакеты (openai, gigachat) импортируются лениво —
    не загружаются, если соответствующий провайдер не выбран.
    """
    from app.llm.engine import LLMPromptEngine

    provider = settings.llm_provider.lower()

    if provider == "gigachat" and settings.llm_gigachat_credentials:
        from app.llm.client import GigaChatLLMClient
        client = GigaChatLLMClient(
            credentials=settings.llm_gigachat_credentials,
            model=settings.llm_model,
            timeout=settings.llm_gigachat_timeout,
        )
        logger.info("LLM enabled (provider=gigachat, model=%s)", settings.llm_model)
        return LLMPromptEngine(client=client, study=study)

    if provider == "openai" and settings.llm_api_key:
        from app.llm.client import OpenAILLMClient
        client = OpenAILLMClient(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
        logger.info("LLM enabled (provider=openai, model=%s)", settings.llm_model)
        return LLMPromptEngine(client=client, study=study)

    logger.info(
        "LLM not configured (provider=%s) — StaticPromptEngine (static mode)",
        settings.llm_provider,
    )
    return StaticPromptEngine(study=study)


def main() -> None:
    token = settings.telegram_bot_token
    if not token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Add it to .env and restart."
        )
        sys.exit(1)

    # Инициализируем БД: создаём таблицы и миграции если нужно.
    engine = build_engine(settings.database_url)
    init_db(engine)
    session_factory = build_session_factory(engine)
    store = SQLiteSessionStore(session_factory)

    # Загружаем активный Study из БД.
    # None → legacy-режим (interview_script.py как источник вопросов).
    from app.researcher.repository import StudyRepository
    study_repo = StudyRepository(session_factory)
    active_study = study_repo.get_active()
    if active_study is not None:
        logger.info(
            'Active study: #%d "%s" (%d questions)',
            active_study.study_id, active_study.title, len(active_study.questions),
        )
    else:
        logger.info("No active study — using legacy interview_script.py")

    # Выбираем Prompt Engine на основе конфига; передаём active_study.
    prompt_engine = _build_engine(settings, study=active_study)

    # Читаем whitelist исследователей из settings.researcher_telegram_ids.
    # При пустой строке researcher-режим недоступен никому.
    researcher_ids = frozenset(
        int(x.strip())
        for x in settings.researcher_telegram_ids.split(",")
        if x.strip().isdigit()
    )
    if researcher_ids:
        logger.info("Researcher mode enabled for %d user(s).", len(researcher_ids))
    else:
        logger.info("Researcher mode disabled (RESEARCHER_TELEGRAM_IDS not set).")

    logger.info("Starting Telegram polling...")
    app = build_application(
        token,
        store=store,
        engine=prompt_engine,
        researcher_ids=researcher_ids,
        study_repo=study_repo,
        session_factory=session_factory,
    )
    app.run_polling()


if __name__ == "__main__":
    main()
