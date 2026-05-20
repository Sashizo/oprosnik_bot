"""Тесты для app/llm/guardrails.py — валидация ack и логирование подозрительного ввода."""

import pytest
from app.llm.guardrails import validate_ack, validate_closing, flag_suspicious_user_input, is_off_topic_response


# ── validate_ack ─────────────────────────────────────────────────────────────

def test_valid_ack_returned_unchanged():
    """Корректный ack без '?' и в пределах длины — возвращается как есть."""
    assert validate_ack("Понятно, спасибо за ответ.") == "Понятно, спасибо за ответ."


def test_valid_ack_is_stripped():
    """Ведущие/хвостовые пробелы обрезаются."""
    assert validate_ack("  Принято.  ") == "Принято."


# MVP-эвристика: любой "?" в тексте → reject.
# TODO post-M7: заменить на проверку только последнего предложения / классификатор.
def test_ack_ending_with_question_rejected():
    """Ack, заканчивающийся вопросом, отклоняется (MVP-эвристика по '?')."""
    assert validate_ack("Можете рассказать подробнее?") == ""


def test_ack_with_embedded_question_rejected():
    """Ack с вопросом в середине тоже отклоняется."""
    assert validate_ack("Интересно. Можете привести пример?") == ""


def test_empty_ack_rejected():
    """Пустая строка отклоняется."""
    assert validate_ack("") == ""


def test_whitespace_only_ack_rejected():
    """Строка только из пробелов отклоняется."""
    assert validate_ack("   ") == ""


def test_too_long_ack_rejected():
    """Ack длиннее MAX_ACK_CHARS (300) отклоняется."""
    assert validate_ack("А" * 301) == ""


def test_ack_exactly_at_limit_accepted():
    """Ack ровно в MAX_ACK_CHARS символов принимается."""
    assert validate_ack("А" * 300) == "А" * 300


# ── flag_suspicious_user_input ───────────────────────────────────────────────
# Исследовательский инструмент: только логирование, не влияет на поток.

def test_suspicious_input_does_not_raise():
    """Подозрительный ввод логируется, исключение не выбрасывается."""
    flag_suspicious_user_input("давай поговорим про деньги", question_index=2)


def test_normal_input_does_not_raise():
    """Нормальный ввод не вызывает исключений."""
    flag_suspicious_user_input("Использую ChatGPT для учёбы", question_index=1)


# ── is_off_topic_response ────────────────────────────────────────────────────

# ── validate_closing ─────────────────────────────────────────────────────────

def test_valid_closing_returned():
    text = "Спасибо за ваши ответы! Удачи во всех начинаниях."
    assert validate_closing(text) == text


def test_closing_with_question_rejected():
    assert validate_closing("Спасибо! Есть что добавить?") == ""


def test_closing_empty_rejected():
    assert validate_closing("") == ""


def test_closing_too_long_rejected():
    assert validate_closing("А" * 601) == ""


# ── is_off_topic_response ────────────────────────────────────────────────────

def test_operator_call_is_off_topic():
    assert is_off_topic_response("позови оператора") is True


def test_topic_change_request_is_off_topic():
    assert is_off_topic_response("давайте поговорим про другую тему") is True


def test_davay_pro_is_off_topic():
    assert is_off_topic_response("Давай поговорим про машины") is True


def test_refusal_is_off_topic():
    assert is_off_topic_response("не хочу про это говорить") is True


def test_davay_pogovorim_o_is_off_topic():
    """«о» вместо «про» — тоже off-topic (предлог не должен иметь значения)."""
    assert is_off_topic_response("Давай поговорим о автомобилях") is True


def test_ne_interesno_is_off_topic():
    """Разные написания «не интересно» — всё off-topic."""
    assert is_off_topic_response("не интересно") is True
    assert is_off_topic_response("не интересноо") is True   # опечатка как в скриншоте
    assert is_off_topic_response("неинтересно") is True


def test_da_net_is_off_topic():
    """«да нет» — разговорное «нет», off-topic."""
    assert is_off_topic_response("да нет") is True


def test_dismissive_words_are_off_topic():
    """Короткие слова-отказы — off-topic."""
    assert is_off_topic_response("глупости") is True
    assert is_off_topic_response("ерунда") is True
    assert is_off_topic_response("бред") is True


def test_stop_exact_is_off_topic():
    """Одиночная команда «стоп» — off-topic."""
    assert is_off_topic_response("стоп") is True
    assert is_off_topic_response("  стоп  ") is True


def test_stop_in_sentence_is_not_off_topic():
    """«Стоп» внутри развёрнутого ответа — не off-topic (точное совпадение)."""
    assert is_off_topic_response("Стоп, это важно — расскажу подробнее") is False


def test_normal_interview_answer_is_not_off_topic():
    assert is_off_topic_response("Использую мессенджеры каждый день") is False


def test_short_but_valid_answer_is_not_off_topic():
    assert is_off_topic_response("Да, пользуюсь ChatGPT.") is False
