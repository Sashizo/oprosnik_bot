"""Экспорт данных интервью в CSV и JSON.

Содержит:
  - SessionRecord / AnswerRecord  — DTO для аналитики (не ORM-объекты)
  - question_text_map()           — словарь question_id → текст вопроса
  - duration_minutes()            — длительность сессии в минутах
  - to_csv(sessions, path)        — запись плоской CSV-таблицы
  - to_json(sessions, path)       — запись JSON-файла
  - load_sessions(db_url)         — загрузка всех сессий из SQLite
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services import interview_script as script


# ── DTO ───────────────────────────────────────────────────────────────────────

@dataclass
class AnswerRecord:
    question_id: str
    text: str
    answered_at: datetime


@dataclass
class SessionRecord:
    session_id: int
    user_id: int
    started_at: datetime
    finished_at: datetime | None
    finished: bool
    current_question_index: int
    answers: list[AnswerRecord]
    # study_id = None означает legacy-сессию (до M10, сценарий из interview_script.py).
    study_id: int | None = None


# ── Вспомогательные функции ───────────────────────────────────────────────────

def question_text_map(study_id: int | None = None) -> dict[str, str]:
    """Словарь question_id → полный текст вопроса.

    При study_id=None (legacy) — берёт из interview_script.
    При study_id=<int> — ищет Study в БД через StudyRepository.
    StudyRepository импортируется лениво во избежание циклических импортов.
    """
    if study_id is None:
        return {q.question_id: q.text for q in script.QUESTIONS}

    from app.researcher.repository import StudyRepository
    from app.db.database import build_engine, build_session_factory
    from app.core.config import settings

    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    sd = StudyRepository(session_factory).get_by_id(study_id)
    if sd is None:
        return {}
    return {q.question_id: q.text for q in sd.questions}


def duration_minutes(session: SessionRecord) -> float | None:
    """Длительность завершённой сессии в минутах; None для незавершённых."""
    if session.finished_at is None:
        return None
    delta = session.finished_at - session.started_at
    return round(delta.total_seconds() / 60, 2)


# ── CSV ───────────────────────────────────────────────────────────────────────

CSV_HEADERS = [
    "session_id", "user_id", "started_at", "finished_at", "finished",
    "duration_minutes", "question_id", "question_text",
    "answer_text", "answered_at", "answer_length_chars",
]


def _build_q_map_cache(sessions: list[SessionRecord]) -> dict:
    """Создаёт кэш question_text_map для каждого уникального study_id в списке сессий.

    Lazy: map строится один раз per unique study_id, не per session.
    NULL (None) → legacy map из interview_script.
    """
    cache: dict = {}
    for s in sessions:
        if s.study_id not in cache:
            cache[s.study_id] = question_text_map(s.study_id)
    return cache


def to_csv(sessions: list[SessionRecord], path: Path) -> None:
    """Записывает плоскую CSV-таблицу: одна строка = один ответ.

    Незавершённые сессии без ответов попадают в CSV одной строкой
    с пустыми answer-полями — чтобы не потерять такие сессии из анализа.

    Корректно разрешает question_text как для legacy-сессий (study_id=None),
    так и для сессий с явным study_id.
    """
    q_maps = _build_q_map_cache(sessions)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()

        for s in sessions:
            q_map = q_maps[s.study_id]
            dur = duration_minutes(s)
            base = {
                "session_id": s.session_id,
                "user_id": s.user_id,
                "started_at": s.started_at.isoformat(),
                "finished_at": s.finished_at.isoformat() if s.finished_at else "",
                "finished": s.finished,
                "duration_minutes": dur if dur is not None else "",
            }

            if s.answers:
                for a in s.answers:
                    writer.writerow({
                        **base,
                        "question_id": a.question_id,
                        "question_text": q_map.get(a.question_id, ""),
                        "answer_text": a.text,
                        "answered_at": a.answered_at.isoformat(),
                        "answer_length_chars": len(a.text),
                    })
            else:
                # Сессия без ответов — одна строка с пустыми полями ответа
                writer.writerow({
                    **base,
                    "question_id": "",
                    "question_text": "",
                    "answer_text": "",
                    "answered_at": "",
                    "answer_length_chars": "",
                })


# ── JSON ──────────────────────────────────────────────────────────────────────

def to_json(sessions: list[SessionRecord], path: Path) -> None:
    """Записывает JSON-файл: список сессий с вложенными ответами.

    Корректно разрешает question_text как для legacy-сессий (study_id=None),
    так и для сессий с явным study_id.
    """
    q_maps = _build_q_map_cache(sessions)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = []
    for s in sessions:
        q_map = q_maps[s.study_id]
        dur = duration_minutes(s)
        data.append({
            "session_id": s.session_id,
            "user_id": s.user_id,
            "started_at": s.started_at.isoformat(),
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            "finished": s.finished,
            "duration_minutes": dur,
            "study_id": s.study_id,
            "answers": [
                {
                    "question_id": a.question_id,
                    "question_text": q_map.get(a.question_id, ""),
                    "answer_text": a.text,
                    "answered_at": a.answered_at.isoformat(),
                    "answer_length_chars": len(a.text),
                }
                for a in s.answers
            ],
        })

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Загрузка из БД ────────────────────────────────────────────────────────────

def load_sessions(db_url: str) -> list[SessionRecord]:
    """Загружает все сессии из SQLite через get_all_sessions().

    Создаёт одноразовый engine/session_factory — только для CLI/аналитики,
    не используется в runtime бота.
    """
    from app.db.database import build_engine, build_session_factory
    from app.db.repository import get_all_sessions

    engine = build_engine(db_url)
    session_factory = build_session_factory(engine)
    return get_all_sessions(session_factory)
