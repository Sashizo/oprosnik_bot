"""Тесты для app/bot/adapter.py — build_application и handler routing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler

from app.bot.adapter import _handle_callback, build_application
from app.bot.keyboards import CALLBACK_BEGIN, CALLBACK_RESTART
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

def _make_dm_mock(begin_text="Вопрос 1?", begin_kind="question"):
    """Создаёт mock DialogManager с настроенным begin()."""
    dm = MagicMock()
    dm.begin.return_value = DialogResult(text=begin_text, kind=begin_kind)
    return dm


def test_handle_callback_begin_calls_dm_begin():
    """CALLBACK_BEGIN вызывает dm.begin() и отправляет первый вопрос."""
    dm_mock = _make_dm_mock(begin_text="Вопрос 1?")

    query_mock = AsyncMock()
    query_mock.data = CALLBACK_BEGIN
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
    dm_mock.begin.assert_called_once_with(42)
    query_mock.message.reply_text.assert_awaited_once()
    assert "Вопрос 1?" in query_mock.message.reply_text.call_args[0][0]


def test_handle_callback_restart_calls_dm_begin():
    """CALLBACK_RESTART («Пройти ещё раз») вызывает dm.begin() — без повторного приветствия."""
    dm_mock = _make_dm_mock(begin_text="Вопрос 1?")

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
    dm_mock.begin.assert_called_once_with(42)
    query_mock.message.reply_text.assert_awaited_once()
    assert "Вопрос 1?" in query_mock.message.reply_text.call_args[0][0]


def test_handle_callback_unknown_data_is_ignored():
    """Неизвестный callback_data не вызывает dm.begin() и не падает с ошибкой."""
    dm_mock = _make_dm_mock()

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

    query_mock.answer.assert_awaited_once()     # answer вызывается всегда
    dm_mock.begin.assert_not_called()            # dm.begin НЕ вызывается
    query_mock.message.reply_text.assert_not_awaited()
