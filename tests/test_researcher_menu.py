"""Тесты для app/bot/researcher_menu.py — Researcher Menu in Telegram."""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.researcher_menu import (
    R_ACTIVATE,
    R_ACTIVATE_PREFIX,
    R_EXPORT,
    R_LIST,
    R_MENU,
    R_STATS,
    _cmd_researcher,
    _do_activate,
    _do_export,
    _fmt_active_card,
    _generate_csv_bytes,
    _handle_researcher_callback,
    _is_researcher,
    _kb_back,
    _kb_main,
    _show_activate_menu,
    _show_list,
    _show_stats,
    register_researcher_handlers,
)
from app.bot.adapter import build_application
from telegram.ext import CallbackQueryHandler, CommandHandler


# ── Вспомогательные фабрики ───────────────────────────────────────────────────

def _make_context(
    researcher_ids=frozenset(),
    study_repo=None,
    session_factory=None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.bot_data = {
        "researcher_ids": researcher_ids,
        "study_repo": study_repo,
        "session_factory": session_factory,
    }
    ctx.bot.send_document = AsyncMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _make_update(user_id: int = 1) -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    return update


def _make_query(user_id: int = 1, data: str = R_MENU) -> AsyncMock:
    query = AsyncMock()
    query.from_user.id = user_id
    query.data = data
    query.message.edit_text = AsyncMock()
    query.message.chat_id = 100
    return query


def _make_study(study_id: int = 1, title: str = "Тест", n_questions: int = 3):
    """Создаёт MagicMock, имитирующий StudyDefinition."""
    study = MagicMock()
    study.study_id = study_id
    study.title = title
    study.questions = [MagicMock()] * n_questions
    return study


# ── _is_researcher ────────────────────────────────────────────────────────────

def test_is_researcher_authorized():
    ctx = _make_context(researcher_ids=frozenset({42}))
    assert _is_researcher(42, ctx) is True


def test_is_researcher_unauthorized():
    ctx = _make_context(researcher_ids=frozenset({42}))
    assert _is_researcher(99, ctx) is False


def test_is_researcher_empty_whitelist():
    ctx = _make_context(researcher_ids=frozenset())
    assert _is_researcher(42, ctx) is False


# ── _fmt_active_card ──────────────────────────────────────────────────────────

def test_fmt_active_card_no_study():
    text = _fmt_active_card(None)
    assert "Нет активного" in text


def test_fmt_active_card_with_study():
    study = _make_study(study_id=3, title="Цифровые технологии", n_questions=3)
    text = _fmt_active_card(study)
    assert "Цифровые технологии" in text
    assert "3" in text
    assert "id: 3" in text


# ── _cmd_researcher — авторизация ─────────────────────────────────────────────

def test_cmd_researcher_unauthorized_does_nothing():
    update = _make_update(user_id=99)
    ctx = _make_context(researcher_ids=frozenset({42}))
    asyncio.run(_cmd_researcher(update, ctx))
    update.message.reply_text.assert_not_awaited()


def test_cmd_researcher_authorized_sends_menu():
    update = _make_update(user_id=42)
    repo = MagicMock()
    repo.get_active.return_value = _make_study()
    ctx = _make_context(researcher_ids=frozenset({42}), study_repo=repo)
    asyncio.run(_cmd_researcher(update, ctx))
    update.message.reply_text.assert_awaited_once()


def test_cmd_researcher_no_active_study():
    update = _make_update(user_id=42)
    repo = MagicMock()
    repo.get_active.return_value = None
    ctx = _make_context(researcher_ids=frozenset({42}), study_repo=repo)
    asyncio.run(_cmd_researcher(update, ctx))
    text = update.message.reply_text.call_args[0][0]
    assert "Нет активного" in text


# ── _handle_researcher_callback — авторизация ─────────────────────────────────

def test_callback_unauthorized_is_ignored():
    query = _make_query(user_id=99, data=R_MENU)
    ctx = _make_context(researcher_ids=frozenset({42}))
    asyncio.run(_handle_researcher_callback(MagicMock(callback_query=query), ctx))
    query.message.edit_text.assert_not_awaited()


# ── _show_list ────────────────────────────────────────────────────────────────

def test_show_list_no_studies():
    query = _make_query()
    repo = MagicMock()
    repo.list_all.return_value = []
    repo.get_active.return_value = None
    asyncio.run(_show_list(query, repo))
    text = query.message.edit_text.call_args[0][0]
    assert "Исследований нет" in text


def test_show_list_marks_active():
    query = _make_query()
    repo = MagicMock()
    s1 = _make_study(study_id=1, title="Первое")
    s2 = _make_study(study_id=2, title="Второе")
    repo.list_all.return_value = [s1, s2]
    repo.get_active.return_value = _make_study(study_id=2, title="Второе")
    asyncio.run(_show_list(query, repo))
    text = query.message.edit_text.call_args[0][0]
    assert "Первое" in text
    assert "Второе" in text
    assert "активное" in text


def test_show_list_no_repo():
    query = _make_query()
    asyncio.run(_show_list(query, None))
    text = query.message.edit_text.call_args[0][0]
    assert "недоступен" in text


# ── _show_activate_menu ───────────────────────────────────────────────────────

def test_show_activate_menu_empty():
    query = _make_query()
    repo = MagicMock()
    repo.list_all.return_value = []
    asyncio.run(_show_activate_menu(query, repo))
    text = query.message.edit_text.call_args[0][0]
    assert "Нет исследований" in text


def test_show_activate_menu_has_buttons():
    query = _make_query()
    repo = MagicMock()
    repo.list_all.return_value = [
        _make_study(study_id=1, title="Исследование 1"),
        _make_study(study_id=2, title="Исследование 2"),
    ]
    asyncio.run(_show_activate_menu(query, repo))
    markup = query.message.edit_text.call_args[1]["reply_markup"]
    # Кнопки исследований + кнопка «↩ Меню»
    all_buttons = [btn for row in markup.inline_keyboard for btn in row]
    cb_datas = [b.callback_data for b in all_buttons]
    assert f"{R_ACTIVATE_PREFIX}1" in cb_datas
    assert f"{R_ACTIVATE_PREFIX}2" in cb_datas
    assert R_MENU in cb_datas


# ── _do_activate ──────────────────────────────────────────────────────────────

def _make_context_with_engines():
    """Минимальный context-мок для _do_activate (нужен для rebuild engines)."""
    from app.services.prompt_engine import StaticPromptEngine
    from app.services.dialog_manager import DialogManager
    context = MagicMock()
    context.bot_data = {
        "engines": {"static": StaticPromptEngine()},
        "active_provider": "static",
        "store": MagicMock(),
    }
    return context


def test_do_activate_success():
    query = _make_query()
    context = _make_context_with_engines()
    repo = MagicMock()
    repo.activate.return_value = True
    repo.get_by_id.return_value = _make_study(study_id=7, title="Выбранное")
    asyncio.run(_do_activate(query, context, repo, "7"))
    repo.activate.assert_called_once_with(7)
    text = query.message.edit_text.call_args[0][0]
    assert "Выбранное" in text
    assert "Активировано" in text


def test_do_activate_not_found():
    query = _make_query()
    context = _make_context_with_engines()
    repo = MagicMock()
    repo.activate.return_value = False
    asyncio.run(_do_activate(query, context, repo, "999"))
    text = query.message.edit_text.call_args[0][0]
    assert "не найдено" in text


def test_do_activate_invalid_id():
    query = _make_query()
    context = _make_context_with_engines()
    repo = MagicMock()
    asyncio.run(_do_activate(query, context, repo, "abc"))
    text = query.message.edit_text.call_args[0][0]
    assert "Некорректный" in text
    repo.activate.assert_not_called()


# ── _show_stats ───────────────────────────────────────────────────────────────

def test_show_stats_no_active_study():
    query = _make_query()
    repo = MagicMock()
    repo.get_active.return_value = None
    ctx = _make_context()
    asyncio.run(_show_stats(query, repo, ctx))
    text = query.message.edit_text.call_args[0][0]
    assert "Нет активного" in text


def test_show_stats_with_data():
    query = _make_query()
    repo = MagicMock()
    repo.get_active.return_value = _make_study(study_id=3, title="Мониторинг")

    # Мок session_factory: контекстный менеджер → мок-db → query chain
    db_mock = MagicMock()
    # first call: total=10, second call: finished=7
    db_mock.query.return_value.filter_by.return_value.count.side_effect = [10, 7]
    sf_mock = MagicMock(return_value=MagicMock(
        __enter__=lambda s, *a: db_mock,
        __exit__=lambda s, *a: None,
    ))
    ctx = _make_context(session_factory=sf_mock)

    asyncio.run(_show_stats(query, repo, ctx))
    text = query.message.edit_text.call_args[0][0]
    assert "Мониторинг" in text
    assert "10" in text   # total
    assert "7" in text    # finished
    assert "3" in text    # in_progress = 10 - 7


def test_show_stats_no_session_factory():
    query = _make_query()
    repo = MagicMock()
    repo.get_active.return_value = _make_study()
    ctx = _make_context(session_factory=None)
    asyncio.run(_show_stats(query, repo, ctx))
    text = query.message.edit_text.call_args[0][0]
    assert "недоступен" in text


# ── _do_export ────────────────────────────────────────────────────────────────

def test_do_export_sends_document():
    query = _make_query()
    # session_factory должен быть не None, иначе _do_export вернётся раньше
    ctx = _make_context(session_factory=MagicMock())

    fake_sessions = []  # пустой список → пустой CSV, но документ всё равно отправится
    with patch("app.db.repository.get_all_sessions", return_value=fake_sessions):
        asyncio.run(_do_export(query, ctx))

    ctx.bot.send_document.assert_awaited_once()
    call_kwargs = ctx.bot.send_document.call_args[1]
    assert call_kwargs["chat_id"] == query.message.chat_id
    assert call_kwargs["filename"].endswith(".csv")
    assert "сессий" in call_kwargs["caption"]


def test_do_export_no_session_factory():
    query = _make_query()
    ctx = _make_context(session_factory=None)
    asyncio.run(_do_export(query, ctx))
    ctx.bot.send_document.assert_not_awaited()
    ctx.bot.send_message.assert_awaited_once()


# ── _generate_csv_bytes ───────────────────────────────────────────────────────

def test_generate_csv_bytes_returns_bytes():
    result = _generate_csv_bytes([])
    assert isinstance(result, bytes)


def test_generate_csv_bytes_has_headers():
    result = _generate_csv_bytes([])
    text = result.decode("utf-8")
    assert "session_id" in text
    assert "answer_text" in text


# ── Callback routing isolation ────────────────────────────────────────────────

def test_researcher_handler_has_r_prefix_pattern():
    """researcher CallbackQueryHandler должен иметь паттерн r'^r:'."""
    from app.bot.adapter import build_application
    app = build_application("123:FAKE")
    cq_handlers = [
        h for group in app.handlers.values()
        for h in group
        if isinstance(h, CallbackQueryHandler)
    ]
    patterns = []
    for h in cq_handlers:
        if hasattr(h, "pattern") and h.pattern is not None:
            patterns.append(h.pattern.pattern if hasattr(h.pattern, "pattern") else str(h.pattern))
    assert any("^r:" in p for p in patterns), (
        f"Нет CallbackQueryHandler с паттерном r'^r:'. Найдены паттерны: {patterns}"
    )


def test_responder_callback_does_not_match_researcher_pattern():
    """action:restart НЕ должен совпадать с паттерном r'^r:'."""
    import re
    pattern = re.compile(r"^r:")
    assert not pattern.match("action:restart")


def test_researcher_callback_matches_pattern():
    """r:menu, r:list, r:activate:5 — все совпадают с r'^r:'."""
    import re
    pattern = re.compile(r"^r:")
    for cb in [R_MENU, R_LIST, R_ACTIVATE, R_STATS, R_EXPORT, f"{R_ACTIVATE_PREFIX}5"]:
        assert pattern.match(cb), f"Callback {cb!r} не совпал с паттерном"


# ── Responder flow не сломан ──────────────────────────────────────────────────

def test_respondent_session_unaffected_by_researcher_command():
    """/researcher не трогает DialogManager — состояние сессии не меняется."""
    from app.services.dialog_manager import DialogManager
    from app.services.session_store import InMemorySessionStore

    dm = DialogManager(store=InMemorySessionStore())
    dm.start(user_id=42)
    dm.process(42, "первый ответ")

    # Имитируем вызов /researcher (не трогает dm вообще)
    update = _make_update(user_id=42)
    repo = MagicMock()
    repo.get_active.return_value = None
    ctx = _make_context(researcher_ids=frozenset({42}), study_repo=repo)
    asyncio.run(_cmd_researcher(update, ctx))

    # Состояние диалога должно остаться на вопросе 1 (индекс 1)
    session = dm._store.get_or_create(42)
    assert session.current_question_index == 1


# ── register_researcher_handlers ─────────────────────────────────────────────

def test_register_adds_command_and_callback_handlers():
    """После register_researcher_handlers в app есть /researcher CommandHandler."""
    app = build_application("123:FAKE")
    handler_types = [
        type(h) for group in app.handlers.values() for h in group
    ]
    assert CommandHandler in handler_types
    assert CallbackQueryHandler in handler_types
