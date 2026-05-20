import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.repository import SQLiteSessionStore


@pytest.fixture
def store() -> SQLiteSessionStore:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SQLiteSessionStore(sessionmaker(bind=engine))


def test_get_or_create_returns_fresh_session(store):
    s = store.get_or_create(user_id=1)
    assert s.user_id == 1
    assert s.current_question_index == 0
    assert s.finished is False
    assert s.answers == {}


def test_save_and_reload_answer(store):
    s = store.get_or_create(user_id=1)
    s.answers["q1"] = "мой ответ"
    s.current_question_index = 1
    store.save(s)

    reloaded = store.get_or_create(user_id=1)
    assert reloaded.answers["q1"] == "мой ответ"
    assert reloaded.current_question_index == 1


def test_reset_gives_clean_session(store):
    s = store.get_or_create(user_id=1)
    s.answers["q1"] = "ответ"
    s.current_question_index = 1
    store.save(s)

    s2 = store.reset(user_id=1)
    assert s2.current_question_index == 0
    assert s2.answers == {}


def test_two_users_are_isolated(store):
    s1 = store.get_or_create(user_id=1)
    s1.answers["q1"] = "ответ user 1"
    store.save(s1)

    s2 = store.get_or_create(user_id=2)
    assert "q1" not in s2.answers
