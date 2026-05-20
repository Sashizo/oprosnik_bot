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

from typing import Annotated

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin import templates
from app.core.config import settings
from app.core.security import require_admin
from app.db.database import build_engine, build_session_factory
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


RepoDep = Annotated[StudyRepository, Depends(get_study_repo)]


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

    return templates.TemplateResponse(request, "studies_list.html", {"rows": rows})


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
    """Активирует исследование; деактивирует остальные."""
    repo.activate(study_id)
    logger.info("[AUDIT] action=admin_activate_study study_id=%d", study_id)
    return RedirectResponse(url="/admin/studies", status_code=303)
