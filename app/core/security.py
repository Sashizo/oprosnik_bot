"""HTTP Basic Auth для web-admin (M14 — Security Hardening Baseline).

require_admin — FastAPI Depends()-dependency.
Подключается к router как: router = APIRouter(dependencies=[Depends(require_admin)])

Почему Basic Auth:
  - Встроен в FastAPI (HTTPBasic), нет доп. зависимостей
  - secrets.compare_digest предотвращает timing attack
  - Браузер сохраняет credentials в сессии — не нужно вводить каждый раз
  - Достаточно для localhost/LAN использования
  - Session cookies потребовали бы login-страницу и хранилище сессий

Ограничение: без HTTPS credentials передаются base64-encoded (не зашифрованы).
Не использовать без TLS при публичном размещении.
"""

import logging
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings

logger = logging.getLogger(__name__)

# auto_error=False: если заголовок Authorization отсутствует, FastAPI возвращает
# credentials=None вместо автоматического 401. Это позволяет require_admin
# самостоятельно решать, открыть доступ (dev-mode) или потребовать авторизацию.
_http_basic = HTTPBasic(auto_error=False)


def require_admin(
    credentials: Optional[HTTPBasicCredentials] = Depends(_http_basic),
) -> None:
    """FastAPI dependency — проверяет Basic Auth для /admin/* маршрутов.

    При пустом ADMIN_PASSWORD в settings доступ открыт без авторизации
    (dev-mode; предупреждение логируется в lifespan в main.py).
    """
    # Dev-mode: пароль не задан — admin открыт.
    if not settings.admin_password:
        return

    # Пароль задан, но credentials не предоставлены → 401 с www-authenticate.
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

    correct_user = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.admin_username.encode("utf-8"),
    )
    correct_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )

    if not (correct_user and correct_pass):
        logger.warning("[AUDIT] action=admin_auth_failed username=%r", credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
