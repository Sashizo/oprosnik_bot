"""Smoke-тесты для web-admin endpoints (M13).

Используют FastAPI TestClient (httpx-based, синхронный).
StudyRepository мокается через FastAPI dependency override.
"""

import urllib.parse
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.admin.router import get_study_repo
from app.researcher.schema import QuestionDef, StudyDefinition, StudyTexts


# ── Фабрики ───────────────────────────────────────────────────────────────────

def _make_study(
    study_id: int = 1,
    title: str = "Тест",
    description: str = "",
    n_questions: int = 2,
) -> StudyDefinition:
    questions = tuple(
        QuestionDef(question_id=f"q{i + 1}", text=f"Вопрос {i + 1}")
        for i in range(n_questions)
    )
    texts = StudyTexts(
        greeting="Привет!",
        closing="Спасибо!",
        redirect="Пожалуйста, ответьте подробнее.",
        help="Это исследование.",
        already_done="Вы уже участвовали.",
    )
    return StudyDefinition(
        title=title,
        description=description,
        questions=questions,
        texts=texts,
        study_id=study_id,
    )


def _make_repo(
    studies: list | None = None,
    active_id: int | None = None,
) -> MagicMock:
    """Возвращает мок StudyRepository с настроенными возвращаемыми значениями."""
    repo = MagicMock()
    studies = studies or []

    repo.list_all.return_value = studies
    repo.get_active_orm_id.return_value = active_id
    repo.count_all_sessions.return_value = 0
    repo.count_questions.return_value = 2

    if studies:
        repo.get_by_id.return_value = studies[0]
    else:
        repo.get_by_id.return_value = None

    repo.create.return_value = _make_study(study_id=99)
    repo.update.return_value = True
    repo.activate.return_value = True

    return repo


def _make_client(repo: MagicMock) -> TestClient:
    """Создаёт TestClient с переопределённой зависимостью get_study_repo."""
    app = create_app()
    app.dependency_overrides[get_study_repo] = lambda: repo
    return TestClient(app, follow_redirects=False)


def _post_form(client: TestClient, url: str, pairs: list[tuple[str, str]], **kwargs):
    """Отправляет POST-запрос с form-encoded телом.

    Использует urllib.parse.urlencode для корректной передачи
    повторяющихся полей (q_id, q_text) — то, что httpx TestClient
    не поддерживает через data=list_of_tuples.
    """
    content = urllib.parse.urlencode(pairs).encode()
    return client.post(
        url,
        content=content,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        **kwargs,
    )


def _valid_pairs(
    title: str = "Тестовое исследование",
    n_questions: int = 2,
    greeting: str = "Привет, участник!",
    closing: str = "Спасибо за участие!",
    redirect: str = "Пожалуйста, ответьте подробнее.",
    help: str = "Это исследование.",
    already_done: str = "Вы уже прошли.",
) -> list[tuple[str, str]]:
    """Возвращает list of tuples с валидными данными формы."""
    pairs = [
        ("title", title),
        ("description", ""),
        ("greeting", greeting),
        ("closing", closing),
        ("redirect", redirect),
        ("help", help),
        ("already_done", already_done),
    ]
    for i in range(n_questions):
        pairs.append(("q_id", f"q{i + 1}"))
        pairs.append(("q_text", f"Расскажите о теме {i + 1}"))
    return pairs


# ── GET /admin/ ────────────────────────────────────────────────────────────────

def test_admin_root_redirects_to_studies():
    repo = _make_repo()
    client = _make_client(repo)
    r = client.get("/admin/")
    assert r.status_code == 302
    assert r.headers["location"].endswith("/admin/studies")


# ── GET /admin/studies ─────────────────────────────────────────────────────────

def test_studies_list_empty():
    repo = _make_repo(studies=[])
    client = _make_client(repo)
    r = client.get("/admin/studies")
    assert r.status_code == 200
    assert "Исследований пока нет" in r.text


def test_studies_list_shows_study():
    s = _make_study(study_id=1, title="Мой опрос")
    repo = _make_repo(studies=[s], active_id=None)
    client = _make_client(repo)
    r = client.get("/admin/studies")
    assert r.status_code == 200
    assert "Мой опрос" in r.text


def test_studies_list_active_badge():
    s = _make_study(study_id=3, title="Активный опрос")
    repo = _make_repo(studies=[s], active_id=3)
    client = _make_client(repo)
    r = client.get("/admin/studies")
    assert r.status_code == 200
    assert "Активное" in r.text


def test_studies_list_draft_badge():
    s = _make_study(study_id=2, title="Черновик")
    repo = _make_repo(studies=[s], active_id=None)
    repo.count_all_sessions.return_value = 0
    client = _make_client(repo)
    r = client.get("/admin/studies")
    assert "Черновик" in r.text


def test_studies_list_used_badge():
    s = _make_study(study_id=2, title="Старый опрос")
    repo = _make_repo(studies=[s], active_id=None)
    repo.count_all_sessions.return_value = 5
    client = _make_client(repo)
    r = client.get("/admin/studies")
    assert "Использовано" in r.text


# ── GET /admin/studies/new ────────────────────────────────────────────────────

def test_studies_new_form_returns_200():
    repo = _make_repo()
    client = _make_client(repo)
    r = client.get("/admin/studies/new")
    assert r.status_code == 200
    assert "Новое исследование" in r.text
    assert "<form" in r.text


# ── POST /admin/studies/new ───────────────────────────────────────────────────

def test_studies_new_valid_redirects():
    repo = _make_repo()
    client = _make_client(repo)
    r = _post_form(client, "/admin/studies/new", _valid_pairs())
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/studies")
    repo.create.assert_called_once()


def test_studies_new_empty_title_returns_422():
    repo = _make_repo()
    client = _make_client(repo)
    pairs = _valid_pairs(title="")
    r = _post_form(client, "/admin/studies/new", pairs)
    assert r.status_code == 422
    assert "title" in r.text
    repo.create.assert_not_called()


def test_studies_new_no_questions_returns_422():
    repo = _make_repo()
    client = _make_client(repo)
    pairs = _valid_pairs(n_questions=0)
    r = _post_form(client, "/admin/studies/new", pairs)
    assert r.status_code == 422
    repo.create.assert_not_called()


def test_studies_new_empty_greeting_returns_422():
    repo = _make_repo()
    client = _make_client(repo)
    pairs = _valid_pairs(greeting="")
    r = _post_form(client, "/admin/studies/new", pairs)
    assert r.status_code == 422
    assert "greeting" in r.text


# ── GET /admin/studies/{id}/edit ─────────────────────────────────────────────

def test_studies_edit_form_returns_200():
    s = _make_study(study_id=1, title="Опрос для редактирования")
    repo = _make_repo(studies=[s])
    client = _make_client(repo)
    r = client.get("/admin/studies/1/edit")
    assert r.status_code == 200
    assert "Опрос для редактирования" in r.text


def test_studies_edit_form_not_found():
    repo = _make_repo(studies=[])
    repo.get_by_id.return_value = None
    client = _make_client(repo)
    r = client.get("/admin/studies/999/edit")
    assert r.status_code == 404


def test_studies_edit_form_locked_questions():
    """При наличии сессий показывается предупреждение о блокировке вопросов."""
    s = _make_study(study_id=5)
    repo = _make_repo(studies=[s])
    repo.count_all_sessions.return_value = 3
    client = _make_client(repo)
    r = client.get("/admin/studies/5/edit")
    assert r.status_code == 200
    assert "заблокированы" in r.text


def test_studies_edit_form_allow_full_edit():
    """Без сессий форма показывает полный редактор."""
    s = _make_study(study_id=6)
    repo = _make_repo(studies=[s])
    repo.count_all_sessions.return_value = 0
    client = _make_client(repo)
    r = client.get("/admin/studies/6/edit")
    assert r.status_code == 200
    assert "Добавить вопрос" in r.text


# ── POST /admin/studies/{id}/edit ─────────────────────────────────────────────

def test_studies_edit_valid_redirects():
    s = _make_study(study_id=1)
    repo = _make_repo(studies=[s])
    repo.count_all_sessions.return_value = 0
    client = _make_client(repo)
    r = _post_form(client, "/admin/studies/1/edit", _valid_pairs())
    assert r.status_code == 303
    repo.update.assert_called_once()


def test_studies_edit_not_found():
    repo = _make_repo(studies=[])
    repo.get_by_id.return_value = None
    client = _make_client(repo)
    r = _post_form(client, "/admin/studies/999/edit", _valid_pairs())
    assert r.status_code == 404


def test_studies_edit_invalid_returns_422():
    s = _make_study(study_id=1)
    repo = _make_repo(studies=[s])
    client = _make_client(repo)
    r = _post_form(client, "/admin/studies/1/edit", _valid_pairs(title=""))
    assert r.status_code == 422
    repo.update.assert_not_called()


# ── GET /admin/studies/{id}/preview ──────────────────────────────────────────

def test_studies_preview_returns_200():
    s = _make_study(study_id=1, title="Превью опрос")
    repo = _make_repo(studies=[s])
    client = _make_client(repo)
    r = client.get("/admin/studies/1/preview")
    assert r.status_code == 200
    assert "Превью опрос" in r.text
    assert "Привет!" in r.text         # greeting
    assert "Спасибо!" in r.text        # closing
    assert "Вопрос 1" in r.text


def test_studies_preview_not_found():
    repo = _make_repo(studies=[])
    repo.get_by_id.return_value = None
    client = _make_client(repo)
    r = client.get("/admin/studies/999/preview")
    assert r.status_code == 404


def test_studies_preview_active_badge():
    s = _make_study(study_id=3)
    repo = _make_repo(studies=[s], active_id=3)
    client = _make_client(repo)
    r = client.get("/admin/studies/3/preview")
    assert "Сейчас активное" in r.text


def test_studies_preview_shows_activate_button_when_not_active():
    s = _make_study(study_id=2)
    repo = _make_repo(studies=[s], active_id=1)
    client = _make_client(repo)
    r = client.get("/admin/studies/2/preview")
    assert "Активировать" in r.text


# ── POST /admin/studies/{id}/activate ────────────────────────────────────────

def test_studies_activate_redirects():
    repo = _make_repo()
    client = _make_client(repo)
    r = client.post("/admin/studies/1/activate")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/studies")
    repo.activate.assert_called_once_with(1)


def test_studies_activate_calls_repo_with_correct_id():
    repo = _make_repo()
    client = _make_client(repo)
    client.post("/admin/studies/42/activate")
    repo.activate.assert_called_once_with(42)


# ── Static files ──────────────────────────────────────────────────────────────

def test_static_css_accessible():
    repo = _make_repo()
    client = _make_client(repo)
    r = client.get("/admin/static/admin.css")
    assert r.status_code == 200
    assert "text/css" in r.headers.get("content-type", "")


def test_static_js_accessible():
    repo = _make_repo()
    client = _make_client(repo)
    r = client.get("/admin/static/admin.js")
    assert r.status_code == 200
