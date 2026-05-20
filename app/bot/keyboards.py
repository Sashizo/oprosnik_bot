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


# ── Keyboard builders ─────────────────────────────────────────────────────────

def keyboard_restart() -> InlineKeyboardMarkup:
    """Кнопка «Пройти ещё раз» — для CLOSING и ALREADY_DONE.

    Нажатие эквивалентно команде /start.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Пройти ещё раз", callback_data=CALLBACK_RESTART)
    ]])


def keyboard_start() -> InlineKeyboardMarkup:
    """Кнопка «Начать интервью» — для /help.

    Нажатие эквивалентно команде /start.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶ Начать интервью", callback_data=CALLBACK_RESTART)
    ]])
