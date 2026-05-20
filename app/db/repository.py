from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker, Session as SASession, joinedload

from app.db.models import InterviewSession, Answer
from app.services.session_store import Session


class SQLiteSessionStore:
    """SessionStore backed by SQLite via SQLAlchemy ORM.

    Implements the SessionStore Protocol:  get_or_create / reset / save.
    Each method opens and closes its own DB session via a context manager.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._factory = session_factory

    # ------------------------------------------------------------------
    # Public interface (SessionStore Protocol)
    # ------------------------------------------------------------------

    def get_or_create(self, user_id: int) -> Session:
        with self._factory() as db:
            orm = self._latest_active(db, user_id)
            if orm is None:
                return self._new_session_in_db(db, user_id)
            return self._to_dataclass(orm)

    def reset(self, user_id: int) -> Session:
        with self._factory() as db:
            return self._new_session_in_db(db, user_id)

    def save(self, session: Session) -> None:
        with self._factory() as db:
            orm = self._latest_active(db, session.user_id)
            if orm is None:
                return  # session was already reset — nothing to update

            orm.current_question_index = session.current_question_index
            orm.finished = session.finished
            if session.finished and orm.finished_at is None:
                orm.finished_at = datetime.now(timezone.utc)

            # INSERT-only: добавляем только новые ответы, без UPDATE существующих.
            existing_qids = {a.question_id for a in orm.answers}
            for q_id, text in session.answers.items():
                if q_id not in existing_qids:
                    db.add(Answer(
                        session_id=orm.id,
                        question_id=q_id,
                        text=text,
                        answered_at=datetime.now(timezone.utc),
                    ))

            db.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _latest_active(self, db: SASession, user_id: int) -> InterviewSession | None:
        return (
            db.query(InterviewSession)
            .filter_by(user_id=user_id, finished=False)
            .order_by(InterviewSession.started_at.desc())
            .first()
        )

    def _new_session_in_db(self, db: SASession, user_id: int, study_id: int | None = None) -> Session:
        orm = InterviewSession(
            user_id=user_id,
            started_at=datetime.now(timezone.utc),
            study_id=study_id,
        )
        db.add(orm)
        db.commit()
        return Session(user_id=user_id, study_id=study_id)

    def _to_dataclass(self, orm: InterviewSession) -> Session:
        return Session(
            user_id=orm.user_id,
            current_question_index=orm.current_question_index,
            answers={a.question_id: a.text for a in orm.answers},
            started_at=orm.started_at,
            finished=orm.finished,
            study_id=orm.study_id,
        )


# ── Аналитика (read-only, вне Protocol SessionStore) ─────────────────────────

def get_all_sessions(session_factory: sessionmaker) -> list:
    """Возвращает все сессии с ответами в виде list[SessionRecord].

    Read-only утилита для аналитики/экспорта. Не является частью Protocol SessionStore
    и не используется в runtime бота.

    Импорт SessionRecord/AnswerRecord отложен (lazy) чтобы избежать
    циклических импортов на уровне модуля.
    """
    from app.analysis.export import AnswerRecord, SessionRecord

    with session_factory() as db:
        rows = (
            db.query(InterviewSession)
            .options(joinedload(InterviewSession.answers))
            .order_by(InterviewSession.started_at)
            .all()
        )
        return [
            SessionRecord(
                session_id=r.id,
                user_id=r.user_id,
                started_at=r.started_at,
                finished_at=r.finished_at,
                finished=r.finished,
                current_question_index=r.current_question_index,
                study_id=r.study_id,
                answers=[
                    AnswerRecord(
                        question_id=a.question_id,
                        text=a.text,
                        answered_at=a.answered_at,
                    )
                    for a in sorted(r.answers, key=lambda x: x.answered_at)
                ],
            )
            for r in rows
        ]
