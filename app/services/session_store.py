from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class Session:
    user_id: int
    current_question_index: int = 0          # индекс вопроса, на который ждём ответ
    answers: dict[str, str] = field(default_factory=dict)  # question_id → текст ответа
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    finished: bool = False
    # study_id фиксируется при создании сессии и не меняется,
    # даже если active study переключился в процессе интервью.
    # None = legacy-сессия (до M10, сценарий из interview_script.py).
    study_id: int | None = None


class SessionStore(Protocol):
    """Интерфейс хранилища сессий.

    Реализуется InMemorySessionStore (тесты, запуск без БД)
    и SQLiteSessionStore (production-режим с SQLAlchemy).
    DialogManager зависит только от этого протокола.
    """

    def get_or_create(self, user_id: int) -> Session: ...
    def reset(self, user_id: int) -> Session: ...
    def save(self, session: Session) -> None: ...


class InMemorySessionStore:
    """In-memory реализация SessionStore. Не переживает рестарт процесса."""

    def __init__(self) -> None:
        self._sessions: dict[int, Session] = {}

    def get_or_create(self, user_id: int) -> Session:
        if user_id not in self._sessions:
            self._sessions[user_id] = Session(user_id=user_id)
        return self._sessions[user_id]

    def reset(self, user_id: int) -> Session:
        session = Session(user_id=user_id)
        self._sessions[user_id] = session
        return session

    def save(self, session: Session) -> None:
        # No-op: мутации уже видны через ссылку в словаре.
        pass
