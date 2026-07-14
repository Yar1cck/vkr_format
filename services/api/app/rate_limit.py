"""Глобальный rate-limiter для публичных эндпоинтов аутентификации.

Защищает /auth/login, /auth/register и /auth/refresh от brute-force и
массовой регистрации. Лимит — per remote address; в кластере с Redis
бэкендом счётчики разделяются между инстансами API.

Применение: декоратор `@limiter.limit("10/minute")` на эндпоинте,
которому нужно ограничение. Эндпоинт ДОЛЖЕН иметь параметр `request:
Request` — иначе slowapi не извлечёт IP клиента.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from services.core.vkr_core.config.settings import get_settings

_settings = get_settings()


# В dev / тестах падать на Redis нежелательно (зависимость, которой может не
# быть). slowapi автоматически использует in-memory storage, если URL не
# задан — это приемлемо для одного инстанса. В продакшне с несколькими
# воркерами Uvicorn / Gunicorn нужен Redis, иначе лимиты считаются per
# процесс, а не глобально.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.redis_url or "memory://",
    default_limits=[],  # лимиты ставим per-route, глобальных нет
)
