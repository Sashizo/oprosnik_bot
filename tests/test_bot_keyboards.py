"""Unit-тесты для app/bot/keyboards.py — keyboard builders."""

from telegram import InlineKeyboardMarkup

from app.bot.keyboards import (
    CALLBACK_BEGIN,
    CALLBACK_RESTART,
    keyboard_begin,
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
    """keyboard_start() делегирует keyboard_begin() → использует CALLBACK_BEGIN."""
    markup = keyboard_start()
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == CALLBACK_BEGIN


def test_keyboard_start_button_text():
    markup = keyboard_start()
    button = markup.inline_keyboard[0][0]
    assert "Начать интервью" in button.text


# ── keyboard_begin / keyboard_start ──────────────────────────────────────────

def test_callback_begin_value():
    assert CALLBACK_BEGIN == "action:begin"


def test_keyboard_begin_uses_callback_begin():
    """keyboard_begin() использует CALLBACK_BEGIN."""
    button = keyboard_begin().inline_keyboard[0][0]
    assert button.callback_data == CALLBACK_BEGIN


def test_keyboard_restart_uses_callback_restart():
    """keyboard_restart() по-прежнему использует CALLBACK_RESTART."""
    button = keyboard_restart().inline_keyboard[0][0]
    assert button.callback_data == CALLBACK_RESTART


def test_keyboard_restart_and_begin_use_different_callbacks():
    """keyboard_restart и keyboard_begin ведут к разным action-константам."""
    cb_restart = keyboard_restart().inline_keyboard[0][0].callback_data
    cb_begin = keyboard_begin().inline_keyboard[0][0].callback_data
    assert cb_restart == CALLBACK_RESTART
    assert cb_begin == CALLBACK_BEGIN
    assert cb_restart != cb_begin


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
