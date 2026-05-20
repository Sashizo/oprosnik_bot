from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Study(Base):
    """Сценарий исследования (Study Definition).

    texts_json хранит JSON-словарь служебных текстов бота:
    greeting, closing, redirect, help, already_done.
    Это MVP-компромисс: один JSON-столбец проще отдельной таблицы study_texts
    и достаточен для пилота. Не нормализован намеренно.
    """

    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    texts_json: Mapped[str] = mapped_column(Text)   # JSON: greeting/closing/redirect/help/already_done
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    questions: Mapped[list["StudyQuestion"]] = relationship(
        back_populates="study",
        order_by="StudyQuestion.position",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="study")


class StudyQuestion(Base):
    """Один вопрос сценария, привязанный к конкретному Study."""

    __tablename__ = "study_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    study_id: Mapped[int] = mapped_column(ForeignKey("studies.id"))
    position: Mapped[int] = mapped_column(Integer)   # 0-based порядковый номер
    question_id: Mapped[str] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)

    study: Mapped["Study"] = relationship(back_populates="questions")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    current_question_index: Mapped[int] = mapped_column(default=0)
    finished: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Ссылка на Study; NULL = legacy-сессия (до M10, сценарий из interview_script.py).
    # Инвариант: study_id фиксируется при создании сессии и не меняется,
    # даже если active study переключается в процессе интервью.
    study_id: Mapped[int | None] = mapped_column(
        ForeignKey("studies.id"), nullable=True, default=None
    )

    answers: Mapped[list["Answer"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    study: Mapped["Study | None"] = relationship(back_populates="sessions")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id"))
    question_id: Mapped[str] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[datetime]

    session: Mapped["InterviewSession"] = relationship(back_populates="answers")
