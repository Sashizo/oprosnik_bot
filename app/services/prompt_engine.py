from dataclasses import dataclass, field
from typing import Protocol

from app.services import interview_script as script
from app.llm.guardrails import is_off_topic_response


@dataclass
class InterviewContext:
    """Контекст беседы, передаваемый движку для формирования ответа бота.

    question_index    — индекс следующего вопроса (0-based).
    previous_answers  — question_id → текст ответа; тот же тип, что Session.answers.
    last_user_text    — последнее сообщение пользователя (None при старте).
    """

    question_index: int
    previous_answers: dict[str, str] = field(default_factory=dict)
    last_user_text: str | None = None


class PromptEngine(Protocol):
    """Протокол формирования текстов интервью.

    StaticPromptEngine — детерминированная реализация.
    LLMPromptEngine    — с LLM-acknowledgment и LLM-closing.

    Методы questions() и total_questions() — единственный источник правды
    о списке вопросов для DialogManager: DialogManager не импортирует
    interview_script напрямую и не хранит StudyDefinition отдельно.
    """

    def intro(self) -> str: ...
    def question(self, ctx: InterviewContext) -> str: ...
    def closing(self, ctx: InterviewContext) -> str: ...
    def already_done(self) -> str: ...
    def redirect(self, ctx: InterviewContext) -> str: ...
    def is_off_topic(self, user_text: str, ctx: InterviewContext) -> bool: ...
    def build_system_prompt(self) -> str: ...
    def questions(self) -> tuple: ...
    def total_questions(self) -> int: ...


class StaticPromptEngine:
    """Детерминированный движок: возвращает фиксированные тексты.

    При study=None — берёт все тексты и вопросы из interview_script (legacy-режим).
    При study=<StudyDefinition> — берёт из StudyDefinition.

    build_system_prompt() подготовлен для LLM-клиента, но не вызывается
    в текущем runtime-потоке DialogManager.
    """

    def __init__(self, study=None) -> None:
        """
        study: app.researcher.schema.StudyDefinition | None.
               None → legacy-режим (interview_script.py как источник правды).
        """
        self._study = study

    # ── Вопросы: единственный источник правды для DialogManager ──────────────

    def questions(self) -> tuple:
        """Кортеж вопросов активного сценария.

        При study=None возвращает script.QUESTIONS как кортеж (Question-объекты).
        При study=<StudyDefinition> возвращает study.questions (кортеж QuestionDef).
        Оба типа имеют атрибуты question_id и text — совместимы с DialogManager.
        """
        if self._study is not None:
            return self._study.questions
        return tuple(script.QUESTIONS)

    def total_questions(self) -> int:
        """Общее число вопросов в сценарии."""
        return len(self.questions())

    # ── PromptEngine Protocol ─────────────────────────────────────────────────

    def intro(self) -> str:
        """Только приветствие. Q1 всегда приходит через question(ctx, index=0)."""
        if self._study is not None:
            return self._study.texts.greeting
        return script.GREETING

    def question(self, ctx: InterviewContext) -> str:
        """Текст вопроса с прогресс-меткой.

        Прогресс-строка формируется здесь и не затрагивает
        исходный текст вопроса (исследовательский инструмент неизменен).
        В БД сохраняется только ответ участника — без каких-либо префиксов.
        """
        qs = self.questions()
        q = qs[ctx.question_index]
        total = self.total_questions()
        n = ctx.question_index + 1
        if n == total:
            prefix = f"Последний вопрос ({n} из {total})"
        else:
            prefix = f"Вопрос {n} из {total}"
        return f"{prefix}\n\n{q.text}"

    def closing(self, ctx: InterviewContext) -> str:
        if self._study is not None:
            return self._study.texts.closing
        return script.CLOSING

    def already_done(self) -> str:
        if self._study is not None:
            return self._study.texts.already_done
        return script.ALREADY_DONE

    def redirect(self, ctx: InterviewContext) -> str:
        """Редирект к текущему вопросу без продвижения (при уклонении участника).

        ctx.question_index — индекс ТЕКУЩЕГО вопроса (не следующего).
        """
        qs = self.questions()
        redirect_text = self._study.texts.redirect if self._study else script.REDIRECT
        return redirect_text + qs[ctx.question_index].text

    def is_off_topic(self, user_text: str, ctx: InterviewContext) -> bool:
        """Keyword-эвристика: используется в StaticPromptEngine и как fallback в LLMPromptEngine."""
        return is_off_topic_response(user_text)

    def build_system_prompt(self) -> str:
        """Системный промпт для LLM-клиента.

        Источник правды по вопросам — questions() (interview_script или StudyDefinition).
        """
        questions_block = "\n".join(
            f"{i + 1}. [{q.question_id}] {q.text}"
            for i, q in enumerate(self.questions())
        )
        return (
            "Ты бот-интервьюер для академического исследования. "
            "Проводишь структурированное интервью на русском языке. "
            "Задавай вопросы строго в порядке ниже, не интерпретируй и не оценивай ответы, "
            "сохраняй нейтральный доброжелательный тон.\n\n"
            f"Вопросы:\n{questions_block}"
        )
