"""Тесты для app/researcher/schema.py — validate()."""

import pytest

from app.researcher.schema import QuestionDef, StudyDefinition, StudyTexts, validate


# ── Фикстуры ─────────────────────────────────────────────────────────────────

def _texts(**kwargs) -> StudyTexts:
    defaults = dict(
        greeting="Здравствуйте!",
        closing="Спасибо!",
        redirect="Понимаю вас.\n\n",
        help="Просто отвечайте.",
        already_done="Уже завершено.",
    )
    defaults.update(kwargs)
    return StudyTexts(**defaults)


def _sd(questions=None, title="Тестовое исследование", texts=None, description="") -> StudyDefinition:
    if questions is None:
        questions = (QuestionDef("q1", "Вопрос 1?"), QuestionDef("q2", "Вопрос 2?"))
    return StudyDefinition(
        title=title,
        description=description,
        questions=tuple(questions),
        texts=texts or _texts(),
    )


# ── Валидная конфигурация ─────────────────────────────────────────────────────

def test_valid_study_has_no_errors():
    errors = validate(_sd())
    assert errors == []


def test_valid_study_single_question():
    errors = validate(_sd(questions=[QuestionDef("q1", "Расскажите что-нибудь.")]))
    assert errors == []


def test_valid_study_ten_questions():
    qs = [QuestionDef(f"q{i}", f"Вопрос {i}?") for i in range(1, 11)]
    errors = validate(_sd(questions=qs))
    assert errors == []


# ── title ─────────────────────────────────────────────────────────────────────

def test_empty_title_is_error():
    errors = validate(_sd(title=""))
    assert any("title" in e for e in errors)


def test_whitespace_title_is_error():
    errors = validate(_sd(title="   "))
    assert any("title" in e for e in errors)


def test_too_long_title_is_error():
    errors = validate(_sd(title="А" * 201))
    assert any("title" in e for e in errors)


def test_title_exactly_at_limit():
    errors = validate(_sd(title="А" * 200))
    assert errors == []


# ── questions ─────────────────────────────────────────────────────────────────

def test_zero_questions_is_error():
    errors = validate(_sd(questions=[]))
    assert any("questions" in e for e in errors)


def test_eleven_questions_is_error():
    qs = [QuestionDef(f"q{i}", f"Вопрос {i}?") for i in range(1, 12)]
    errors = validate(_sd(questions=qs))
    assert any("questions" in e for e in errors)


def test_duplicate_question_id_is_error():
    qs = [QuestionDef("q1", "Первый"), QuestionDef("q1", "Дубль")]
    errors = validate(_sd(questions=qs))
    assert any("дублирующийся" in e for e in errors)


def test_question_id_with_uppercase_is_error():
    errors = validate(_sd(questions=[QuestionDef("Q1", "Вопрос?")]))
    assert any("[a-z0-9_]" in e for e in errors)


def test_question_id_with_space_is_error():
    errors = validate(_sd(questions=[QuestionDef("my question", "Вопрос?")]))
    assert any("[a-z0-9_]" in e for e in errors)


def test_question_same_id_in_different_studies_is_ok():
    """q1 можно использовать в любом Study — уникальность только внутри одного."""
    errors = validate(_sd(questions=[QuestionDef("q1", "Вопрос?")]))
    assert errors == []


def test_empty_question_text_is_error():
    errors = validate(_sd(questions=[QuestionDef("q1", "")]))
    assert any("text" in e for e in errors)


def test_too_long_question_text_is_error():
    errors = validate(_sd(questions=[QuestionDef("q1", "А" * 2001)]))
    assert any("text" in e for e in errors)


# ── texts ─────────────────────────────────────────────────────────────────────

def test_empty_greeting_is_error():
    errors = validate(_sd(texts=_texts(greeting="")))
    assert any("texts.greeting" in e for e in errors)


def test_empty_closing_is_error():
    errors = validate(_sd(texts=_texts(closing="")))
    assert any("texts.closing" in e for e in errors)


def test_empty_redirect_is_error():
    errors = validate(_sd(texts=_texts(redirect="")))
    assert any("texts.redirect" in e for e in errors)


def test_too_long_text_is_error():
    errors = validate(_sd(texts=_texts(help="А" * 3001)))
    assert any("texts.help" in e for e in errors)


def test_multiple_errors_all_reported():
    """Все ошибки собираются, не останавливаясь на первой."""
    qs = [QuestionDef("q1", "q1"), QuestionDef("q1", "дубль")]  # дубль
    sd = _sd(title="", questions=qs, texts=_texts(greeting=""))
    errors = validate(sd)
    assert len(errors) >= 3  # title + дубль + greeting
