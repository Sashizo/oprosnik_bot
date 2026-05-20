"""Тесты для app/analysis/ — экспорт и метрики.

Все тесты работают с мок-данными (list[SessionRecord]) без обращения к БД.
"""

import csv
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from app.analysis.export import (
    SessionRecord, AnswerRecord,
    to_csv, to_json, duration_minutes, question_text_map, CSV_HEADERS,
)
from app.analysis.metrics import (
    completion_rate, dropout_distribution, avg_answer_length, duration_stats,
)
from app.services import interview_script as script


# ── Фикстуры ─────────────────────────────────────────────────────────────────

def _dt(offset_minutes: int = 0) -> datetime:
    return datetime(2025, 5, 10, 10, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


def _answer(qid: str, text: str, offset: int = 1) -> AnswerRecord:
    return AnswerRecord(question_id=qid, text=text, answered_at=_dt(offset))


def _finished_session(session_id: int = 1, user_id: int = 100) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        user_id=user_id,
        started_at=_dt(0),
        finished_at=_dt(6),
        finished=True,
        current_question_index=3,
        answers=[
            _answer("q1", "Использую телеграмм и вконтакте каждый день.", 1),
            _answer("q2", "Да, пользовался ChatGPT.", 3),
            _answer("q3", "Думаю, бот не заменит живого исследователя.", 5),
        ],
    )


def _unfinished_session(session_id: int = 2, user_id: int = 200,
                        at_index: int = 1) -> SessionRecord:
    answers = []
    if at_index > 0:
        answers.append(_answer("q1", "Немного пользуюсь.", 1))
    return SessionRecord(
        session_id=session_id,
        user_id=user_id,
        started_at=_dt(0),
        finished_at=None,
        finished=False,
        current_question_index=at_index,
        answers=answers,
    )


def _empty_session(session_id: int = 3, user_id: int = 300) -> SessionRecord:
    """Сессия без единого ответа (участник открыл, но ничего не написал)."""
    return SessionRecord(
        session_id=session_id,
        user_id=user_id,
        started_at=_dt(0),
        finished_at=None,
        finished=False,
        current_question_index=0,
        answers=[],
    )


# ── completion_rate ───────────────────────────────────────────────────────────

def test_completion_rate_all_finished():
    sessions = [_finished_session(1), _finished_session(2)]
    assert completion_rate(sessions) == 1.0


def test_completion_rate_none_finished():
    sessions = [_unfinished_session(1), _unfinished_session(2)]
    assert completion_rate(sessions) == 0.0


def test_completion_rate_mixed():
    sessions = [_finished_session(1), _unfinished_session(2)]
    assert completion_rate(sessions) == 0.5


def test_completion_rate_empty_list():
    """Пустой список не вызывает ZeroDivisionError."""
    assert completion_rate([]) == 0.0


# ── dropout_distribution ──────────────────────────────────────────────────────

def test_dropout_distribution_counts():
    sessions = [
        _finished_session(1),          # не учитывается — завершён
        _empty_session(2),             # отказ на index=0
        _unfinished_session(3, at_index=1),  # отказ на index=1
        _unfinished_session(4, at_index=1),  # ещё один на index=1
    ]
    dist = dropout_distribution(sessions)
    assert dist[0] == 1
    assert dist[1] == 2
    assert 3 not in dist   # завершённый не попадает


# ── avg_answer_length ─────────────────────────────────────────────────────────

def test_avg_answer_length_by_question():
    s1 = _finished_session(1)  # q1: 44 chars, q2: 22, q3: 42
    # перезаписываем тексты для предсказуемости
    s1.answers[0].text = "А" * 100
    s1.answers[1].text = "Б" * 50
    sessions = [s1]
    avg = avg_answer_length(sessions)
    assert avg["q1"] == 100.0
    assert avg["q2"] == 50.0


def test_avg_answer_length_multiple_sessions():
    s1 = _finished_session(1)
    s1.answers[0].text = "А" * 100
    s2 = _finished_session(2)
    s2.answers[0].text = "А" * 200
    avg = avg_answer_length([s1, s2])
    assert avg["q1"] == 150.0


def test_avg_answer_length_empty():
    assert avg_answer_length([]) == {}


# ── duration_stats ────────────────────────────────────────────────────────────

def test_duration_stats_only_finished():
    """Незавершённые не учитываются в duration_stats."""
    finished = _finished_session(1)   # 6 минут (_dt(0) → _dt(6))
    unfinished = _unfinished_session(2)
    stats = duration_stats([finished, unfinished])
    assert stats is not None
    assert stats["min"] == stats["max"] == stats["avg"] == 6.0


def test_duration_stats_empty():
    assert duration_stats([]) is None


def test_duration_stats_no_finished():
    assert duration_stats([_unfinished_session(1)]) is None


# ── to_csv ────────────────────────────────────────────────────────────────────

def test_to_csv_headers(tmp_path):
    path = tmp_path / "out.csv"
    to_csv([_finished_session()], path)
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert list(reader.fieldnames) == CSV_HEADERS


def test_to_csv_row_count(tmp_path):
    """3 ответа = 3 строки данных (+ 1 заголовок)."""
    path = tmp_path / "out.csv"
    to_csv([_finished_session()], path)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3


def test_to_csv_unfinished_session_included(tmp_path):
    """Сессия без ответов попадает в CSV одной строкой с пустыми полями."""
    path = tmp_path / "out.csv"
    to_csv([_empty_session()], path)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["answer_text"] == ""
    assert rows[0]["finished"] == "False"


def test_to_csv_duration_empty_for_unfinished(tmp_path):
    path = tmp_path / "out.csv"
    to_csv([_unfinished_session()], path)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["duration_minutes"] == ""


def test_question_text_resolved_from_script(tmp_path):
    """question_text в CSV совпадает с interview_script."""
    path = tmp_path / "out.csv"
    to_csv([_finished_session()], path)
    q_map = question_text_map()
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            qid = row["question_id"]
            assert row["question_text"] == q_map.get(qid, "")


# ── to_json ───────────────────────────────────────────────────────────────────

def test_to_json_structure(tmp_path):
    path = tmp_path / "out.json"
    to_json([_finished_session()], path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 1
    s = data[0]
    assert "session_id" in s
    assert "answers" in s
    assert isinstance(s["answers"], list)
    assert len(s["answers"]) == 3
    assert "question_text" in s["answers"][0]
    assert "answer_length_chars" in s["answers"][0]


def test_to_json_finished_at_none_for_unfinished(tmp_path):
    path = tmp_path / "out.json"
    to_json([_empty_session()], path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["finished_at"] is None
    assert data[0]["duration_minutes"] is None
