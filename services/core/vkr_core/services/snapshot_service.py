"""Сервис снимков состояния документа для поддержки отмены ручных правок.

Каждый снимок фиксирует состояние ДО применения мутирующей операции, поэтому
откат к снимку восстанавливает именно то, что было до этой правки.

Принцип хранения файлов: поскольку каждая ручная правка создаёт новый файл
с новым UUID-именем в хранилище, старые пути остаются валидны — копировать
файлы не нужно. Снимок хранит только ссылки на уже существующие пути.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.vkr_core.models.entities import (
    Document,
    DocumentSnapshot,
    ProcessingReport,
    ViolationRecord,
)
from services.core.vkr_core.models.enums import ViolationStatus

_MAX_SNAPSHOTS_PER_DOC = 30


async def create_snapshot(
    document: Document,
    report: ProcessingReport,
    violations: list[ViolationRecord],
    action_type: str,
    action_description: str,
    db: AsyncSession,
) -> DocumentSnapshot:
    """Создаёт снимок текущего состояния документа перед мутирующей правкой.

    Вызывать ПОСЛЕ захвата row-lock'а на документ и ПЕРЕД записью изменений,
    чтобы снимок отражал состояние «до правки».
    """
    if not document.processed_storage_path:
        raise ValueError("Документ не имеет processed_storage_path — снимок невозможен")

    max_idx = await db.scalar(
        sa_select(func.max(DocumentSnapshot.snapshot_index)).where(
            DocumentSnapshot.document_id == document.id
        )
    )
    next_index = (max_idx or 0) + 1

    violation_data = [
        {
            "id": str(v.id),
            "report_id": str(v.report_id),
            "type": v.type,
            "rule_reference": v.rule_reference,
            "severity": v.severity,
            "description": v.description,
            "paragraph_index": v.paragraph_index,
            "section_title": v.section_title,
            "original_text": v.original_text,
            "fixed_text": v.fixed_text,
            "fix_options": v.fix_options,
            "caused_by_index": v.caused_by_index,
            "detector_signals": v.detector_signals,
            "status": v.status.value,
            "supervisor_comment": v.supervisor_comment,
        }
        for v in violations
    ]

    snapshot = DocumentSnapshot(
        document_id=document.id,
        snapshot_index=next_index,
        action_type=action_type,
        action_description=action_description,
        processed_storage_path=document.processed_storage_path,
        processed_pdf_storage_path=report.processed_pdf_storage_path,
        violation_snapshot=violation_data,
    )
    db.add(snapshot)

    # Удаляем самые старые снимки при превышении лимита.
    existing_count = await db.scalar(
        sa_select(func.count()).select_from(DocumentSnapshot).where(
            DocumentSnapshot.document_id == document.id
        )
    ) or 0
    if existing_count >= _MAX_SNAPSHOTS_PER_DOC:
        overflow = existing_count - _MAX_SNAPSHOTS_PER_DOC + 1
        oldest_ids = list(await db.scalars(
            sa_select(DocumentSnapshot.id)
            .where(DocumentSnapshot.document_id == document.id)
            .order_by(DocumentSnapshot.snapshot_index)
            .limit(overflow)
        ))
        if oldest_ids:
            await db.execute(
                sa_delete(DocumentSnapshot).where(DocumentSnapshot.id.in_(oldest_ids))
            )

    await db.flush()
    return snapshot


async def list_snapshots(document_id: UUID, db: AsyncSession) -> list[DocumentSnapshot]:
    """Возвращает историю снимков: новые первыми (убывающий snapshot_index)."""
    result = await db.scalars(
        sa_select(DocumentSnapshot)
        .where(DocumentSnapshot.document_id == document_id)
        .order_by(DocumentSnapshot.snapshot_index.desc())
    )
    return list(result)


async def rollback_to_snapshot(
    document: Document,
    report: ProcessingReport,
    snapshot_id: UUID,
    db: AsyncSession,
) -> DocumentSnapshot:
    """Откатывает документ к указанному снимку.

    Восстанавливает processed_storage_path, processed_pdf_storage_path и
    полный набор ViolationRecord. Удаляет снимки после восстанавливаемого
    (линейная история — после отката нельзя «повторить» отменённое; при
    следующей ручной правке история пишется заново).
    """
    snapshot = await db.get(DocumentSnapshot, snapshot_id)
    if snapshot is None or snapshot.document_id != document.id:
        raise ValueError("Снимок не найден или не принадлежит данному документу")

    # Восстанавливаем файловые указатели.
    document.processed_storage_path = snapshot.processed_storage_path
    report.processed_pdf_storage_path = snapshot.processed_pdf_storage_path

    # Заменяем все нарушения содержимым снимка.
    await db.execute(
        sa_delete(ViolationRecord).where(ViolationRecord.report_id == report.id)
    )
    await db.flush()

    for v in snapshot.violation_snapshot:
        db.add(
            ViolationRecord(
                report_id=report.id,
                type=v["type"],
                rule_reference=v["rule_reference"],
                severity=v["severity"],
                description=v["description"],
                paragraph_index=v.get("paragraph_index"),
                section_title=v.get("section_title"),
                original_text=v.get("original_text"),
                fixed_text=v.get("fixed_text"),
                fix_options=v.get("fix_options"),
                caused_by_index=v.get("caused_by_index"),
                detector_signals=v.get("detector_signals"),
                status=ViolationStatus(v["status"]),
                supervisor_comment=v.get("supervisor_comment"),
            )
        )

    # Пересчитываем счётчики отчёта.
    data = snapshot.violation_snapshot
    report.total_violations = len(data)
    report.auto_fixed = sum(1 for v in data if v["status"] == "auto_fixed")
    report.manual_required = sum(1 for v in data if v["status"] == "manual_required")

    # Удаляем всю «будущую» историю (снимки с индексом > восстанавливаемого).
    await db.execute(
        sa_delete(DocumentSnapshot).where(
            DocumentSnapshot.document_id == document.id,
            DocumentSnapshot.snapshot_index > snapshot.snapshot_index,
        )
    )

    await db.flush()
    return snapshot
