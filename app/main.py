import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.admin import setup_admin
from app.api.health import router as health_router
from app.core.config import settings
from app.db.database import build_engine, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запускает идемпотентные миграции БД и security-checks при старте uvicorn."""
    engine = build_engine(settings.database_url)
    init_db(engine)

    if not settings.admin_password:
        logger.warning(
            "ADMIN_PASSWORD is not set — web admin is accessible without a password. "
            "Set ADMIN_PASSWORD in .env before deploying."
        )

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Interview Bot", lifespan=lifespan)
    app.include_router(health_router)
    setup_admin(app)

    # ── Глобальный обработчик необработанных исключений ───────────────────────
    # Логирует детали в файл/stderr, но не показывает stack trace пользователю.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "[ERROR] Unhandled exception on %s %s: %s",
            request.method, request.url.path, exc,
            exc_info=True,
        )
        if request.url.path.startswith("/admin"):
            return HTMLResponse(
                "<h1>Произошла внутренняя ошибка</h1>"
                "<p><a href='/admin/studies'>← Вернуться к списку исследований</a></p>",
                status_code=500,
            )
        return JSONResponse(
            status_code=500,
            content={"detail": "Внутренняя ошибка сервера"},
        )

    return app


app = create_app()
