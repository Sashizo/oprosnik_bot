"""Модель сценария исследования и функция валидации.

StudyDefinition — неизменяемый dataclass, описывающий полный сценарий:
  вопросы, тексты и метаданные исследования.
validate(sd) → list[str] — список ошибок; пустой список означает корректную конфигурацию.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Константы валидации ───────────────────────────────────────────────────────

_ID_PATTERN = re.compile(r'^[a-z0-9_]+$')
_MAX_TITLE = 200
_MAX_QUESTION_ID = 50
_MAX_QUESTION_TEXT = 2000
_MAX_TEXT = 3000
_MIN_QUESTIONS = 1
_MAX_QUESTIONS = 10


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QuestionDef:
    """Один вопрос сценария исследования.

    question_id — уникальный внутри одного Study идентификатор ([a-z0-9_]).
    Глобальная уникальность между разными исследованиями не требуется:
    q1/q2/q3 можно использовать в любом новом Study.
    """

    question_id: str
    text: str


@dataclass(frozen=True)
class StudyTexts:
    """Служебные тексты интерфейса бота для конкретного исследования."""

    greeting: str
    closing: str
    redirect: str
    help: str
    already_done: str


@dataclass(frozen=True)
class StudyDefinition:
    """Полное описание сценария исследования.

    study_id заполняется только после записи в БД (StudyRepository.create).
    В памяти (до записи) study_id = None.
    """

    title: str
    description: str
    questions: tuple[QuestionDef, ...]
    texts: StudyTexts
    study_id: int | None = None


# ── Валидация ─────────────────────────────────────────────────────────────────

def validate(sd: StudyDefinition) -> list[str]:
    """Проверяет StudyDefinition на соответствие всем правилам.

    Возвращает список ошибок на русском языке.
    Пустой список — конфигурация корректна.
    """
    errors: list[str] = []

    # ── title ─────────────────────────────────────────────────────────────────
    if not sd.title.strip():
        errors.append("title: не может быть пустым")
    elif len(sd.title) > _MAX_TITLE:
        errors.append(f"title: превышает {_MAX_TITLE} символов (сейчас {len(sd.title)})")

    # ── questions ─────────────────────────────────────────────────────────────
    if len(sd.questions) < _MIN_QUESTIONS:
        errors.append(f"questions: требуется минимум {_MIN_QUESTIONS} вопрос")
    elif len(sd.questions) > _MAX_QUESTIONS:
        errors.append(f"questions: максимум {_MAX_QUESTIONS} вопросов (сейчас {len(sd.questions)})")

    seen_ids: set[str] = set()
    for i, q in enumerate(sd.questions):
        prefix = f"questions[{i}]"

        if not q.question_id:
            errors.append(f"{prefix}: id не может быть пустым")
        elif not _ID_PATTERN.match(q.question_id):
            errors.append(
                f"{prefix} (id={q.question_id!r}): id должен содержать только символы [a-z0-9_]"
            )
        elif len(q.question_id) > _MAX_QUESTION_ID:
            errors.append(
                f"{prefix} (id={q.question_id!r}): id превышает {_MAX_QUESTION_ID} символов"
            )

        if q.question_id in seen_ids:
            errors.append(f"{prefix} (id={q.question_id!r}): дублирующийся id")
        else:
            seen_ids.add(q.question_id)

        if not q.text.strip():
            errors.append(f"{prefix} (id={q.question_id!r}): text не может быть пустым")
        elif len(q.text) > _MAX_QUESTION_TEXT:
            errors.append(
                f"{prefix} (id={q.question_id!r}): text превышает {_MAX_QUESTION_TEXT} символов"
            )

    # ── texts ─────────────────────────────────────────────────────────────────
    text_checks: list[tuple[str, str]] = [
        ("greeting", sd.texts.greeting),
        ("closing", sd.texts.closing),
        ("redirect", sd.texts.redirect),
        ("help", sd.texts.help),
        ("already_done", sd.texts.already_done),
    ]
    for field_name, value in text_checks:
        if not value.strip():
            errors.append(f"texts.{field_name}: не может быть пустым")
        elif len(value) > _MAX_TEXT:
            errors.append(
                f"texts.{field_name}: превышает {_MAX_TEXT} символов (сейчас {len(value)})"
            )

    return errors
