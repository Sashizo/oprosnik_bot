"""Репозиторий для хранения и получения Study из SQLite.

StudyRepository — CRUD для Study/StudyQuestion ORM-объектов.
Использует session_factory (не Engine напрямую), чтобы не нарушать
текущий паттерн работы с БД (SQLiteSessionStore).
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker, joinedload

from app.db.models import Study as StudyORM, StudyQuestion as StudyQuestionORM
from app.researcher.schema import QuestionDef, StudyDefinition, StudyTexts


class StudyRepository:
    """CRUD для Study.

    Методы: create, get_active, get_by_id, list_all, activate.
    Все операции записи коммитятся внутри метода.
    """

    def __init__(self, session_factory: sessionmaker) -> None:
        self._factory = session_factory

    # ── Запись ────────────────────────────────────────────────────────────────

    def create(self, sd: StudyDefinition) -> StudyDefinition:
        """Создаёт Study в БД. Возвращает StudyDefinition с заполненным study_id.

        Не активирует — вызовите activate(study_id) отдельно.
        """
        texts_json = json.dumps({
            "greeting": sd.texts.greeting,
            "closing": sd.texts.closing,
            "redirect": sd.texts.redirect,
            "help": sd.texts.help,
            "already_done": sd.texts.already_done,
        }, ensure_ascii=False)

        with self._factory() as db:
            orm = StudyORM(
                title=sd.title,
                description=sd.description,
                texts_json=texts_json,
                is_active=False,
                created_at=datetime.now(timezone.utc),
            )
            db.add(orm)
            db.flush()  # чтобы получить orm.id до commit

            for pos, q in enumerate(sd.questions):
                db.add(StudyQuestionORM(
                    study_id=orm.id,
                    position=pos,
                    question_id=q.question_id,
                    text=q.text,
                ))

            db.commit()
            study_id = orm.id

        return StudyDefinition(
            title=sd.title,
            description=sd.description,
            questions=sd.questions,
            texts=sd.texts,
            study_id=study_id,
        )

    def update(
        self,
        study_id: int,
        sd: StudyDefinition,
        allow_question_changes: bool,
    ) -> bool:
        """Обновляет Study в БД. Возвращает True если study_id найден.

        allow_question_changes=True  → title, description, texts, вопросы (полное пересоздание)
        allow_question_changes=False → title, description, texts; у вопросов только text (по позиции)

        В обоих случаях updated_at выставляется в текущее UTC-время.
        """
        texts_json = json.dumps({
            "greeting": sd.texts.greeting,
            "closing": sd.texts.closing,
            "redirect": sd.texts.redirect,
            "help": sd.texts.help,
            "already_done": sd.texts.already_done,
        }, ensure_ascii=False)

        with self._factory() as db:
            orm = (
                db.query(StudyORM)
                .options(joinedload(StudyORM.questions))
                .filter_by(id=study_id)
                .first()
            )
            if orm is None:
                return False

            orm.title = sd.title
            orm.description = sd.description
            orm.texts_json = texts_json
            orm.updated_at = datetime.now(timezone.utc)

            if allow_question_changes:
                # Удаляем старые вопросы и вставляем новые
                for q_orm in list(orm.questions):
                    db.delete(q_orm)
                db.flush()
                for pos, q in enumerate(sd.questions):
                    db.add(StudyQuestionORM(
                        study_id=study_id,
                        position=pos,
                        question_id=q.question_id,
                        text=q.text,
                    ))
            else:
                # Обновляем только text существующих вопросов (по позиции)
                existing = sorted(orm.questions, key=lambda x: x.position)
                for pos, q in enumerate(sd.questions):
                    if pos < len(existing):
                        existing[pos].text = q.text

            db.commit()
        return True

    def activate(self, study_id: int) -> bool:
        """Делает Study активным; деактивирует все остальные.

        Возвращает True если study_id найден, False если нет.
        """
        with self._factory() as db:
            target = db.query(StudyORM).filter_by(id=study_id).first()
            if target is None:
                return False
            # Деактивируем все
            db.query(StudyORM).filter(StudyORM.is_active.is_(True)).update(
                {"is_active": False}
            )
            target.is_active = True
            db.commit()
        return True

    # ── Чтение ────────────────────────────────────────────────────────────────

    def get_active(self) -> StudyDefinition | None:
        """Возвращает активный Study или None если ни одного не активировано.

        None означает legacy-режим: бот использует interview_script.py.
        """
        with self._factory() as db:
            orm = (
                db.query(StudyORM)
                .options(joinedload(StudyORM.questions))
                .filter_by(is_active=True)
                .first()
            )
            if orm is None:
                return None
            return self._to_definition(orm)

    def get_by_id(self, study_id: int) -> StudyDefinition | None:
        """Возвращает StudyDefinition по id или None."""
        with self._factory() as db:
            orm = (
                db.query(StudyORM)
                .options(joinedload(StudyORM.questions))
                .filter_by(id=study_id)
                .first()
            )
            if orm is None:
                return None
            return self._to_definition(orm)

    def list_all(self) -> list[StudyDefinition]:
        """Возвращает все Study (кратко — без вопросов для производительности)."""
        with self._factory() as db:
            rows = db.query(StudyORM).order_by(StudyORM.created_at).all()
            return [
                StudyDefinition(
                    title=r.title,
                    description=r.description,
                    questions=(),         # не загружаем вопросы для list
                    texts=StudyTexts(
                        greeting="", closing="", redirect="", help="", already_done=""
                    ),
                    study_id=r.id,
                )
                for r in rows
            ]

    def count_all_sessions(self, study_id: int) -> int:
        """Количество всех сессий для данного Study (любой статус finished/active)."""
        from app.db.models import InterviewSession
        with self._factory() as db:
            return (
                db.query(InterviewSession)
                .filter_by(study_id=study_id)
                .count()
            )

    def count_questions(self, study_id: int) -> int:
        """Количество вопросов в данном Study."""
        with self._factory() as db:
            return (
                db.query(StudyQuestionORM)
                .filter_by(study_id=study_id)
                .count()
            )

    def count_unfinished(self, study_id: int) -> int:
        """Количество незавершённых сессий для данного Study."""
        from app.db.models import InterviewSession
        with self._factory() as db:
            return (
                db.query(InterviewSession)
                .filter_by(study_id=study_id, finished=False)
                .count()
            )

    def get_active_orm_id(self) -> int | None:
        """Возвращает id текущего активного Study или None (без загрузки вопросов)."""
        with self._factory() as db:
            row = db.query(StudyORM.id).filter_by(is_active=True).first()
            return row[0] if row else None

    # ── Приватные хелперы ─────────────────────────────────────────────────────

    def _to_definition(self, orm: StudyORM) -> StudyDefinition:
        texts_data = json.loads(orm.texts_json)
        texts = StudyTexts(
            greeting=texts_data.get("greeting", ""),
            closing=texts_data.get("closing", ""),
            redirect=texts_data.get("redirect", ""),
            help=texts_data.get("help", ""),
            already_done=texts_data.get("already_done", ""),
        )
        questions = tuple(
            QuestionDef(question_id=q.question_id, text=q.text)
            for q in sorted(orm.questions, key=lambda x: x.position)
        )
        return StudyDefinition(
            title=orm.title,
            description=orm.description,
            questions=questions,
            texts=texts,
            study_id=orm.id,
        )
