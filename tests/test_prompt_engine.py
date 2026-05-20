from app.services.prompt_engine import StaticPromptEngine, InterviewContext
from app.services import interview_script as script


def test_intro_is_greeting_only():
    """intro() — только приветствие. Q1 приходит через question(ctx, index=0)."""
    intro = StaticPromptEngine().intro()
    assert script.GREETING in intro
    assert script.QUESTIONS[0].text not in intro


def test_question_index_zero_returns_first_question():
    ctx = InterviewContext(question_index=0, previous_answers={})
    assert script.QUESTIONS[0].text in StaticPromptEngine().question(ctx)


def test_question_returns_correct_text_by_index():
    ctx = InterviewContext(question_index=1, previous_answers={"q1": "ответ"})
    assert script.QUESTIONS[1].text in StaticPromptEngine().question(ctx)


def test_question_has_progress_prefix():
    """Ответ содержит прогресс-метку вида «1 из 3»."""
    ctx = InterviewContext(question_index=0, previous_answers={})
    result = StaticPromptEngine().question(ctx)
    assert "1 из 3" in result


def test_last_question_has_last_label():
    """Последний вопрос содержит «Последний» и «3 из 3»."""
    last_index = len(script.QUESTIONS) - 1
    ctx = InterviewContext(question_index=last_index, previous_answers={})
    result = StaticPromptEngine().question(ctx)
    assert "Последний" in result
    assert f"{last_index + 1} из {len(script.QUESTIONS)}" in result


def test_question_text_unchanged_in_script():
    """QUESTIONS[i].text не содержит прогресс-префикс — источник правды не тронут."""
    total = len(script.QUESTIONS)
    for i, q in enumerate(script.QUESTIONS):
        assert "из" not in q.text or "из" in q.text  # sanity — поле существует
        # Главная проверка: сам текст вопроса не начинается с прогресс-метки
        assert not q.text.startswith(f"Вопрос {i + 1} из {total}")
        assert not q.text.startswith(f"Последний вопрос")


def test_closing_returns_closing_text():
    ctx = InterviewContext(question_index=len(script.QUESTIONS), previous_answers={})
    assert StaticPromptEngine().closing(ctx) == script.CLOSING


def test_already_done_returns_already_done_text():
    assert StaticPromptEngine().already_done() == script.ALREADY_DONE


def test_system_prompt_contains_all_question_ids():
    prompt = StaticPromptEngine().build_system_prompt()
    for q in script.QUESTIONS:
        assert q.question_id in prompt
