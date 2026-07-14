from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import update

from services.api.app.rate_limit import limiter
from services.api.app.routers import admin, auth, documents, normative, violations
from services.core.vkr_core.config.settings import get_settings
from services.core.vkr_core.db.session import AsyncSessionLocal
from services.core.vkr_core.models import Document, DocumentStatus
from services.core.vkr_core.services import ensure_default_normative
from services.core.vkr_core.services.antivirus_service import check_antivirus_available

settings = get_settings()


def _check_jwt_secret_for_env() -> None:
    """В non-dev окружении JWT_SECRET не должен быть дефолтным или коротким.

    Дефолтный 'change-me' позволяет любому злоумышленнику подделать JWT —
    это пусть и редкий, но катастрофический сценарий. Падать на старте,
    чтобы оператор не пропустил инцидент.
    """
    if settings.env == "dev":
        return
    if settings.jwt_secret == "change-me":
        raise RuntimeError(
            "JWT_SECRET is set to the default 'change-me' value in a non-dev "
            "environment. Generate a strong secret (>=32 chars) and set the "
            "JWT_SECRET env variable."
        )
    if len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET must be at least 32 characters long in a non-dev "
            "environment."
        )


_startup_logger = logging.getLogger("vkr.startup")


async def _startup_db_sync() -> None:
    """Стартовая синхронизация состояния с БД: загрузка нормативки и сброс
    зависших processing-документов в error. Выполняется с retry/backoff —
    БД и API могут стартовать одновременно (docker-compose), и нормально
    подождать пока PostgreSQL поднимется."""
    max_attempts = 5
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            async with AsyncSessionLocal() as db:
                await ensure_default_normative(db)
                await db.execute(
                    update(Document)
                    .where(Document.status == DocumentStatus.processing)
                    .values(
                        status=DocumentStatus.error,
                        progress=100,
                        processing_error=(
                            "Обработка прервана: сервер был перезапущен "
                            "во время обработки."
                        ),
                    )
                )
                await db.commit()
            return
        except Exception as exc:
            last_exc = exc
            _startup_logger.warning(
                "Database startup attempt %d/%d failed: %s",
                attempt, max_attempts, exc,
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
    raise RuntimeError(
        f"Database is unavailable after {max_attempts} attempts. "
        f"Last error: {last_exc!r}"
    )


def _run_migrations() -> None:
    """Прогоняет `alembic upgrade head` синхронно при старте.

    Alembic использует синхронный движок (psycopg2 — env.py снимает +asyncpg),
    поэтому вызывается до инициализации async-сессий. При отсутствии новых
    ревизий — no-op (несколько секунд на проверку версий и exit).
    """
    from alembic import command as alembic_command
    from alembic.config import Config

    # В docker рабочая директория — /app; локально — корень репозитория.
    # alembic.ini всегда лежит в services/api/ относительно корня.
    candidates = [
        Path("services/api/alembic.ini"),
        Path(__file__).parent.parent.parent.parent / "services" / "api" / "alembic.ini",
    ]
    ini_path = next((p for p in candidates if p.exists()), candidates[0])
    cfg = Config(str(ini_path))
    alembic_command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Стартовые проверки безопасности. Выполняются ДО любой работы с БД и
    # ДО приёма запросов: если конфигурация небезопасна, сервис должен
    # упасть быстро и с понятной диагностикой, а не работать с дырой в
    # security годами.
    _check_jwt_secret_for_env()
    check_antivirus_available()
    await asyncio.to_thread(_run_migrations)
    await _startup_db_sync()

    yield


app = FastAPI(
    title="VKR.Format API",
    version="1.0.0",
    description=(
        "REST-API сервиса автоматизированного оформления ВКР МИИГАиК.\n\n"
        "Документация группирована по тегам: **auth**, **documents**, "
        "**violations**, **normative**, **admin**. Аутентификация — JWT "
        "(Bearer); токены выдаёт `/auth/login`, отзыв — `/auth/logout`.\n\n"
        "Подробная архитектура: `docs/ARCHITECTURE.md` в репозитории."
    ),
    lifespan=lifespan,
)

# Rate-limiter регистрируется ДО других middleware, чтобы 429 отдавался
# раньше остальной обработки запроса. Лимиты per-route проставлены в
# routers/auth.py — здесь только инфраструктура.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


_unhandled_logger = logging.getLogger("vkr.unhandled")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Стек и текст исключения — в логи (там их увидит оператор). Клиенту —
    # generic message, чтобы не утекали пути, имена БД, фрагменты SQL и т.п.
    # В dev возвращаем `repr(exc)` обратно, чтобы разработчику не приходилось
    # каждый раз лазить в логи.
    _unhandled_logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    if settings.env == "dev":
        return JSONResponse(status_code=500, content={"detail": repr(exc)})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(violations.router)
app.include_router(normative.router)
app.include_router(admin.router)
