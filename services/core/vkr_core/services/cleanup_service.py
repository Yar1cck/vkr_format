"""Удаление документов, у которых истёк срок хранения (`expires_at`).

ТЗ §5.4 / Р-08: документы хранятся 90 дней, после чего должны быть удалены
вместе со всеми связанными артефактами (отчётами, превью, нарушениями).
Без этого механизма БД и storage растут линейно — для пилотной нагрузки
300 студентов × 50 МБ × 90 дней = ~13.5 ГБ только активных + столько же
просроченных.

Запускается из Celery beat ежесуточно (см. `worker/app/celery_app.py`).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.vkr_core.models import Document, ProcessingReport
from services.core.vkr_core.services.storage_service import StorageService

_logger = logging.getLogger(__name__)


async def cleanup_expired_documents(db: AsyncSession) -> int:
    """Удаляет все документы с `expires_at < now()` вместе с файлами.

    Возвращает количество удалённых документов. Удаление файлов идёт
    best-effort: ошибка для одного файла не прерывает очистку остальных
    (storage может быть временно недоступен — оставшиеся осиротевшие файлы
    подберём в следующий запуск или вручную). БД-строки удаляются в одной
    транзакции — либо все, либо ничего.
    """
    now = datetime.now(UTC)
    result = await db.execute(select(Document).where(Document.expires_at < now))
    documents = list(result.scalars().all())
    if not documents:
        return 0

    storage = StorageService()
    deleted = 0
    for doc in documents:
        report = await db.scalar(
            select(ProcessingReport).where(ProcessingReport.document_id == doc.id)
        )
        paths: list[str | None] = [
            doc.original_storage_path,
            doc.processed_storage_path,
        ]
        if report is not None:
            paths.extend([
                report.original_pdf_storage_path,
                report.processed_pdf_storage_path,
                report.report_storage_path,
                report.report_pdf_storage_path,
                report.diff_storage_path,
            ])
        for path in paths:
            if not path:
                continue
            try:
                storage.delete(path)
            except Exception:
                _logger.warning(
                    "Cleanup: failed to delete %s for document %s",
                    path, doc.id, exc_info=True,
                )

        # Document → ProcessingReport не каскадная связь, удаляем явно;
        # ProcessingReport → ViolationRecord — каскадная, нарушения уйдут с
        # отчётом.
        if report is not None:
            await db.delete(report)
        await db.delete(doc)
        deleted += 1

    await db.commit()
    _logger.info("Cleanup: deleted %d expired documents", deleted)
    return deleted
