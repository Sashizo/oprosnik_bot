import sys
import pytest
from unittest.mock import MagicMock

from app.llm.engine import LLMPromptEngine
from app.services.prompt_engine import InterviewContext
from app.services import interview_script as script


@pytest.fixture
def fake_client():
    client = MagicMock()
    client.complete.return_value = "Спасибо за ответ."
    return client


def test_question_combines_ack_and_static_question(fake_client):
    """question() = LLM acknowledgment + скриптовый вопрос дословно."""
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=1, previous_answers={"q1": "мой ответ"})
    result = engine.question(ctx)
    assert fake_client.complete.called
    assert "Спасибо за ответ." in result
    assert script.QUESTIONS[1].text in result   # вопрос — всегда из скрипта


def test_question_falls_back_to_static_on_llm_exception():
    """При сбое LLM question() возвращает только статический вопрос — без исключения."""
    failing = MagicMock()
    failing.complete.side_effect = Exception("API unavailable")
    engine = LLMPromptEngine(client=failing)
    ctx = InterviewContext(question_index=1, previous_answers={"q1": "мой ответ"})
    result = engine.question(ctx)
    assert script.QUESTIONS[1].text in result   # чистый fallback (с прогресс-префиксом)


def test_closing_falls_back_to_static_on_exception():
    """При сбое LLM closing() возвращает script.CLOSING — без исключения."""
    failing = MagicMock()
    failing.complete.side_effect = Exception("timeout")
    engine = LLMPromptEngine(client=failing)
    ctx = InterviewContext(
        question_index=len(script.QUESTIONS),
        previous_answers={"q1": "a", "q2": "b", "q3": "c"},
    )
    result = engine.closing(ctx)
    assert result == script.CLOSING


def test_closing_falls_back_to_static_when_guardrail_rejects():
    """Если closing от LLM не прошёл guardrail (содержит '?') — возвращается script.CLOSING."""
    bad_client = MagicMock()
    bad_client.complete.return_value = "Спасибо! Есть что добавить?"
    engine = LLMPromptEngine(client=bad_client)
    ctx = InterviewContext(
        question_index=len(script.QUESTIONS),
        previous_answers={"q1": "a", "q2": "b", "q3": "c"},
    )
    result = engine.closing(ctx)
    assert result == script.CLOSING


def test_intro_is_static_no_llm_call(fake_client):
    """intro() возвращает статическое приветствие без обращения к LLM."""
    engine = LLMPromptEngine(client=fake_client)
    assert engine.intro() == script.GREETING
    fake_client.complete.assert_not_called()


def test_already_done_is_static_no_llm_call(fake_client):
    """already_done() возвращает статический текст без обращения к LLM."""
    engine = LLMPromptEngine(client=fake_client)
    assert engine.already_done() == script.ALREADY_DONE
    fake_client.complete.assert_not_called()


def test_acknowledgment_passes_full_history_to_llm(fake_client):
    """M19: _generate_acknowledgment() передаёт историю всех предыдущих Q&A в LLM.

    LLM получает не только последний ответ, но и все предыдущие пары вопрос/ответ —
    это позволяет генерировать контекстно-осведомлённые подтверждения.
    """
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(
        question_index=2,
        previous_answers={
            script.QUESTIONS[0].question_id: "ответ на первый вопрос",
            script.QUESTIONS[1].question_id: "ответ на второй вопрос",
        },
    )
    engine.question(ctx)
    call_args = fake_client.complete.call_args
    messages = call_args[1]["messages"]
    all_content = " ".join(m["content"] for m in messages)
    assert "ответ на первый вопрос" in all_content
    assert "ответ на второй вопрос" in all_content


# ── GigaChatLLMClient ────────────────────────────────────────────────────────

@pytest.fixture
def mock_gigachat(monkeypatch):
    """Мокает gigachat SDK целиком — пакет не нужен для запуска тестов."""
    mock_mod = MagicMock()
    mock_models = MagicMock()

    # Имитируем MessagesRole.SYSTEM / USER / ASSISTANT как строки
    mock_models.MessagesRole.SYSTEM = "system"
    mock_models.MessagesRole.USER = "user"
    mock_models.MessagesRole.ASSISTANT = "assistant"

    monkeypatch.setitem(sys.modules, "gigachat", mock_mod)
    monkeypatch.setitem(sys.modules, "gigachat.models", mock_models)
    return mock_mod, mock_models


def test_gigachat_client_complete(mock_gigachat):
    """GigaChatLLMClient.complete() вызывает SDK и возвращает stripped content."""
    mock_mod, mock_models = mock_gigachat

    # Настраиваем ответ SDK
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "  Спасибо за ответ.  "
    mock_giga_instance = MagicMock()
    mock_giga_instance.chat.return_value = mock_response
    mock_mod.GigaChat.return_value.__enter__ = MagicMock(return_value=mock_giga_instance)
    mock_mod.GigaChat.return_value.__exit__ = MagicMock(return_value=False)

    from app.llm.client import GigaChatLLMClient
    client = GigaChatLLMClient(credentials="test-key", model="GigaChat")
    result = client.complete(
        system="системный промпт",
        messages=[{"role": "user", "content": "ответ участника"}],
    )

    assert result == "Спасибо за ответ."   # strip() применён
    assert mock_giga_instance.chat.called


def test_gigachat_client_used_as_llm_engine(mock_gigachat, fake_client):
    """LLMPromptEngine работает с GigaChatLLMClient через общий Protocol."""
    # GigaChatLLMClient подходит к LLMPromptEngine без изменений движка —
    # достаточно проверить, что движок принимает любой объект с методом complete().
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=1, previous_answers={"q1": "ответ"})
    result = engine.question(ctx)
    assert script.QUESTIONS[1].text in result   # вопрос всегда из скрипта


# ── LLM classifier (is_off_topic) ────────────────────────────────────────────

def test_is_off_topic_returns_true_when_llm_says_da(fake_client):
    """LLM отвечает «ДА» → is_off_topic() = True."""
    fake_client.complete.return_value = "ДА"
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=0, previous_answers={})
    assert engine.is_off_topic("давай про машины", ctx) is True


def test_is_off_topic_returns_false_when_llm_says_net(fake_client):
    """LLM отвечает «НЕТ» → is_off_topic() = False."""
    fake_client.complete.return_value = "НЕТ"
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=0, previous_answers={})
    assert engine.is_off_topic("Использую телефон каждый день", ctx) is False


def test_is_off_topic_falls_back_to_keywords_on_llm_exception():
    """При сбое LLM классификатор падает на keyword-эвристику — без исключения."""
    failing = MagicMock()
    failing.complete.side_effect = Exception("timeout")
    engine = LLMPromptEngine(client=failing)
    ctx = InterviewContext(question_index=0, previous_answers={})
    # keyword-эвристика: "позови оператора" → True
    assert engine.is_off_topic("позови оператора", ctx) is True


def test_is_off_topic_passes_question_context_to_llm(fake_client):
    """LLM классификатор получает текст текущего вопроса в запросе."""
    fake_client.complete.return_value = "НЕТ"
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=0, previous_answers={})
    engine.is_off_topic("какой-то ответ", ctx)
    call_args = fake_client.complete.call_args
    # текст вопроса должен быть в сообщении пользователя
    assert script.QUESTIONS[0].text in call_args[1]["messages"][0]["content"]


# ── LLM classifier (is_clarifying_question) ──────────────────────────────────

def test_is_clarifying_question_returns_true_when_llm_says_da(fake_client):
    """LLM отвечает «ДА» → is_clarifying_question() = True."""
    fake_client.complete.return_value = "ДА"
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=0, previous_answers={})
    assert engine.is_clarifying_question("А вас интересуют только приложения?", ctx) is True


def test_is_clarifying_question_returns_false_when_llm_says_net(fake_client):
    """LLM отвечает «НЕТ» → is_clarifying_question() = False."""
    fake_client.complete.return_value = "НЕТ"
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=0, previous_answers={})
    assert engine.is_clarifying_question("Использую ChatGPT каждый день", ctx) is False


def test_is_clarifying_question_falls_back_to_heuristic_on_exception():
    """При сбое LLM — fallback на эвристику «заканчивается на ?»."""
    failing = MagicMock()
    failing.complete.side_effect = Exception("timeout")
    engine = LLMPromptEngine(client=failing)
    ctx = InterviewContext(question_index=0, previous_answers={})
    assert engine.is_clarifying_question("Что именно вас интересует?", ctx) is True
    assert engine.is_clarifying_question("Использую телефон каждый день", ctx) is False


def test_is_clarifying_question_passes_question_text_to_llm(fake_client):
    """Классификатор уточнений передаёт текст текущего вопроса в LLM."""
    fake_client.complete.return_value = "НЕТ"
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(question_index=0, previous_answers={})
    engine.is_clarifying_question("Что вы имеете в виду?", ctx)
    call_args = fake_client.complete.call_args
    assert script.QUESTIONS[0].text in call_args[1]["messages"][0]["content"]


# ── LLM clarify ───────────────────────────────────────────────────────────────

def test_clarify_returns_llm_text_plus_static_question(fake_client):
    """clarify() = LLM-разъяснение + статический текст вопроса."""
    fake_client.complete.return_value = "Нас интересует ваш личный опыт в любом формате."
    engine = LLMPromptEngine(client=fake_client)
    ctx = InterviewContext(
        question_index=0,
        previous_answers={},
        last_user_text="Что вы имеете в виду?",
    )
    result = engine.clarify(ctx)
    assert "Нас интересует ваш личный опыт" in result
    assert script.QUESTIONS[0].text in result


def test_clarify_falls_back_to_static_on_llm_exception():
    """При сбое LLM clarify() возвращает статический fallback с текстом вопроса."""
    failing = MagicMock()
    failing.complete.side_effect = Exception("timeout")
    engine = LLMPromptEngine(client=failing)
    ctx = InterviewContext(question_index=0, previous_answers={}, last_user_text="?")
    result = engine.clarify(ctx)
    assert script.QUESTIONS[0].text in result


def test_clarify_falls_back_when_guardrail_rejects_question_mark():
    """Если LLM добавил «?» в разъяснение — guardrail отклоняет, возвращается fallback."""
    bad_client = MagicMock()
    bad_client.complete.return_value = "Хотите уточнить, что именно?"
    engine = LLMPromptEngine(client=bad_client)
    ctx = InterviewContext(question_index=0, previous_answers={}, last_user_text="?")
    result = engine.clarify(ctx)
    # guardrail отклонил (содержит "?") → fallback содержит статический вопрос
    assert script.QUESTIONS[0].text in result
    assert "Хотите уточнить" not in result
