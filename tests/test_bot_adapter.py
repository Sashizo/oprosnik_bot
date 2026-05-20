"""Тесты для app/bot/adapter.py — build_application и handler routing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler

from app.bot.adapter import _handle_callback, build_application
from app.bot.keyboards import CALLBACK_RESTART
from app.services.dialog_manager import DialogResult

_FAKE_TOKEN = "123:FAKE_TOKEN_FOR_TESTING"


# ── build_application ─────────────────────────────────────────────────────────

def test_build_application_returns_application():
    app = build_application(_FAKE_TOKEN)
    assert isinstance(app, Application)


def test_handlers_registered():
    app = build_application(_FAKE_TOKEN)
    handler_types = [
        type(h)
        for group in app.handlers.values()
        for h in group
    ]
    assert CommandHandler in handler_types
    assert MessageHandler in handler_types


def test_callback_query_handler_registered():
    """CallbackQueryHandler зарегистрирован в приложении."""
    app = build_application(_FAKE_TOKEN)
    handler_types = [
        type(h)
        for group in app.handlers.values()
        for h in group
    ]
    assert CallbackQueryHandler in handler_types


# ── _handle_callback routing ──────────────────────────────────────────────────

def test_handle_callback_restart_calls_dm_start():
    """Нажатие CALLBACK_RESTART вызывает dm.start() и отправляет сообщение."""
    dm_mock = MagicMock()
    dm_mock.start.return_value = DialogResult(text="Привет! Вопрос 1?", kind="question")

    query_mock = AsyncMock()
    query_mock.data = CALLBACK_RESTART
    query_mock.from_user.id = 42
    query_mock.message.reply_text = AsyncMock()

    update_mock = MagicMock()
    update_mock.callback_query = query_mock
    update_mock.effective_chat.id = 100

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock}
    context_mock.bot.send_chat_action = AsyncMock()

    asyncio.run(_handle_callback(update_mock, context_mock))

    query_mock.answer.assert_awaited_once()
    dm_mock.start.assert_called_once_with(42)
    query_mock.message.reply_text.assert_awaited_once()
    call_args = query_mock.message.reply_text.call_args[0][0]
    assert "Вопрос 1?" in call_args


def test_handle_callback_unknown_data_is_ignored():
    """Неизвестный callback_data не вызывает dm.start() и не падает с ошибкой."""
    dm_mock = MagicMock()

    query_mock = AsyncMock()
    query_mock.data = "action:unknown_future_action"
    query_mock.message.reply_text = AsyncMock()

    update_mock = MagicMock()
    update_mock.callback_query = query_mock
    update_mock.effective_chat.id = 100

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock}
    context_mock.bot.send_chat_action = AsyncMock()

    asyncio.run(_handle_callback(update_mock, context_mock))

    query_mock.answer.assert_awaited_once()    # answer вызывается всегда
    dm_mock.start.assert_not_called()           # dm.start НЕ вызывается
    query_mock.message.reply_text.assert_not_awaited()
