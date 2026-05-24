"""FastAPI router для web-admin исследователя (M13).

Маршруты:
  GET  /admin/              → redirect → /admin/studies
  GET  /admin/studies       → список всех исследований
  GET  /admin/studies/new   → пустая форма создания
  POST /admin/studies/new   → создать study, redirect → list
  GET  /admin/studies/{id}/edit    → форма редактирования
  POST /admin/studies/{id}/edit    → обновить study, redirect → list
  GET  /admin/studies/{id}/preview → preview сценария
  POST /admin/studies/{id}/activate → активировать, redirect → list
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app.admin import templates
from app.analysis.metrics import (
    avg_answer_length,
    completion_rate,
    dropout_distribution,
    duration_stats,
)
from app.core.config import settings
from app.core.security import require_admin
from app.db.database import build_engine, build_session_factory
from app.db.repository import get_all_sessions
from app.researcher.repository import StudyRepository
from app.researcher.schema import QuestionDef, StudyDefinition, StudyTexts, validate

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])

# ── Dependency injection ──────────────────────────────────────────────────────


def get_study_repo() -> StudyRepository:
    """FastAPI dependency — создаёт StudyRepository для каждого запроса.

    MVP: создаём engine на запрос. Для одного пользователя это приемлемо.
    Оптимизация (lifespan-managed engine) — deferred.
    """
    engine = build_engine(settings.database_url)
    sf = build_session_factory(engine)
    return StudyRepository(sf)


def get_session_factory():
    """FastAPI dependency — создаёт session_factory для analytics-маршрутов."""
    engine = build_engine(settings.database_url)
    return build_session_factory(engine)


RepoDep = Annotated[StudyRepository, Depends(get_study_repo)]
SFDep = Annotated[object, Depends(get_session_factory)]


# ── Вспомогательные функции ───────────────────────────────────────────────────


def _parse_questions_from_form(
    q_text: list[str],
    q_id: list[str],
) -> tuple[tuple[QuestionDef, ...], list[str]]:
    """Собирает кортеж QuestionDef из параллельных списков текстов и id.

    Возвращает (questions, form_errors).
    form_errors непусто, если количество элементов не совпадает.
    """
    errors: list[str] = []

    if len(q_text) != len(q_id):
        errors.append("Несоответствие количества id и текстов вопросов.")
        return (), errors

    questions = tuple(
        QuestionDef(question_id=qid.strip(), text=txt.strip())
        for qid, txt in zip(q_id, q_text)
    )
    return questions, errors


# ── Маршруты ─────────────────────────────────────────────────────────────────


@router.get("/", include_in_schema=False)
async def admin_root():
    return RedirectResponse(url="/admin/studies", status_code=302)


@router.get("/studies", response_class=HTMLResponse)
async def studies_list(request: Request, repo: RepoDep):
    """Список всех исследований с агрегированными данными."""
    activated = request.query_params.get("activated") == "1"
    all_studies = repo.list_all()
    active_id = repo.get_active_orm_id()

    rows = []
    for sd in all_studies:
        sid = sd.study_id
        total = repo.count_all_sessions(sid)
        n_q = repo.count_questions(sid)
        is_active = (sid == active_id)

        if is_active:
            status = "active"
        elif total > 0:
            status = "used"
        else:
            status = "draft"

        rows.append({
            "study_id": sid,
            "title": sd.title,
            "n_questions": n_q,
            "total_sessions": total,
            "is_active": is_active,
            "status": status,
        })

    return templates.TemplateResponse(request, "studies_list.html", {
        "rows": rows,
        "activated": activated,
    })


@router.get("/studies/new", response_class=HTMLResponse)
async def studies_new_form(request: Request):
    """Пустая форма создания исследования."""
    return templates.TemplateResponse(request, "study_form.html", {
        "title": "Новое исследование",
        "study": None,
        "questions": [],
        "allow_question_changes": True,
        "errors": [],
        "form": {},
    })


@router.post("/studies/new")
async def studies_new_submit(
    request: Request,
    repo: RepoDep,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    q_text: Annotated[list[str], Form()] = [],
    q_id: Annotated[list[str], Form()] = [],
    greeting: Annotated[str, Form()] = "",
    closing: Annotated[str, Form()] = "",
    redirect: Annotated[str, Form()] = "",
    help: Annotated[str, Form()] = "",
    already_done: Annotated[str, Form()] = "",
):
    """Создаёт новое исследование; при ошибках возвращает форму с сообщениями."""
    questions, parse_errors = _parse_questions_from_form(q_text, q_id)

    sd = StudyDefinition(
        title=title.strip(),
        description=description.strip(),
        questions=questions,
        texts=StudyTexts(
            greeting=greeting.strip(),
            closing=closing.strip(),
            redirect=redirect.strip(),
            help=help.strip(),
            already_done=already_done.strip(),
        ),
    )
    errors = parse_errors + validate(sd)

    if errors:
        return templates.TemplateResponse(
            request,
            "study_form.html",
            {
                "title": "Новое исследование",
                "study": None,
                "questions": [
                    {"question_id": qid, "text": txt}
                    for qid, txt in zip(q_id, q_text)
                ],
                "allow_question_changes": True,
                "errors": errors,
                "form": {
                    "title": title,
                    "description": description,
                    "greeting": greeting,
                    "closing": closing,
                    "redirect": redirect,
                    "help": help,
                    "already_done": already_done,
                },
            },
            status_code=422,
        )

    created = repo.create(sd)
    logger.info("[AUDIT] action=admin_create_study study_id=%d title=%r",
                created.study_id, created.title)
    return RedirectResponse(url="/admin/studies", status_code=303)


@router.get("/studies/{study_id}/edit", response_class=HTMLResponse)
async def studies_edit_form(request: Request, study_id: int, repo: RepoDep):
    """Форма редактирования существующего исследования."""
    sd = repo.get_by_id(study_id)
    if sd is None:
        return HTMLResponse("<h1>Исследование не найдено</h1>", status_code=404)

    total = repo.count_all_sessions(study_id)
    allow_q = (total == 0)

    return templates.TemplateResponse(request, "study_form.html", {
        "title": f"Редактировать: {sd.title}",
        "study": {"study_id": study_id, "title": sd.title},
        "questions": [
            {"question_id": q.question_id, "text": q.text}
            for q in sd.questions
        ],
        "allow_question_changes": allow_q,
        "errors": [],
        "form": {
            "title": sd.title,
            "description": sd.description,
            "greeting": sd.texts.greeting,
            "closing": sd.texts.closing,
            "redirect": sd.texts.redirect,
            "help": sd.texts.help,
            "already_done": sd.texts.already_done,
        },
    })


@router.post("/studies/{study_id}/edit")
async def studies_edit_submit(
    request: Request,
    study_id: int,
    repo: RepoDep,
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    q_text: Annotated[list[str], Form()] = [],
    q_id: Annotated[list[str], Form()] = [],
    greeting: Annotated[str, Form()] = "",
    closing: Annotated[str, Form()] = "",
    redirect: Annotated[str, Form()] = "",
    help: Annotated[str, Form()] = "",
    already_done: Annotated[str, Form()] = "",
):
    """Обновляет существующее исследование."""
    sd_existing = repo.get_by_id(study_id)
    if sd_existing is None:
        return HTMLResponse("<h1>Исследование не найдено</h1>", status_code=404)

    total = repo.count_all_sessions(study_id)
    allow_q = (total == 0)

    questions, parse_errors = _parse_questions_from_form(q_text, q_id)

    sd = StudyDefinition(
        title=title.strip(),
        description=description.strip(),
        questions=questions,
        texts=StudyTexts(
            greeting=greeting.strip(),
            closing=closing.strip(),
            redirect=redirect.strip(),
            help=help.strip(),
            already_done=already_done.strip(),
        ),
    )
    errors = parse_errors + validate(sd)

    if errors:
        return templates.TemplateResponse(
            request,
            "study_form.html",
            {
                "title": f"Редактировать: {sd_existing.title}",
                "study": {"study_id": study_id, "title": sd_existing.title},
                "questions": [
                    {"question_id": qid, "text": txt}
                    for qid, txt in zip(q_id, q_text)
                ],
                "allow_question_changes": allow_q,
                "errors": errors,
                "form": {
                    "title": title,
                    "description": description,
                    "greeting": greeting,
                    "closing": closing,
                    "redirect": redirect,
                    "help": help,
                    "already_done": already_done,
                },
            },
            status_code=422,
        )

    repo.update(study_id, sd, allow_question_changes=allow_q)
    logger.info("[AUDIT] action=admin_update_study study_id=%d", study_id)
    return RedirectResponse(url="/admin/studies", status_code=303)


@router.get("/studies/{study_id}/preview", response_class=HTMLResponse)
async def studies_preview(request: Request, study_id: int, repo: RepoDep):
    """Preview сценария — как увидит респондент."""
    sd = repo.get_by_id(study_id)
    if sd is None:
        return HTMLResponse("<h1>Исследование не найдено</h1>", status_code=404)

    active_id = repo.get_active_orm_id()
    return templates.TemplateResponse(request, "preview.html", {
        "study": sd,
        "is_active": (study_id == active_id),
        "questions": list(sd.questions),
    })


@router.post("/studies/{study_id}/activate")
async def studies_activate(study_id: int, repo: RepoDep):
    """Активирует исследование; деактивирует остальные.

    Обновляет БД, после чего редиректит на список с уведомлением.
    Внимание: бот-процесс (interview-bot.service) читает активное исследование
    только при запуске. Для немедленного применения используйте активацию
    через Telegram /researcher → Активировать, либо перезапустите сервис:
        sudo systemctl restart interview-bot
    """
    repo.activate(study_id)
    logger.info("[AUDIT] action=admin_activate_study study_id=%d", study_id)
    return RedirectResponse(url="/admin/studies?activated=1", status_code=303)


# ── Analytics ─────────────────────────────────────────────────────────────────


def _build_csv_bytes(sessions) -> bytes:
    """Генерирует CSV в памяти и возвращает bytes.

    Логика идентична app/analysis/export.to_csv(), но без записи на диск.
    Импорт из analysis.export допустим — это не bot-слой.
    """
    from app.analysis.export import CSV_HEADERS, _build_q_map_cache, duration_minutes

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADERS)
    writer.writeheader()

    q_maps = _build_q_map_cache(sessions)
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
            writer.writerow({
                **base,
                "question_id": "",
                "question_text": "",
                "answer_text": "",
                "answered_at": "",
                "answer_length_chars": "",
            })

    return buf.getvalue().encode("utf-8")


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, repo: RepoDep, sf: SFDep):
    """Страница аналитики активного исследования."""
    active_study = repo.get_active()

    sessions = get_all_sessions(sf)

    # Фильтруем по активному исследованию, если оно задано.
    if active_study is not None:
        sessions = [s for s in sessions if s.study_id == active_study.study_id]

    total_sessions = len(sessions)
    finished_sessions = sum(1 for s in sessions if s.finished)
    completion_pct = round(completion_rate(sessions) * 100, 1)
    dropout = dropout_distribution(sessions)
    avg_lengths = avg_answer_length(sessions)
    duration = duration_stats(sessions)

    # Для таблицы avg_lengths — добавляем текст вопроса, если есть active_study.
    q_text_map: dict[str, str] = {}
    if active_study is not None:
        q_text_map = {q.question_id: q.text for q in active_study.questions}

    logger.info("[AUDIT] action=admin_view_analytics user=admin")
    return templates.TemplateResponse(request, "analytics.html", {
        "active_study": active_study,
        "n_questions": len(active_study.questions) if active_study else 0,
        "total_sessions": total_sessions,
        "finished_sessions": finished_sessions,
        "completion_pct": completion_pct,
        "dropout": dropout,
        "avg_lengths": avg_lengths,
        "q_text_map": q_text_map,
        "duration": duration,
    })


@router.get("/analytics/export")
async def analytics_export(repo: RepoDep, sf: SFDep):
    """Скачать все сессии активного исследования в CSV."""
    active_study = repo.get_active()

    sessions = get_all_sessions(sf)
    if active_study is not None:
        sessions = [s for s in sessions if s.study_id == active_study.study_id]

    csv_bytes = _build_csv_bytes(sessions)
    filename = f"export_{date.today().isoformat()}.csv"

    logger.info(
        "[AUDIT] action=admin_export_csv study_id=%s rows=%d",
        active_study.study_id if active_study else "all",
        len(sessions),
    )
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
