import logging

from app.llm.client import LLMClient
from app.llm.guardrails import flag_suspicious_user_input, is_off_topic_response, validate_ack, validate_closing
from app.services import interview_script as script
from app.services.prompt_engine import InterviewContext, StaticPromptEngine

logger = logging.getLogger(__name__)

_ACK_SYSTEM_PROMPT = (
    "Ты бот-интервьюер для академического исследования. "
    "Твоя единственная задача: написать ровно 1–2 нейтральных предложения "
    "в ответ на последнее сообщение участника. "
    "СТРОГО ЗАПРЕЩЕНО: задавать вопросы, просить уточнить, давать советы, "
    "добавлять знак вопроса (?). "
    "Только утвердительные или безличные предложения. "
    "Только на русском языке. Без форматирования.\n\n"
    "Пример правильно: «Понятно, спасибо за ответ.»\n"
    "Пример неправильно: «Можете рассказать подробнее?» — содержит вопрос, запрещено."
)

_CLASSIFIER_SYSTEM_PROMPT = (
    "Ты помощник исследователя. Твоя задача — определить, уклоняется ли участник "
    "от ответа на вопрос интервью.\n\n"
    "УКЛОНЕНИЕ (ДА) — только если участник:\n"
    "  • явно хочет сменить тему («давай про машины», «поговорим о другом»)\n"
    "  • отказывается отвечать («не хочу», «не буду», «пропусти»)\n"
    "  • просит позвать кого-то или выйти («позови оператора», «стоп»)\n"
    "  • пишет очевидную бессмыслицу, не связанную с темой\n\n"
    "НЕ УКЛОНЕНИЕ (НЕТ) — участник отвечает, если:\n"
    "  • упоминает хоть что-то из темы вопроса, даже одним словом\n"
    "  • отвечает кратко («да», «нет», «не знаю», «не использую»)\n"
    "  • даёт негативный ответ по теме («я не пользуюсь», «мне не интересно это»)\n\n"
    "Примеры:\n"
    "  Вопрос о мессенджерах — «я использую телеграмм» → НЕТ\n"
    "  Вопрос о мессенджерах — «не пользуюсь ничем» → НЕТ\n"
    "  Вопрос о мессенджерах — «давай про автомобили» → ДА\n"
    "  Вопрос о мессенджерах — «я не хочу отвечать» → ДА\n\n"
    "Отвечай ТОЛЬКО одним словом: ДА или НЕТ. "
    "Если сомневаешься — отвечай НЕТ."
)

_CLOSING_SYSTEM_PROMPT = (
    "Ты бот-интервьюер для академического исследования. "
    "Все вопросы интервью заданы. Напиши тёплое завершающее сообщение: "
    "2–3 предложения, поблагодари участника за уделённое время и вклад в исследование. "
    "Не упоминай конкретные темы, слова или детали из ответов участника. "
    "Пиши обобщённо: благодари за время и вклад в исследование. "
    "Только на русском языке. Без форматирования."
)


class LLMPromptEngine:
    """Prompt Engine с LLM-generated acknowledgment.

    Ключевой инвариант:
      - Текст исследовательских вопросов ВСЕГДА берётся через StaticPromptEngine.
      - LLM генерирует только acknowledgment (1–2 предложения реакции) и closing.
      - При любом сбое LLM — автоматический fallback на StaticPromptEngine.
      - DialogManager не изменяется.

    Два режима использования (для методики ВКР):
      - Static mode: StaticPromptEngine (без LLM)
      - LLM mode:    LLMPromptEngine (ack через LLM + вопрос из скрипта/StudyDefinition)
    """

    def __init__(self, client: LLMClient, study=None) -> None:
        """
        study: app.researcher.schema.StudyDefinition | None.
               Передаётся в StaticPromptEngine — источник правды по вопросам.
        """
        self._client = client
        self._static = StaticPromptEngine(study=study)

    # ── Методы PromptEngine Protocol ─────────────────────────────────────────

    def intro(self) -> str:
        """Приветствие — статическое, LLM не нужен."""
        return self._static.intro()

    def question(self, ctx: InterviewContext) -> str:
        """Acknowledgment (LLM) + следующий вопрос дословно из interview_script.

        Вопрос НИКОГДА не генерируется LLM — только из StaticPromptEngine.
        При сбое LLM или отклонении guardrail: возвращает только статический
        вопрос (бесшовный fallback). Научная валидность сохранена в любом случае.
        """
        # Исследовательское логирование (не влияет на ход интервью)
        flag_suspicious_user_input(ctx.last_user_text or "", ctx.question_index)

        ack = self._generate_acknowledgment(ctx)
        next_q = self._static.question(ctx)      # источник правды — interview_script
        return f"{ack}\n\n{next_q}" if ack else next_q

    def closing(self, ctx: InterviewContext) -> str:
        """Тёплое завершение (LLM) с guardrail-валидацией и fallback на статический текст."""
        try:
            history = self._build_full_history(ctx)
            raw = self._client.complete(system=_CLOSING_SYSTEM_PROMPT, messages=history)
            result = validate_closing(raw)
            if result:
                return result
            logger.warning("LLM closing rejected by guardrail, using static closing")
            return self._static.closing(ctx)
        except Exception as exc:
            logger.warning("LLM closing failed (%s), using static closing", exc)
            return self._static.closing(ctx)

    def already_done(self) -> str:
        """Статическое — LLM не нужен."""
        return self._static.already_done()

    def redirect(self, ctx: InterviewContext) -> str:
        """Редирект к текущему вопросу при уклонении участника.

        Всегда статический — LLM не привлекается, чтобы гарантировать
        нейтральность сообщения и отсутствие галлюцинаций.
        ctx.question_index — индекс ТЕКУЩЕГО вопроса (не следующего).
        """
        return self._static.redirect(ctx)

    def is_off_topic(self, user_text: str, ctx: InterviewContext) -> bool:
        """LLM-классификатор: уклоняется ли участник от ответа на текущий вопрос.

        Задаёт LLM вопрос: «участник уклоняется? ДА/НЕТ».
        Контекст (текст текущего вопроса) передаётся явно — модель знает
        что именно спрашивалось и может оценить релевантность ответа.

        Fallback: keyword-эвристика из guardrails при любой ошибке LLM.
        """
        try:
            question_text = self._static.questions()[ctx.question_index].text
            messages = [{
                "role": "user",
                "content": (
                    f"Вопрос интервью: «{question_text}»\n"
                    f"Ответ участника: «{user_text}»\n"
                    f"Участник уклоняется от ответа?"
                ),
            }]
            raw = self._client.complete(system=_CLASSIFIER_SYSTEM_PROMPT, messages=messages)
            # Парсим только первое слово — GigaChat иногда добавляет пояснение
            first_word = raw.strip().split()[0].upper().rstrip(".,!") if raw.strip() else ""
            is_off = first_word == "ДА"
            logger.info(
                "[CLASSIFIER] q=%d decision=%r text=%r",
                ctx.question_index, first_word, user_text[:80],
            )
            if is_off:
                logger.warning(
                    "[GUARDRAIL][OFF_TOPIC][LLM] q=%d text=%r",
                    ctx.question_index, user_text[:120],
                )
            return is_off
        except Exception as exc:
            logger.warning("LLM classifier failed (%s), falling back to keyword heuristic", exc)
            return is_off_topic_response(user_text)

    def questions(self) -> tuple:
        """Делегирует в StaticPromptEngine — единственный источник правды по вопросам."""
        return self._static.questions()

    def total_questions(self) -> int:
        return self._static.total_questions()

    def build_system_prompt(self) -> str:
        """Расширенный system prompt для справки / будущих реализаций.

        StaticPromptEngine.build_system_prompt() — базовый референс.
        LLMPromptEngine использует отдельные узкоспециализированные промпты
        (_ACK_SYSTEM_PROMPT, _CLOSING_SYSTEM_PROMPT) для каждого вызова.
        """
        base = self._static.build_system_prompt()
        return (
            base + "\n\n"
            "Режим acknowledgment: после каждого ответа участника генерируй "
            "1–2 нейтральных предложения реакции. Текст следующего вопроса "
            "берётся дословно из списка выше — не перефразируй."
        )

    # ── Внутренние методы ────────────────────────────────────────────────────

    def _generate_acknowledgment(self, ctx: InterviewContext) -> str:
        """Запрашивает у LLM 1–2 предложения реакции на последний ответ.

        При исключении возвращает пустую строку — question() покажет только
        статический вопрос без acknowledgment.

        История строится из interview_script (не из предыдущих LLM-ответов):
        это гарантирует детерминированность контекста.
        """
        try:
            history = self._build_history(ctx)
            if not history:
                return ""  # нет предыдущих ответов — ack не нужен
            raw = self._client.complete(system=_ACK_SYSTEM_PROMPT, messages=history)
            return validate_ack(raw)   # guardrail: пустая строка при нарушении
        except Exception as exc:
            logger.warning("LLM acknowledgment failed (%s), skipping ack", exc)
            return ""

    def _build_history(self, ctx: InterviewContext) -> list[dict[str, str]]:
        """Conversation history до текущего момента (без следующего вопроса).

        assistant: текст вопроса из StaticPromptEngine (не из LLM-ответа)
        user:      ответ участника из ctx.previous_answers
        """
        history: list[dict[str, str]] = []
        for q in self._static.questions()[: ctx.question_index]:
            history.append({"role": "assistant", "content": q.text})
            if q.question_id in ctx.previous_answers:
                history.append(
                    {"role": "user", "content": ctx.previous_answers[q.question_id]}
                )
        return history

    def _build_full_history(self, ctx: InterviewContext) -> list[dict[str, str]]:
        """Полная история: все вопросы + все ответы (для closing)."""
        history: list[dict[str, str]] = []
        for q in self._static.questions():
            history.append({"role": "assistant", "content": q.text})
            if q.question_id in ctx.previous_answers:
                history.append(
                    {"role": "user", "content": ctx.previous_answers[q.question_id]}
                )
        return history
