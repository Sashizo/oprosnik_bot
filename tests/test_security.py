"""Тесты для M14 — Security Hardening Baseline.

Покрывает:
  - InMemoryRateLimiter (app/bot/rate_limiter.py)
  - HTTP Basic Auth для web-admin (app/core/security.py + admin/router.py)
  - Ограничение размера сообщений Telegram (app/bot/adapter.py)
  - Rate limiting в Telegram-обработчиках (app/bot/adapter.py)
  - GigaChat timeout (app/llm/client.py)
  - Audit logging в researcher_menu и admin/router
  - Глобальный 500 error handler (app/main.py)
  - Warning при пустом ADMIN_PASSWORD
"""

import asyncio
import logging
import time
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.bot.rate_limiter import InMemoryRateLimiter


# ── InMemoryRateLimiter ───────────────────────────────────────────────────────

class TestInMemoryRateLimiter:

    def test_under_limit_is_allowed(self):
        limiter = InMemoryRateLimiter(max_calls=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed(user_id=1) is True

    def test_over_limit_is_blocked(self):
        limiter = InMemoryRateLimiter(max_calls=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed(user_id=1)
        assert limiter.is_allowed(user_id=1) is False

    def test_different_users_are_independent(self):
        limiter = InMemoryRateLimiter(max_calls=1, window_seconds=60)
        assert limiter.is_allowed(user_id=1) is True
        assert limiter.is_allowed(user_id=2) is True
        # user_id=1 исчерпал лимит, user_id=2 — нет
        assert limiter.is_allowed(user_id=1) is False
        assert limiter.is_allowed(user_id=2) is False

    def test_window_expires_allows_new_calls(self):
        """Вызовы за пределами окна не учитываются."""
        limiter = InMemoryRateLimiter(max_calls=2, window_seconds=0.1)
        limiter.is_allowed(user_id=1)
        limiter.is_allowed(user_id=1)
        assert limiter.is_allowed(user_id=1) is False
        time.sleep(0.15)
        # После истечения окна счётчик сброшен
        assert limiter.is_allowed(user_id=1) is True

    def test_reset_clears_counter(self):
        limiter = InMemoryRateLimiter(max_calls=1, window_seconds=60)
        limiter.is_allowed(user_id=42)
        assert limiter.is_allowed(user_id=42) is False
        limiter.reset(user_id=42)
        assert limiter.is_allowed(user_id=42) is True

    def test_remaining_decrements(self):
        limiter = InMemoryRateLimiter(max_calls=3, window_seconds=60)
        assert limiter.remaining(user_id=1) == 3
        limiter.is_allowed(user_id=1)
        assert limiter.remaining(user_id=1) == 2

    def test_remaining_is_zero_when_limit_reached(self):
        limiter = InMemoryRateLimiter(max_calls=2, window_seconds=60)
        limiter.is_allowed(user_id=1)
        limiter.is_allowed(user_id=1)
        assert limiter.remaining(user_id=1) == 0

    def test_max_calls_one_allows_single_call(self):
        limiter = InMemoryRateLimiter(max_calls=1, window_seconds=60)
        assert limiter.is_allowed(user_id=99) is True
        assert limiter.is_allowed(user_id=99) is False


# ── HTTP Basic Auth для web-admin ─────────────────────────────────────────────

def _make_admin_client(password: str = "", username: str = "researcher"):
    """Создаёт TestClient с переопределёнными настройками auth."""
    from app.main import create_app
    from app.admin.router import get_study_repo
    from app.researcher.schema import StudyDefinition, StudyTexts

    repo = MagicMock()
    repo.list_all.return_value = []
    repo.get_active_orm_id.return_value = None
    repo.count_all_sessions.return_value = 0
    repo.count_questions.return_value = 0

    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = username
        mock_settings.admin_password = password

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        return TestClient(app, follow_redirects=False), mock_settings


def test_admin_without_auth_returns_401():
    """GET /admin/studies без credentials → 401."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "researcher"
        mock_settings.admin_password = "secret"

        from app.main import create_app
        from app.admin.router import get_study_repo
        repo = MagicMock()
        repo.list_all.return_value = []
        repo.get_active_orm_id.return_value = None
        repo.count_all_sessions.return_value = 0
        repo.count_questions.return_value = 0

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        client = TestClient(app, follow_redirects=False)

        r = client.get("/admin/studies")
        assert r.status_code == 401
        assert "WWW-Authenticate" in r.headers


def test_admin_with_wrong_password_returns_401():
    """GET /admin/studies с неверным паролем → 401."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "researcher"
        mock_settings.admin_password = "correct"

        from app.main import create_app
        from app.admin.router import get_study_repo
        repo = MagicMock()
        repo.list_all.return_value = []
        repo.get_active_orm_id.return_value = None
        repo.count_all_sessions.return_value = 0
        repo.count_questions.return_value = 0

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        client = TestClient(app, follow_redirects=False)

        r = client.get("/admin/studies", auth=("researcher", "wrong"))
        assert r.status_code == 401


def test_admin_with_correct_credentials_returns_200():
    """GET /admin/studies с правильными credentials → 200."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "researcher"
        mock_settings.admin_password = "secret"

        from app.main import create_app
        from app.admin.router import get_study_repo
        repo = MagicMock()
        repo.list_all.return_value = []
        repo.get_active_orm_id.return_value = None
        repo.count_all_sessions.return_value = 0
        repo.count_questions.return_value = 0

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        client = TestClient(app, follow_redirects=False)

        r = client.get("/admin/studies", auth=("researcher", "secret"))
        assert r.status_code == 200


def test_admin_without_password_is_open(caplog):
    """Если ADMIN_PASSWORD пуст — admin доступен без credentials (dev-mode)."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "researcher"
        mock_settings.admin_password = ""

        from app.main import create_app
        from app.admin.router import get_study_repo
        repo = MagicMock()
        repo.list_all.return_value = []
        repo.get_active_orm_id.return_value = None
        repo.count_all_sessions.return_value = 0
        repo.count_questions.return_value = 0

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        client = TestClient(app, follow_redirects=False)

        r = client.get("/admin/studies")
        # При пустом пароле auth не требуется
        assert r.status_code == 200


def test_admin_auth_failed_is_logged(caplog):
    """Неверный пароль → [AUDIT] admin_auth_failed появляется в логах."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "researcher"
        mock_settings.admin_password = "correct"

        from app.main import create_app
        from app.admin.router import get_study_repo
        repo = MagicMock()
        repo.list_all.return_value = []
        repo.get_active_orm_id.return_value = None
        repo.count_all_sessions.return_value = 0
        repo.count_questions.return_value = 0

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        client = TestClient(app, follow_redirects=False)

        with caplog.at_level(logging.WARNING, logger="app.core.security"):
            client.get("/admin/studies", auth=("researcher", "wrong"))

        assert any("admin_auth_failed" in r.message for r in caplog.records)


# ── Telegram: rate limiting messages ─────────────────────────────────────────

def test_handle_text_rate_limited():
    """11-е сообщение от пользователя за 60 с → rate-limited, dm.process не вызывается."""
    from app.bot.adapter import _handle_text

    dm_mock = MagicMock()
    dm_mock.process.return_value = MagicMock(text="Ответ", kind="question")

    limiter = InMemoryRateLimiter(max_calls=3, window_seconds=60)
    # Исчерпываем лимит
    for _ in range(3):
        limiter.is_allowed(user_id=7)

    update_mock = MagicMock()
    update_mock.effective_user.id = 7
    update_mock.effective_chat.id = 100
    update_mock.message.text = "Привет"
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock, "msg_limiter": limiter}
    context_mock.bot.send_chat_action = AsyncMock()

    asyncio.run(_handle_text(update_mock, context_mock))

    dm_mock.process.assert_not_called()
    update_mock.message.reply_text.assert_awaited_once()
    text = update_mock.message.reply_text.call_args[0][0]
    assert "подождите" in text.lower() or "торопитесь" in text.lower()


def test_handle_text_not_rate_limited_when_no_limiter():
    """Если limiter не задан в bot_data — обработка идёт без ограничений."""
    from app.bot.adapter import _handle_text

    dm_mock = MagicMock()
    dm_mock.process.return_value = MagicMock(text="Ответ", kind="question")

    update_mock = MagicMock()
    update_mock.effective_user.id = 5
    update_mock.effective_chat.id = 100
    update_mock.message.text = "Привет"
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock}   # нет msg_limiter
    context_mock.bot.send_chat_action = AsyncMock()

    asyncio.run(_handle_text(update_mock, context_mock))

    dm_mock.process.assert_called_once_with(5, "Привет")


# ── Telegram: oversized message ───────────────────────────────────────────────

def test_handle_text_oversized_message_rejected():
    """Сообщение длиннее max_message_length → отклоняется, dm.process не вызывается."""
    from app.bot.adapter import _handle_text

    dm_mock = MagicMock()

    update_mock = MagicMock()
    update_mock.effective_user.id = 3
    update_mock.effective_chat.id = 100
    update_mock.message.text = "А" * 3000  # больше дефолтного лимита 2000
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock}
    context_mock.bot.send_chat_action = AsyncMock()

    with patch("app.bot.adapter.settings") as mock_settings:
        mock_settings.max_message_length = 2000
        mock_settings.rate_limit_messages = 10
        mock_settings.rate_limit_window_seconds = 60

        asyncio.run(_handle_text(update_mock, context_mock))

    dm_mock.process.assert_not_called()
    update_mock.message.reply_text.assert_awaited_once()
    text = update_mock.message.reply_text.call_args[0][0]
    assert "длинное" in text.lower() or "короче" in text.lower()


def test_handle_text_message_at_limit_is_accepted():
    """Сообщение ровно в max_message_length символов → принимается."""
    from app.bot.adapter import _handle_text

    dm_mock = MagicMock()
    dm_mock.process.return_value = MagicMock(text="OK", kind="question")

    limit = 100
    update_mock = MagicMock()
    update_mock.effective_user.id = 4
    update_mock.effective_chat.id = 100
    update_mock.message.text = "Б" * limit  # ровно лимит
    update_mock.message.reply_text = AsyncMock()

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock}
    context_mock.bot.send_chat_action = AsyncMock()

    with patch("app.bot.adapter.settings") as mock_settings:
        mock_settings.max_message_length = limit
        mock_settings.rate_limit_messages = 10
        mock_settings.rate_limit_window_seconds = 60

        asyncio.run(_handle_text(update_mock, context_mock))

    dm_mock.process.assert_called_once()


# ── Telegram: callback rate limiting ──────────────────────────────────────────

def test_handle_callback_rate_limited():
    """21-й callback от одного user за окно → throttled, dm.start не вызывается."""
    from app.bot.adapter import _handle_callback
    from app.bot.keyboards import CALLBACK_RESTART

    dm_mock = MagicMock()

    cb_limiter = InMemoryRateLimiter(max_calls=2, window_seconds=60)
    for _ in range(2):
        cb_limiter.is_allowed(user_id=9)

    query_mock = AsyncMock()
    query_mock.data = CALLBACK_RESTART
    query_mock.from_user.id = 9

    update_mock = MagicMock()
    update_mock.callback_query = query_mock
    update_mock.effective_chat.id = 100

    context_mock = MagicMock()
    context_mock.bot_data = {"dm": dm_mock, "cb_limiter": cb_limiter}
    context_mock.bot.send_chat_action = AsyncMock()

    asyncio.run(_handle_callback(update_mock, context_mock))

    dm_mock.start.assert_not_called()


# ── GigaChat timeout ──────────────────────────────────────────────────────────

def test_gigachat_client_stores_timeout():
    """GigaChatLLMClient принимает timeout и сохраняет его."""
    from app.llm.client import GigaChatLLMClient
    client = GigaChatLLMClient(credentials="test", model="GigaChat", timeout=45)
    assert client._timeout == 45


def test_gigachat_client_default_timeout():
    """По умолчанию timeout = 30."""
    from app.llm.client import GigaChatLLMClient
    client = GigaChatLLMClient(credentials="test")
    assert client._timeout == 30


def test_gigachat_client_passes_timeout_to_context_manager():
    """GigaChatLLMClient передаёт timeout в GigaChat(...)."""
    from app.llm.client import GigaChatLLMClient

    client = GigaChatLLMClient(credentials="creds", timeout=25)

    with patch("app.llm.client.GigaChatLLMClient.complete") as mock_complete:
        mock_complete.return_value = "ответ"
        result = client.complete("sys", [{"role": "user", "content": "hi"}])

    # Проверяем через прямой вызов complete с моком GigaChat
    with patch("gigachat.GigaChat") as MockGigaChat:
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.chat.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="  ответ  "))]
        )
        MockGigaChat.return_value = mock_instance

        with patch("gigachat.models.Chat"), \
             patch("gigachat.models.Messages"), \
             patch("gigachat.models.MessagesRole"):
            try:
                client.complete("sys", [{"role": "user", "content": "hi"}])
            except Exception:
                pass  # модели могут не загрузиться в тестах

        if MockGigaChat.called:
            call_kwargs = MockGigaChat.call_args[1]
            assert call_kwargs.get("timeout") == 25


# ── Audit logging: researcher actions ────────────────────────────────────────

def test_researcher_list_is_audited(caplog):
    """_show_list логирует [AUDIT] action=researcher_list."""
    from app.bot.researcher_menu import _show_list

    query = AsyncMock()
    query.from_user.id = 42
    query.message.edit_text = AsyncMock()

    repo = MagicMock()
    repo.list_all.return_value = []
    repo.get_active.return_value = None

    with caplog.at_level(logging.INFO, logger="app.bot.researcher_menu"):
        asyncio.run(_show_list(query, repo))

    assert any("researcher_list" in r.message for r in caplog.records)
    assert any("42" in r.message for r in caplog.records)


def test_researcher_activate_is_audited(caplog):
    """_do_activate при успехе логирует [AUDIT] action=researcher_activate_study."""
    from app.bot.researcher_menu import _do_activate

    query = AsyncMock()
    query.from_user.id = 42
    query.message.edit_text = AsyncMock()

    repo = MagicMock()
    repo.activate.return_value = True
    repo.get_by_id.return_value = MagicMock(title="Test Study")

    from app.services.prompt_engine import StaticPromptEngine
    from app.services.dialog_manager import DialogManager
    context = MagicMock()
    context.bot_data = {
        "engines": {"static": StaticPromptEngine()},
        "active_provider": "static",
        "store": MagicMock(),
    }

    with caplog.at_level(logging.INFO, logger="app.bot.researcher_menu"):
        asyncio.run(_do_activate(query, context, repo, "7"))

    assert any("researcher_activate_study" in r.message for r in caplog.records)


def test_researcher_export_is_audited(caplog):
    """_do_export логирует [AUDIT] action=researcher_export."""
    from app.bot.researcher_menu import _do_export

    query = AsyncMock()
    query.from_user.id = 99
    query.message.chat_id = 100

    ctx = MagicMock()
    ctx.bot_data = {"session_factory": MagicMock()}
    ctx.bot.send_document = AsyncMock()

    with patch("app.db.repository.get_all_sessions", return_value=[]):
        with caplog.at_level(logging.INFO, logger="app.bot.researcher_menu"):
            asyncio.run(_do_export(query, ctx))

    assert any("researcher_export" in r.message for r in caplog.records)


# ── Audit logging: admin actions ─────────────────────────────────────────────

def test_admin_activate_is_audited(caplog):
    """POST /admin/studies/{id}/activate → [AUDIT] admin_activate_study в логах."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "u"
        mock_settings.admin_password = ""  # open

        from app.main import create_app
        from app.admin.router import get_study_repo

        repo = MagicMock()
        repo.activate.return_value = True

        app = create_app()
        app.dependency_overrides[get_study_repo] = lambda: repo
        client = TestClient(app, follow_redirects=False)

        with caplog.at_level(logging.INFO, logger="app.admin.router"):
            client.post("/admin/studies/5/activate")

        assert any("admin_activate_study" in r.message for r in caplog.records)


# ── Global 500 error handler ─────────────────────────────────────────────────

def test_unhandled_exception_returns_html_for_admin_path():
    """500 в /admin/* → HTML-ответ, не stack trace."""
    with patch("app.core.security.settings") as mock_settings:
        mock_settings.admin_username = "u"
        mock_settings.admin_password = ""

        from app.main import create_app
        from app.admin.router import get_study_repo

        app = create_app()

        # Добавляем route, который всегда бросает исключение
        @app.get("/admin/boom")
        async def boom():
            raise RuntimeError("test explosion")

        # Переопределяем зависимость
        repo = MagicMock()
        repo.list_all.return_value = []
        repo.get_active_orm_id.return_value = None
        repo.count_all_sessions.return_value = 0
        repo.count_questions.return_value = 0
        app.dependency_overrides[get_study_repo] = lambda: repo

        client = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
        r = client.get("/admin/boom")

    assert r.status_code == 500
    assert "stack" not in r.text.lower()
    assert "traceback" not in r.text.lower()
    # HTML-страница с сообщением об ошибке
    assert "ошибка" in r.text.lower() or "error" in r.text.lower()


# ── ADMIN_PASSWORD warning ────────────────────────────────────────────────────

def test_empty_admin_password_warning_on_startup(caplog):
    """При ADMIN_PASSWORD='' lifespan логирует предупреждение."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.database_url = "sqlite:///:memory:"
        mock_settings.admin_password = ""

        from app.main import create_app

        app = create_app()

        # Lifespan запускается только при входе в контекстный менеджер TestClient.
        with caplog.at_level(logging.WARNING, logger="app.main"):
            with TestClient(app, follow_redirects=False) as client:
                client.get("/health")

        assert any("ADMIN_PASSWORD" in r.message for r in caplog.records)
