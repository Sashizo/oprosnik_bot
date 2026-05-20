"""Тесты для app/researcher/repository.py — StudyRepository."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.database import _migrate_add_study_id
from app.researcher.repository import StudyRepository
from app.researcher.schema import QuestionDef, StudyDefinition, StudyTexts


# ── Фикстуры ─────────────────────────────────────────────────────────────────

@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    _migrate_add_study_id(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def repo(session_factory):
    return StudyRepository(session_factory)


def _make_sd(title="Тестовое исследование", n_questions=2) -> StudyDefinition:
    questions = tuple(
        QuestionDef(f"q{i}", f"Вопрос {i}?") for i in range(1, n_questions + 1)
    )
    texts = StudyTexts(
        greeting="Привет!",
        closing="Спасибо!",
        redirect="Ответьте.\n\n",
        help="Помощь",
        already_done="Завершено.",
    )
    return StudyDefinition(title=title, description="Описание", questions=questions, texts=texts)


# ── create ────────────────────────────────────────────────────────────────────

def test_create_returns_study_with_id(repo):
    sd = repo.create(_make_sd())
    assert sd.study_id is not None
    assert sd.study_id > 0


def test_create_stores_questions(repo):
    sd = repo.create(_make_sd(n_questions=3))
    retrieved = repo.get_by_id(sd.study_id)
    assert len(retrieved.questions) == 3
    assert retrieved.questions[0].question_id == "q1"
    assert retrieved.questions[2].question_id == "q3"


def test_create_stores_texts(repo):
    sd = repo.create(_make_sd())
    retrieved = repo.get_by_id(sd.study_id)
    assert retrieved.texts.greeting == "Привет!"
    assert retrieved.texts.closing == "Спасибо!"


def test_create_is_not_active_by_default(repo):
    sd = repo.create(_make_sd())
    retrieved = repo.get_by_id(sd.study_id)
    assert repo.get_active() is None  # не активирован


def test_create_multiple_independent_studies(repo):
    sd1 = repo.create(_make_sd("Исследование 1"))
    sd2 = repo.create(_make_sd("Исследование 2"))
    assert sd1.study_id != sd2.study_id
    all_studies = repo.list_all()
    assert len(all_studies) == 2


# ── activate ──────────────────────────────────────────────────────────────────

def test_activate_sets_is_active(repo):
    sd = repo.create(_make_sd())
    result = repo.activate(sd.study_id)
    assert result is True
    active = repo.get_active()
    assert active is not None
    assert active.study_id == sd.study_id


def test_activate_deactivates_previous(repo):
    sd1 = repo.create(_make_sd("Study 1"))
    sd2 = repo.create(_make_sd("Study 2"))
    repo.activate(sd1.study_id)
    repo.activate(sd2.study_id)
    active = repo.get_active()
    assert active.study_id == sd2.study_id


def test_activate_nonexistent_returns_false(repo):
    result = repo.activate(9999)
    assert result is False


# ── get_active ────────────────────────────────────────────────────────────────

def test_get_active_returns_none_when_no_studies(repo):
    assert repo.get_active() is None


def test_get_active_returns_correct_study(repo):
    sd = repo.create(_make_sd())
    repo.activate(sd.study_id)
    active = repo.get_active()
    assert active.title == "Тестовое исследование"
    assert len(active.questions) == 2


def test_get_active_preserves_question_order(repo):
    qs = [QuestionDef("a", "Первый"), QuestionDef("b", "Второй"), QuestionDef("c", "Третий")]
    texts = StudyTexts("G", "C", "R", "H", "A")
    sd = repo.create(StudyDefinition("T", "", tuple(qs), texts))
    repo.activate(sd.study_id)
    active = repo.get_active()
    assert [q.question_id for q in active.questions] == ["a", "b", "c"]


# ── get_by_id ─────────────────────────────────────────────────────────────────

def test_get_by_id_returns_none_for_missing(repo):
    assert repo.get_by_id(9999) is None


def test_get_by_id_returns_correct_study(repo):
    sd = repo.create(_make_sd("Конкретное"))
    retrieved = repo.get_by_id(sd.study_id)
    assert retrieved.title == "Конкретное"


# ── list_all ──────────────────────────────────────────────────────────────────

def test_list_all_empty(repo):
    assert repo.list_all() == []


def test_list_all_returns_all_studies(repo):
    repo.create(_make_sd("A"))
    repo.create(_make_sd("B"))
    repo.create(_make_sd("C"))
    studies = repo.list_all()
    assert len(studies) == 3


# ── _migrate_add_study_id idempotency ─────────────────────────────────────────

def test_migrate_idempotent(session_factory):
    """Повторный вызов _migrate_add_study_id не вызывает ошибку."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    _migrate_add_study_id(engine)
    _migrate_add_study_id(engine)  # второй вызов — не должно быть ошибки
