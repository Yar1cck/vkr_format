from __future__ import annotations

import asyncio
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from services.core.vkr_core.db.session import AsyncSessionLocal
from services.core.vkr_core.services.cleanup_service import cleanup_expired_documents
from services.core.vkr_core.services.processing_service import process_document_sync
from services.worker.app.celery_app import celery_app


# Исключаем SoftTimeLimitExceeded из autoretry: если задача упала по таймауту,
# повторять её 3 раза подряд — это 15 минут впустую тратить воркер на ту же
# зависшую задачу. Документ всё равно перейдёт в error через
# process_document_async и пользователь увидит явное сообщение.
@celery_app.task(
    name="vkr.process_document",
    autoretry_for=(Exception,),
    dont_autoretry_for=(SoftTimeLimitExceeded,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
)
def process_document_task(document_id: str) -> None:
    process_document_sync(UUID(document_id), AsyncSessionLocal)


@celery_app.task(name="vkr.cleanup_expired_documents")
def cleanup_expired_documents_task() -> int:
    """Запускается из Celery beat ежесуточно. Удаляет документы со сгоревшим
    `expires_at`. Не имеет retry — если упало, следующий запуск через сутки
    подберёт оставшихся; нет смысла гонять одну и ту же выборку 3 раза."""
    async def _runner() -> int:
        async with AsyncSessionLocal() as db:
            return await cleanup_expired_documents(db)
    return asyncio.run(_runner())
