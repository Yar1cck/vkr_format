"""Blacklist отозванных JWT (logout, force-signout админом).

Хранится в Redis с TTL равным оставшемуся времени жизни токена. После
TTL запись сама протухает — токен всё равно был бы недействителен по
истечении.

Важно: при недоступности Redis НЕ блокируем запросы. Лучше пропустить
проверку (с warning в логах) чем устроить полный auth-outage. Это
trade-off в пользу availability — security-импликация ограничена тем
окном, когда Redis недоступен.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import redis.asyncio as aioredis

from services.core.vkr_core.config.settings import get_settings

_settings = get_settings()
_logger = logging.getLogger(__name__)
_KEY_TEMPLATE = "vkr:revoked_jti:{jti}"

_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(_settings.redis_url, decode_responses=True)
    return _redis_client


async def revoke_jti(jti: str | None, expires_at: datetime) -> None:
    """Помечает jti как отозванный до момента expires_at.

    expires_at должен быть aware-datetime (с tzinfo). Если уже истёк —
    операция no-op.
    """
    if not jti:
        return
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        return
    ttl = max(int((expires_at - now).total_seconds()), 1)
    try:
        await _get_redis().set(_KEY_TEMPLATE.format(jti=jti), "1", ex=ttl)
    except Exception:
        _logger.exception("Failed to revoke jti=%s in Redis", jti)


async def is_jti_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    try:
        return bool(await _get_redis().exists(_KEY_TEMPLATE.format(jti=jti)))
    except Exception:
        _logger.exception("Failed to check revocation for jti=%s", jti)
        # Fail-open: при недоступности Redis авторизация продолжает
        # работать. Альтернатива (fail-closed) сделала бы Redis SPOF
        # для всего сервиса.
        return False
