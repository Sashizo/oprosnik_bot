from sqlalchemy import create_engine, Engine, text
from sqlalchemy.orm import sessionmaker, Session as SASession

from app.db.models import Base


def build_engine(database_url: str) -> Engine:
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        # check_same_thread=False needed because python-telegram-bot
        # dispatches handlers from a thread pool, not the main thread.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[SASession]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_add_updated_at(engine: Engine) -> None:
    """Идемпотентное добавление колонки updated_at в studies.

    Колонка добавлена в M13 для отображения даты последнего редактирования
    в web-admin. При повторном вызове ALTER TABLE не выполняется.
    """
    with engine.connect() as conn:
        cols = [
            row[1]
            for row in conn.execute(text("PRAGMA table_info(studies)"))
        ]
        if "updated_at" not in cols:
            conn.execute(text(
                "ALTER TABLE studies ADD COLUMN updated_at DATETIME"
            ))
            conn.commit()


def _migrate_add_study_id(engine: Engine) -> None:
    """Идемпотентное добавление колонки study_id в interview_sessions.

    SQLite поддерживает ADD COLUMN для nullable-колонок нативно.
    PRAGMA-проверка гарантирует идемпотентность: при повторном вызове
    ALTER TABLE не выполняется.
    """
    with engine.connect() as conn:
        cols = [
            row[1]
            for row in conn.execute(text("PRAGMA table_info(interview_sessions)"))
        ]
        if "study_id" not in cols:
            conn.execute(text(
                "ALTER TABLE interview_sessions "
                "ADD COLUMN study_id INTEGER REFERENCES studies(id)"
            ))
            conn.commit()


def init_db(engine: Engine) -> None:
    """Создаёт все таблицы и выполняет идемпотентные миграции.

    Шаг А: Base.metadata.create_all() создаёт новые таблицы (studies, study_questions)
           если они ещё не существуют.
    Шаг Б: _migrate_add_study_id() добавляет колонку study_id в interview_sessions
           если она отсутствует (для БД, созданных до M10).

    Note: этот подход без Alembic работает только для additive-изменений.
    При структурных изменениях схемы рекомендуется перейти на Alembic (M11+).
    """
    Base.metadata.create_all(engine)
    _migrate_add_study_id(engine)
    _migrate_add_updated_at(engine)
