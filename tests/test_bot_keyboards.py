"""Unit-тесты для app/bot/keyboards.py — keyboard builders."""

from telegram import InlineKeyboardMarkup

from app.bot.keyboards import (
    CALLBACK_RESTART,
    keyboard_restart,
    keyboard_start,
)


# ── CALLBACK_RESTART константа ────────────────────────────────────────────────

def test_callback_restart_value():
    assert CALLBACK_RESTART == "action:restart"


# ── keyboard_restart ──────────────────────────────────────────────────────────

def test_keyboard_restart_returns_inline_markup():
    markup = keyboard_restart()
    assert isinstance(markup, InlineKeyboardMarkup)


def test_keyboard_restart_has_one_row():
    markup = keyboard_restart()
    assert len(markup.inline_keyboard) == 1


def test_keyboard_restart_has_one_button():
    markup = keyboard_restart()
    assert len(markup.inline_keyboard[0]) == 1


def test_keyboard_restart_callback_data():
    markup = keyboard_restart()
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == CALLBACK_RESTART


def test_keyboard_restart_button_text():
    markup = keyboard_restart()
    button = markup.inline_keyboard[0][0]
    assert "Пройти ещё раз" in button.text


# ── keyboard_start ────────────────────────────────────────────────────────────

def test_keyboard_start_returns_inline_markup():
    markup = keyboard_start()
    assert isinstance(markup, InlineKeyboardMarkup)


def test_keyboard_start_has_one_row():
    markup = keyboard_start()
    assert len(markup.inline_keyboard) == 1


def test_keyboard_start_has_one_button():
    markup = keyboard_start()
    assert len(markup.inline_keyboard[0]) == 1


def test_keyboard_start_callback_data():
    markup = keyboard_start()
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == CALLBACK_RESTART


def test_keyboard_start_button_text():
    markup = keyboard_start()
    button = markup.inline_keyboard[0][0]
    assert "Начать интервью" in button.text


# ── keyboard_restart и keyboard_start используют один callback ────────────────

def test_both_keyboards_share_same_callback():
    """Оба keyboard builder ведут к одному action:restart."""
    cb_restart = keyboard_restart().inline_keyboard[0][0].callback_data
    cb_start = keyboard_start().inline_keyboard[0][0].callback_data
    assert cb_restart == cb_start == CALLBACK_RESTART


# ── Независимость вызовов ─────────────────────────────────────────────────────

def test_keyboard_restart_returns_new_instance_each_call():
    """Каждый вызов возвращает новый объект (нет глобального мутабельного состояния)."""
    m1 = keyboard_restart()
    m2 = keyboard_restart()
    assert m1 is not m2


def test_keyboard_start_returns_new_instance_each_call():
    m1 = keyboard_start()
    m2 = keyboard_start()
    assert m1 is not m2
