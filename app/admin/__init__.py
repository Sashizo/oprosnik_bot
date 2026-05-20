"""Web Admin — интерфейс исследователя (M13).

Подключается к FastAPI-приложению через setup_admin().
Маршруты: /admin/studies (CRUD), /admin/studies/{id}/preview, activate.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ADMIN_DIR = Path(__file__).parent
TEMPLATES_DIR = ADMIN_DIR / "templates"
STATIC_DIR = ADMIN_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def setup_admin(app: FastAPI) -> None:
    """Регистрирует admin-router и монтирует статику."""
    from app.admin.router import router as admin_router

    app.mount("/admin/static", StaticFiles(directory=str(STATIC_DIR)), name="admin_static")
    app.include_router(admin_router, prefix="/admin")
