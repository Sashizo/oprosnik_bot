"""Per-user sliding window rate limiter для Telegram-бота (M14).

InMemoryRateLimiter хранит временные метки вызовов в памяти (dict).
Подходит для одного процесса — при перезапуске счётчики сбрасываются.

Гарантии concurrency:
  Python GIL защищает dict-операции на уровне байткода.
  Для единственного asyncio event loop это безопасно без явных Lock'ов.
  Если перейти на многопоточный сервер — добавить threading.Lock.

Использование:
    limiter = InMemoryRateLimiter(max_calls=10, window_seconds=60)
    if not limiter.is_allowed(user_id):
        # rate limit exceeded
"""

import time
from collections import defaultdict


class InMemoryRateLimiter:
    """Sliding window rate limiter без внешних зависимостей.

    max_calls:       максимальное число вызовов за window_seconds
    window_seconds:  ширина скользящего окна в секундах
    """

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self._log: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, user_id: int) -> bool:
        """Возвращает True если вызов разрешён, False если лимит превышен.

        Побочный эффект: при разрешённом вызове добавляет временную метку.
        """
        now = time.monotonic()
        log = self._log[user_id]
        # Удаляем устаревшие метки за пределами окна
        log[:] = [t for t in log if now - t < self.window]
        if len(log) >= self.max_calls:
            return False
        log.append(now)
        return True

    def reset(self, user_id: int) -> None:
        """Сбрасывает счётчик для конкретного пользователя (тесты, бан-lift)."""
        self._log.pop(user_id, None)

    def remaining(self, user_id: int) -> int:
        """Возвращает оставшееся число разрешённых вызовов в текущем окне."""
        now = time.monotonic()
        log = self._log[user_id]
        active = [t for t in log if now - t < self.window]
        return max(0, self.max_calls - len(active))
