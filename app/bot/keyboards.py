"""Telegram InlineKeyboard builders.

Чистые функции без зависимостей от domain-слоя (DialogManager, PromptEngine).
adapter.py использует их для добавления reply_markup к нужным сообщениям.

Принцип: кнопки — только навигация в конечных состояниях,
никогда не заменяют содержательные ответы на вопросы.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ── Callback data константы ───────────────────────────────────────────────────
# Формат "action:<name>" — простой и расширяемый.

CALLBACK_RESTART = "action:restart"
CALLBACK_BEGIN = "action:begin"


# ── Keyboard builders ─────────────────────────────────────────────────────────

def keyboard_restart() -> InlineKeyboardMarkup:
    """Кнопка «Пройти ещё раз» — для CLOSING и ALREADY_DONE.

    Нажатие эквивалентно команде /start.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Пройти ещё раз", callback_data=CALLBACK_RESTART)
    ]])


def keyboard_begin() -> InlineKeyboardMarkup:
    """Кнопка «Начать интервью» — для приветственного экрана /start и /help.

    Нажатие сбрасывает сессию и показывает первый вопрос.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶ Начать интервью", callback_data=CALLBACK_BEGIN)
    ]])


def keyboard_start() -> InlineKeyboardMarkup:
    """Алиас keyboard_begin() — для обратной совместимости."""
    return keyboard_begin()
