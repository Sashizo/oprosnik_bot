"""LLM Guardrails — валидация вывода LLM и исследовательское логирование.

Назначение:
  Локализованный слой постобработки LLM-вывода для LLMPromptEngine.
  Функции — чистые (без состояния), не знают ни о клиенте, ни о движке.

Ключевая гарантия научной валидности:
  Guardrails могут вырезать ack, но никогда не изменяют и не скрывают
  скриптовые вопросы. Сценарий интервью остаётся идентичным описанному
  в методике ВКР при любом поведении LLM.
"""

import logging

logger = logging.getLogger(__name__)

# Порог длины для acknowledgment (~2 предложения).
# Всё что длиннее — подозрительно и отклоняется.
MAX_ACK_CHARS = 300
MAX_CLOSING_CHARS = 600


def validate_ack(text: str) -> str:
    """Возвращает очищенный текст или пустую строку при нарушении.

    Правила (в порядке проверки):
    1. strip() → если пусто → отклонить
    2. содержит "?" → отклонить
       (MVP-эвристика: LLM, вероятно, добавил вопрос к участнику.
       TODO post-M7: заменить на более аккуратную проверку — например,
       проверку только последнего предложения или классификатор.)
    3. длина > MAX_ACK_CHARS → отклонить (слишком длинный ack)

    При отклонении: возвращается "", и question() показывает только
    статический скриптовый вопрос — бесшовно для участника.

    Все отклонения логируются с меткой [GUARDRAIL][ACK_REJECTED].
    """
    stripped = text.strip()

    if not stripped:
        _log_reject("empty", text)
        return ""

    # MVP-эвристика: знак вопроса → скорее всего LLM добавил вопрос участнику.
    # Намеренно широкая: false positive (лишнее отклонение) лучше, чем
    # false negative (пропустить LLM-вопрос). TODO post-M7: уточнить.
    if "?" in stripped:
        _log_reject("contains_question", stripped)
        return ""

    if len(stripped) > MAX_ACK_CHARS:
        _log_reject("too_long", stripped)
        return ""

    return stripped


def validate_closing(text: str) -> str:
    """Валидация LLM-сгенерированного closing-сообщения.

    Правила:
    1. strip() → если пусто → отклонить (fallback на статический closing)
    2. длина > MAX_CLOSING_CHARS → отклонить (аномально длинный текст)
    3. содержит "?" → отклонить (LLM не должен задавать вопросы в closing)

    Возвращает очищенный текст или пустую строку (engine.closing() делает fallback).
    """
    stripped = text.strip()
    if not stripped:
        logger.warning("[GUARDRAIL][CLOSING_REJECTED] reason=empty")
        return ""
    if len(stripped) > MAX_CLOSING_CHARS:
        logger.warning("[GUARDRAIL][CLOSING_REJECTED] reason=too_long text=%r", stripped[:120])
        return ""
    if "?" in stripped:
        logger.warning("[GUARDRAIL][CLOSING_REJECTED] reason=contains_question text=%r", stripped[:120])
        return ""
    return stripped


def flag_suspicious_user_input(user_text: str, question_index: int) -> None:
    """Исследовательский инструмент: логирует потенциальные попытки prompt injection.

    Назначение:
      — исключительно для исследовательского логирования;
      — результаты НЕ используются для автоматических решений;
      — НЕ влияет на ход интервью (участник получает следующий вопрос в любом случае);
      — данные нужны для последующего качественного анализа случаев
        нецелевого использования бота в рамках ВКР.

    Эвристика намеренно чувствительная (низкий порог): лучше зафиксировать
    лишний случай, чем пропустить реальный.
    """
    triggers = ["давай", "расскажи", "забудь", "игнорируй", "притворись", "стоп"]
    lowered = user_text.lower()
    if any(t in lowered for t in triggers):
        logger.warning(
            "[GUARDRAIL][SUSPICIOUS_INPUT] q=%d text=%r",
            question_index,
            user_text[:120],
        )


def is_off_topic_response(text: str) -> bool:
    """Эвристика: возвращает True если участник явно уклоняется от ответа на вопрос.

    Назначение: защита от продвижения интервью без реального ответа.
    При срабатывании DialogManager возвращает редирект без сохранения ответа.

    MVP-эвристика по ключевым фразам — намеренно консервативная (low false-positive):
    лучше пропустить единичный случай уклонения, чем ошибочно заблокировать
    валидный ответ участника.

    Все срабатывания логируются с меткой [GUARDRAIL][OFF_TOPIC].
    TODO post-M7: улучшить классификатором или семантической проверкой.
    """
    lowered = text.strip().lower()

    # Многословные фразы — высокая точность (few false positives)
    _PHRASES = [
        "позови оператора",
        "вызови оператора",
        "позовите оператора",
        # «давай/давайте поговорим» без привязки к предлогу (про/о/об)
        "давай поговорим",
        "давайте поговорим",
        "поговорим про",
        "поговорим о ",   # пробел после «о» — не поймать «поговорим об этом» как часть ответа
        "говорим про другое",
        "давай про",
        "давайте про",
        "давай о ",
        "давайте о ",
        "про другое",
        "другую тему",
        "другой теме",
        "другой темой",
        "не хочу про это",
        "не хочу об этом",
        "не хочу говорить",
        "не хочу отвечать",
        "не буду отвечать",
        "не интересно",
        "неинтересно",
        "пропусти вопрос",
        "следующий вопрос",
        "другой вопрос",
    ]
    if any(phrase in lowered for phrase in _PHRASES):
        logger.warning("[GUARDRAIL][OFF_TOPIC] text=%r", text[:120])
        return True

    # Короткие команды-отказы (1–2 слова, полное совпадение после strip)
    # Намеренно точное совпадение — чтобы не заблокировать ответ вроде
    # «Стоп, это важно — расскажу подробнее».
    _EXACT = {
        "стоп", "хватит", "нет", "да нет", "не знаю", "незнаю",
        "отказываюсь", "пропусти", "дальше", "не хочу",
        "глупости", "ерунда", "чепуха", "бред", "неважно",
    }
    if lowered in _EXACT:
        logger.warning("[GUARDRAIL][OFF_TOPIC] text=%r", text[:120])
        return True

    return False


MAX_CLARIFY_CHARS = 400


def validate_clarify(text: str) -> str:
    """Валидация LLM-сгенерированного разъяснения уточняющего вопроса.

    Правила: не пусто, не содержит "?" (LLM не должен задавать ответный вопрос
    участнику), не длиннее MAX_CLARIFY_CHARS.
    При отклонении возвращает "" — engine.clarify() вернёт статический fallback.
    """
    stripped = text.strip()
    if not stripped:
        logger.warning("[GUARDRAIL][CLARIFY_REJECTED] reason=empty")
        return ""
    if "?" in stripped:
        logger.warning("[GUARDRAIL][CLARIFY_REJECTED] reason=contains_question text=%r", stripped[:120])
        return ""
    if len(stripped) > MAX_CLARIFY_CHARS:
        logger.warning("[GUARDRAIL][CLARIFY_REJECTED] reason=too_long text=%r", stripped[:120])
        return ""
    return stripped


def _log_reject(reason: str, text: str) -> None:
    logger.warning(
        "[GUARDRAIL][ACK_REJECTED] reason=%s text=%r",
        reason,
        text[:120],
    )
