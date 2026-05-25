import pytest

from app.services.dialog_manager import DialogManager
from app.services.session_store import InMemorySessionStore
from app.services import interview_script as script


@pytest.fixture
def dm() -> DialogManager:
    return DialogManager(store=InMemorySessionStore())


def test_start_returns_intro_with_first_question(dm):
    reply = dm.start(user_id=1)
    assert script.QUESTIONS[0].text in reply


def test_first_answer_leads_to_second_question(dm):
    dm.start(user_id=1)
    reply = dm.process(1, "мой ответ")
    assert script.QUESTIONS[1].text in reply


def test_all_answers_collected_with_correct_ids(dm):
    dm.start(user_id=1)
    dm.process(1, "ответ на q1")
    dm.process(1, "ответ на q2")
    session = dm._store.get_or_create(1)
    assert session.answers["q1"] == "ответ на q1"
    assert session.answers["q2"] == "ответ на q2"


def test_last_answer_triggers_closing(dm):
    dm.start(user_id=1)
    dm.process(1, "a1")
    dm.process(1, "a2")
    reply = dm.process(1, "a3")
    assert script.CLOSING in reply


def test_session_marked_finished_after_closing(dm):
    dm.start(user_id=1)
    for msg in ["a1", "a2", "a3"]:
        dm.process(1, msg)
    session = dm._store.get_or_create(1)
    assert session.finished is True


def test_finished_session_returns_already_done(dm):
    dm.start(user_id=1)
    for msg in ["a1", "a2", "a3"]:
        dm.process(1, msg)
    reply = dm.process(1, "ещё")
    assert script.ALREADY_DONE in reply


# ── begin() ──────────────────────────────────────────────────────────────────

def test_begin_returns_first_question(dm):
    """begin() возвращает первый вопрос без приветствия."""
    result = dm.begin(user_id=1)
    assert script.QUESTIONS[0].text in result.text
    assert result.kind == "question"


def test_begin_does_not_include_greeting(dm):
    """begin() НЕ содержит текст GREETING (он уже был показан /start-экраном)."""
    result = dm.begin(user_id=1)
    # GREETING содержит «бот-интервьюер» — его не должно быть в begin()
    assert "бот-интервьюер" not in result.text


def test_begin_resets_finished_session(dm):
    """begin() после завершённой сессии сбрасывает её и возвращает Q1."""
    dm.start(user_id=1)
    for msg in ["a1", "a2", "a3"]:
        dm.process(1, msg)
    result = dm.begin(user_id=1)
    assert script.QUESTIONS[0].text in result.text
    assert dm._store.get_or_create(1).finished is False


def test_begin_answer_after_begin_advances_normally(dm):
    """После begin() нормальный ответ продвигает интервью ко второму вопросу."""
    dm.begin(user_id=1)
    reply = dm.process(1, "мой ответ")
    assert script.QUESTIONS[1].text in reply


def test_start_resets_finished_session(dm):
    dm.start(user_id=1)
    for msg in ["a1", "a2", "a3"]:
        dm.process(1, msg)
    reply = dm.start(user_id=1)
    assert script.QUESTIONS[0].text in reply
    assert dm._store.get_or_create(1).finished is False


def test_two_users_are_independent(dm):
    dm.start(user_id=1)
    dm.start(user_id=2)
    dm.process(1, "ответ пользователя 1")
    session2 = dm._store.get_or_create(2)
    assert session2.current_question_index == 0


# ── Off-topic redirect ───────────────────────────────────────────────────────

def test_off_topic_returns_redirect_with_current_question(dm):
    """Уклонение → редирект содержит текущий вопрос, не следующий."""
    dm.start(user_id=1)
    reply = dm.process(1, "позови оператора")
    assert script.QUESTIONS[0].text in reply
    assert script.REDIRECT in reply


def test_off_topic_does_not_advance_question_index(dm):
    """После уклонения индекс вопроса не меняется."""
    dm.start(user_id=1)
    dm.process(1, "позови оператора")
    session = dm._store.get_or_create(1)
    assert session.current_question_index == 0


def test_off_topic_answer_not_saved(dm):
    """Уклончивый текст НЕ сохраняется как ответ на вопрос."""
    dm.start(user_id=1)
    dm.process(1, "поговорим про другую тему")
    session = dm._store.get_or_create(1)
    assert "q1" not in session.answers


def test_valid_answer_after_off_topic_advances_normally(dm):
    """После редиректа корректный ответ принимается и двигает интервью."""
    dm.start(user_id=1)
    dm.process(1, "позови оператора")          # уклонение
    reply = dm.process(1, "использую телефон каждый день")   # валидный ответ
    assert script.QUESTIONS[1].text in reply   # следующий вопрос


def test_is_off_topic_detection_phrases(dm):
    """Разные фразы уклонения все распознаются."""
    phrases = [
        "позови оператора",
        "поговорим про другую тему",
        "Давай поговорим про машины",
        "не хочу про это говорить",
        "не интересно",
        "стоп",
        "другую тему давайте",
    ]
    for phrase in phrases:
        dm.start(user_id=99)
        reply = dm.process(99, phrase)
        assert script.QUESTIONS[0].text in reply, f"Не сработал редирект для: {phrase!r}"


# ── Clarifying question ───────────────────────────────────────────────────────

def test_clarifying_question_returns_clarify_kind(dm):
    """Уточняющий вопрос → kind="clarify"."""
    dm.start(user_id=1)
    result = dm.process(1, "А вас интересуют только приложения или сайты тоже?")
    assert result.kind == "clarify"


def test_clarifying_question_repeats_current_question(dm):
    """Ответ на уточняющий вопрос содержит текст текущего вопроса."""
    dm.start(user_id=1)
    result = dm.process(1, "Что вы имеете в виду под этим вопросом?")
    assert script.QUESTIONS[0].text in result.text


def test_clarifying_question_does_not_advance_index(dm):
    """После уточняющего вопроса индекс не двигается."""
    dm.start(user_id=1)
    dm.process(1, "Можете уточнить, что нужно описать?")
    session = dm._store.get_or_create(1)
    assert session.current_question_index == 0


def test_clarifying_question_answer_not_saved(dm):
    """Уточняющий вопрос не сохраняется как ответ."""
    dm.start(user_id=1)
    dm.process(1, "А вас интересуют именно мобильные приложения?")
    session = dm._store.get_or_create(1)
    assert "q1" not in session.answers


def test_valid_answer_after_clarification_advances(dm):
    """После разъяснения нормальный ответ принимается и двигает интервью."""
    dm.start(user_id=1)
    dm.process(1, "Что именно вас интересует?")   # уточнение
    reply = dm.process(1, "Использую ChatGPT для работы")  # ответ
    assert script.QUESTIONS[1].text in reply


def test_non_question_not_treated_as_clarification(dm):
    """Обычный ответ без «?» не попадает в clarify-ветку."""
    dm.start(user_id=1)
    result = dm.process(1, "Я использую ChatGPT и Яндекс Алису")
    assert result.kind == "question"   # следующий вопрос, не clarify
