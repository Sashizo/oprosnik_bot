import logging

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from app.bot.keyboards import CALLBACK_BEGIN, CALLBACK_RESTART, keyboard_begin, keyboard_restart, keyboard_start
from app.bot.rate_limiter import InMemoryRateLimiter
from app.bot.researcher_menu import register_researcher_handlers
from app.core.config import settings
from app.services import interview_script as script
from app.services.dialog_manager import DialogManager
from app.services.prompt_engine import PromptEngine
from app.services.session_store import SessionStore

logger = logging.getLogger(__name__)

# Виды ответов, к которым прикрепляется кнопка «Пройти ещё раз».
_RESTART_BUTTON_KINDS = frozenset({"closing", "already_done"})


class _HTTPXRequestNoProxy(HTTPXRequest):
    """HTTPXRequest с отключённым чтением системного прокси.

    httpx подхватывает системный SOCKS4-прокси (socks4://127.0.0.1),
    который он не поддерживает (только SOCKS5). trust_env=False
    отключает env/registry proxy detection без изменения os.environ.
    """

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**self._client_kwargs, trust_env=False)


async def _start(update: Update, context) -> None:
    """Показывает приветственный экран с кнопкой «Начать интервью».

    Текст берётся через dm.welcome() → engine.intro(), что гарантирует
    отображение актуального приветствия из активного исследования.
    Сессия НЕ сбрасывается здесь — только когда пользователь нажмёт кнопку.
    """
    dm: DialogManager = context.bot_data["dm"]
    await update.message.reply_text(dm.welcome(), reply_markup=keyboard_begin())


async def _handle_text(update: Update, context) -> None:
    user_id = update.effective_user.id

    # ── Rate limiting ─────────────────────────────────────────────────────────
    msg_limiter: InMemoryRateLimiter | None = context.bot_data.get("msg_limiter")
    if msg_limiter is not None and not msg_limiter.is_allowed(user_id):
        logger.info("[AUDIT] action=rate_limit_hit type=message user_id=%d", user_id)
        await update.message.reply_text(
            "Пожалуйста, не торопитесь — подождите немного перед следующим сообщением."
        )
        return

    # ── Input size limit ──────────────────────────────────────────────────────
    if len(update.message.text) > settings.max_message_length:
        logger.info(
            "[AUDIT] action=oversized_message user_id=%d length=%d",
            user_id, len(update.message.text),
        )
        await update.message.reply_text(
            "Ваше сообщение слишком длинное. Пожалуйста, напишите ответ короче."
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )
    dm: DialogManager = context.bot_data["dm"]
    result = dm.process(user_id, update.message.text)
    markup = keyboard_restart() if result.kind in _RESTART_BUTTON_KINDS else None
    await update.message.reply_text(result.text, reply_markup=markup)


async def _help(update: Update, context) -> None:
    """Показывает подсказку с кнопкой «Начать интервью»."""
    await update.message.reply_text(script.HELP, reply_markup=keyboard_start())


async def _handle_callback(update: Update, context) -> None:
    """Обрабатывает нажатия InlineKeyboard-кнопок.

    query.answer() обязательно — убирает индикатор загрузки у кнопки в Telegram.
    Неизвестные callback_data игнорируются без ошибок.
    """
    query = update.callback_query
    user_id = query.from_user.id

    # ── Callback rate limiting ────────────────────────────────────────────────
    cb_limiter: InMemoryRateLimiter | None = context.bot_data.get("cb_limiter")
    if cb_limiter is not None and not cb_limiter.is_allowed(user_id):
        logger.info("[AUDIT] action=rate_limit_hit type=callback user_id=%d", user_id)
        await query.answer()  # убрать «часы», ничего не делать
        return

    await query.answer()  # убрать «часы» у кнопки

    dm: DialogManager = context.bot_data["dm"]

    if query.data == CALLBACK_BEGIN:
        # Кнопка «Начать интервью» (первый запуск или из /help).
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )
        result = dm.begin(query.from_user.id)
        await query.message.reply_text(result.text)

    elif query.data == CALLBACK_RESTART:
        # Кнопка «Пройти ещё раз» (после closing / already_done).
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )
        result = dm.begin(query.from_user.id)
        await query.message.reply_text(result.text)
    # else: неизвестный action — молча игнорируем (forward compatibility)


def build_application(
    token: str,
    store: SessionStore | None = None,
    engine: PromptEngine | None = None,
    engines: dict | None = None,
    active_provider: str = "static",
    researcher_ids: frozenset | None = None,
    study_repo=None,
    session_factory=None,
) -> Application:
    """Собирает Telegram Application.

    store:           реализация SessionStore Protocol.
                     При None — InMemorySessionStore (тесты / запуск без БД).
    engine:          реализация PromptEngine Protocol.
                     При None — DialogManager создаёт StaticPromptEngine по умолчанию.
    researcher_ids:  frozenset[int] авторизованных Telegram user_id исследователей.
                     При None или пустом — researcher-режим недоступен никому.
    study_repo:      StudyRepository для researcher-меню.
                     При None — researcher-меню работает без доступа к исследованиям.
    session_factory: SQLAlchemy sessionmaker для статистики и экспорта в researcher-меню.
    """
    if store is None:
        from app.services.session_store import InMemorySessionStore
        store = InMemorySessionStore()

    # Два отдельных request-объекта: один для API-вызовов (sendMessage и др.),
    # второй для цикла getUpdates (polling). Оба обходят системный прокси.
    request = _HTTPXRequestNoProxy()
    get_updates_request = _HTTPXRequestNoProxy(connection_pool_size=1)

    app = (
        Application.builder()
        .token(token)
        .base_url(settings.telegram_base_url)
        .request(request)
        .get_updates_request(get_updates_request)
        .build()
    )

    # Если передан dict движков — используем активный; иначе берём engine напрямую.
    _engines = engines or {}
    active_engine = _engines.get(active_provider) or engine
    app.bot_data["dm"] = DialogManager(store=store, engine=active_engine)
    app.bot_data["store"] = store          # нужен для пересборки DM при смене модели
    app.bot_data["engines"] = _engines     # все доступные движки
    app.bot_data["active_provider"] = active_provider
    app.bot_data["researcher_ids"] = researcher_ids or frozenset()
    app.bot_data["study_repo"] = study_repo
    app.bot_data["session_factory"] = session_factory

    # Rate limiters: sliding window per-user, configurable via settings.
    app.bot_data["msg_limiter"] = InMemoryRateLimiter(
        max_calls=settings.rate_limit_messages,
        window_seconds=settings.rate_limit_window_seconds,
    )
    app.bot_data["cb_limiter"] = InMemoryRateLimiter(
        max_calls=settings.rate_limit_callbacks,
        window_seconds=settings.rate_limit_window_seconds,
    )

    # Researcher-handler'ы регистрируются ПЕРВЫМИ — до универсального
    # CallbackQueryHandler responder-кнопок. Паттерн r"^r:" гарантирует
    # изоляцию: "action:*" callback'и сюда не попадут.
    register_researcher_handlers(app)

    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    app.add_handler(CallbackQueryHandler(_handle_callback))
    return app
