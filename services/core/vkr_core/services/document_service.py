from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import IO
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.core.vkr_core.config.settings import get_settings
from services.core.vkr_core.models import (
    Document,
    DocumentSnapshot,
    DocumentStatus,
    ProcessingMode,
    ProcessingReport,
    User,
    UserRole,
    ViolationRecord,
)
from services.core.vkr_core.services.antivirus_service import AntivirusError, scan_file
from services.core.vkr_core.services.normative_service import get_active_normative
from services.core.vkr_core.services.storage_service import StorageService
from services.core.vkr_core.utils import (
    MAX_FILE_SIZE_BYTES,
    FileValidationError,
    validate_upload,
)

settings = get_settings()
_logger = logging.getLogger(__name__)


_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MB

_VIOLATION_CATEGORY_BY_TYPE = {
    # Структура
    "missing_structural_section": "Структура",
    "structural_order_violation": "Структура",
    "structural_heading_malformed": "Структура",
    # Заголовки
    "forbidden_heading": "Заголовки",
    "heading_rename": "Заголовки",
    "heading_number_conflict": "Заголовки",
    "heading_confirm": "Заголовки",
    "possible_missed_heading": "Заголовки",
    "heading_recovered": "Заголовки",
    # Нумерация
    "figures_renumbered": "Нумерация",
    "tables_renumbered": "Нумерация",
    "caption_renumbered": "Нумерация",
    "citation_sequence_issue": "Нумерация",
    "formula_numbering_gap": "Нумерация",
    "bibliography_numbering_gap": "Нумерация",
    "bibliography_entries_autonumbered": "Нумерация",
    # Библиография и цитирования
    "citation_without_source": "Библиография",
    "citation_separator_missing": "Библиография",
    "citation_combined": "Библиография",
    "citation_range_suspicious": "Библиография",
    "citation_sequence_issue": "Библиография",
    "source_not_cited": "Библиография",
    "bibliography_missing": "Библиография",
    "bibliography_entry_malformed": "Библиография",
    "bibliography_entries_unrecognised": "Библиография",
    "bibliography_entry_incomplete": "Библиография",
    # Рисунки и таблицы
    "figure_not_referenced": "Рисунки и таблицы",
    "figure_reference_missing": "Рисунки и таблицы",
    "table_not_referenced": "Рисунки и таблицы",
    "table_reference_missing": "Рисунки и таблицы",
    "table_mass_bold_removed": "Рисунки и таблицы",
    "long_table_split_warning": "Рисунки и таблицы",
    # Формулы
    "formula_without_explanation": "Формулы",
    "formula_number_not_right": "Формулы",
    # Приложения
    "appendix_letter_invalid": "Приложения",
    "appendix_letter_gap": "Приложения",
    "appendix_not_referenced": "Приложения",
    "appendix_order_violation": "Приложения",
    # Объём
    "volume_below_minimum": "Объём",
    "volume_above_maximum": "Объём",
    # Шрифт и абзацы
    "font_size_inconsistency": "Шрифт и абзацы",
    "paragraph_spacing": "Шрифт и абзацы",
}


def _retention_days_from_rules(rules: dict | None) -> int:
    security = (rules or {}).get("security") or {}
    value = security.get("retention_days", 90)
    return max(1, int(value))


def _save_upload_streaming(src: IO[bytes], dst_path: Path, max_bytes: int) -> None:
    """Стримит UploadFile в файл блоками. Прерывается с FileValidationError,
    если суммарный размер превышает `max_bytes`. Это позволяет отклонить
    100-MB загрузку, не материализуя весь буфер в памяти Python-процесса
    и не записывая остаток на диск.
    """
    bytes_written = 0
    with dst_path.open("wb") as dst:
        while True:
            chunk = src.read(_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                raise FileValidationError(
                    f"File too large (max {max_bytes // (1024 * 1024)}MB)"
                )
            dst.write(chunk)


class AccessDeniedError(Exception):
    pass


class NotFoundError(Exception):
    pass


async def _purge_other_user_documents(
    user_id: UUID, keep_id: UUID, db: AsyncSession
) -> None:
    """Удаляет все прежние документы пользователя (кроме keep_id), их файлы в
    хранилище и каскадно строки БД.

    Вызывается при загрузке нового документа — у студента всегда ровно один
    активный документ, прошлые версии не копятся ни в storage, ни в БД.
    Best-effort: ошибка удаления файла не мешает удалить строки.
    """
    rows = await db.execute(
        select(Document).where(
            Document.user_id == user_id, Document.id != keep_id
        )
    )
    docs = list(rows.scalars().all())
    if not docs:
        return

    storage = StorageService()
    for doc in docs:
        paths: list[str | None] = [
            doc.original_storage_path,
            doc.processed_storage_path,
        ]
        report = await db.scalar(
            select(ProcessingReport).where(ProcessingReport.document_id == doc.id)
        )
        if report is not None:
            paths += [
                report.original_pdf_storage_path,
                report.processed_pdf_storage_path,
                report.report_storage_path,
                report.report_pdf_storage_path,
            ]
        snaps = await db.execute(
            select(DocumentSnapshot).where(DocumentSnapshot.document_id == doc.id)
        )
        for s in snaps.scalars().all():
            paths += [s.processed_storage_path, s.processed_pdf_storage_path]

        for p in paths:
            if p:
                try:
                    storage.delete(p)
                except Exception:
                    # best-effort: главное — удалить строки БД. Файл подберёт
                    # cleanup-job по orphan-эвристике или ручная чистка S3.
                    _logger.debug("Не удалось удалить файл %s", p, exc_info=True)

        # report→violations каскадный; review_rounds/comments/snapshots уходят
        # по cascade у Document. Report удаляем явно (связь не каскадная).
        if report is not None:
            await db.delete(report)
        await db.delete(doc)
    await db.commit()


async def save_uploaded_document(
    user: User,
    file: UploadFile,
    mode: ProcessingMode,
    db: AsyncSession,
) -> Document:
    tmp_dir = Path(tempfile.mkdtemp(prefix="vkr-upload-"))
    try:
        local_path = tmp_dir / (file.filename or "uploaded.docx")
        # Стримим тело запроса блоками — иначе один 50-MB файл материализуется
        # в RAM процесса, а 8 параллельных загрузок суммарно дают ~400 MB
        # пиковой памяти и риск OOM. Лимит проверяется в процессе записи,
        # чтобы 200-MB злоумышленник был отклонён до записи всего файла.
        await asyncio.to_thread(
            _save_upload_streaming, file.file, local_path, MAX_FILE_SIZE_BYTES
        )

        ext = validate_upload(local_path, file.filename or "uploaded.docx")
        try:
            scan_file(local_path)
        except AntivirusError as exc:
            raise FileValidationError(str(exc)) from exc

        storage = StorageService()
        original_path = storage.save_file(local_path, "original", ext)
        normative = await get_active_normative(db)
        retention_days = _retention_days_from_rules(normative.rules_config)

        document = Document(
            user_id=user.id,
            original_filename=file.filename or local_path.name,
            original_format=ext,
            original_storage_path=original_path,
            status=DocumentStatus.pending,
            progress=0,
            normative_version_id=normative.id,
            processing_mode=mode,
            expires_at=datetime.now(UTC) + timedelta(days=retention_days),
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        # «Заменить на новую работу»: у студента ровно один активный документ —
        # при загрузке нового его прежние удаляются (только свои, только для
        # роли студента; работы других студентов и загрузки персонала не
        # трогаем).
        if user.role == UserRole.student:
            await _purge_other_user_documents(user.id, document.id, db)
        return document
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def list_documents_for_user(user: User, db: AsyncSession) -> list[Document]:
    query = (
        select(Document)
        .options(
            selectinload(Document.user),
            selectinload(Document.normative_version),
        )
        .order_by(Document.uploaded_at.desc())
    )
    if user.role == UserRole.student:
        query = query.where(Document.user_id == user.id)
    elif user.role == UserRole.supervisor:
        query = query.join(User, Document.user_id == User.id).where(User.supervisor_id == user.id)
    result = await db.execute(query)
    return list(result.scalars().all())


def _has_access(user: User, document: Document) -> bool:
    if user.role == UserRole.student:
        return document.user_id == user.id
    return user.role in {UserRole.dean, UserRole.admin}


async def get_document_or_404(document_id: UUID, user: User, db: AsyncSession) -> Document:
    document = await db.get(Document, document_id)
    if not document:
        raise NotFoundError("Document not found")
    if user.role == UserRole.supervisor:
        owner = await db.get(User, document.user_id)
        if not owner or owner.supervisor_id != user.id:
            raise AccessDeniedError("Access denied")
    elif not _has_access(user, document):
        raise AccessDeniedError("Access denied")
    return document


async def get_document_report(document_id: UUID, user: User, db: AsyncSession) -> ProcessingReport:
    document = await get_document_or_404(document_id, user, db)
    report = await db.scalar(select(ProcessingReport).where(ProcessingReport.document_id == document.id))
    if not report:
        raise NotFoundError("Report not found")
    return report


async def list_violations(document_id: UUID, user: User, db: AsyncSession) -> list[ViolationRecord]:
    report = await get_document_report(document_id, user, db)
    result = await db.execute(select(ViolationRecord).where(ViolationRecord.report_id == report.id))
    return list(result.scalars().all())


async def get_violation_or_404(
    violation_id: UUID,
    user: User,
    db: AsyncSession,
    *,
    allow_supervisor: bool = False,
) -> ViolationRecord:
    violation = await db.get(ViolationRecord, violation_id)
    if not violation:
        raise NotFoundError("Violation not found")

    report = await db.get(ProcessingReport, violation.report_id)
    if not report:
        raise NotFoundError("Report not found")
    document = await db.get(Document, report.document_id)
    if not document:
        raise NotFoundError("Document not found")
    if user.role == UserRole.supervisor and allow_supervisor:
        owner = await db.get(User, document.user_id)
        if not owner or owner.supervisor_id != user.id:
            raise AccessDeniedError("Access denied")
    elif not _has_access(user, document):
        raise AccessDeniedError("Access denied")
    return violation


async def delete_document(document_id: UUID, user: User, db: AsyncSession) -> None:
    """Удаляет документ, связанные файлы хранилища и каскадно — строки БД.

    Админ и декан имеют безусловный доступ; студент может удалять только
    свои документы. Нарушения и отчёты удаляются транзитивно — через
    SQLAlchemy cascades, настроенные на связь ProcessingReport.
    """
    document = await get_document_or_404(document_id, user, db)
    if user.role == UserRole.supervisor:
        raise AccessDeniedError("Supervisors cannot delete documents")

    storage = StorageService()
    paths: list[str | None] = [
        document.original_storage_path,
        document.processed_storage_path,
    ]
    report = await db.scalar(
        select(ProcessingReport).where(ProcessingReport.document_id == document.id)
    )
    if report is not None:
        paths.extend([
            report.original_pdf_storage_path,
            report.processed_pdf_storage_path,
            report.report_storage_path,
            report.report_pdf_storage_path,
            report.diff_storage_path,
        ])

    # Снапшоты ручных правок хранят отдельные пути на processed-docx и
    # processed-pdf. Связь Document→DocumentSnapshot каскадная (см.
    # entities.py), но cascade удаляет только строки БД — файлы в storage
    # остаются осиротевшими, если их не собрать сюда.
    snaps = await db.execute(
        select(DocumentSnapshot).where(DocumentSnapshot.document_id == document.id)
    )
    for s in snaps.scalars().all():
        paths.extend([s.processed_storage_path, s.processed_pdf_storage_path])

    for path in paths:
        if path:
            try:
                storage.delete(path)
            except Exception:
                # Очистка по best-effort — главная цель удалить строку БД.
                _logger.debug("Не удалось удалить файл %s", path, exc_info=True)

    # Связь Document→ProcessingReport не каскадная, а Report→ViolationRecord
    # — каскадная. Удаляем отчёт явно (нарушения уйдут каскадом), затем
    # удаляем сам документ.
    if report is not None:
        await db.delete(report)
    await db.delete(document)
    await db.commit()


def _violation_category(vtype: str) -> str:
    return _VIOLATION_CATEGORY_BY_TYPE.get(vtype, "Прочее")


async def get_admin_stats(db: AsyncSession, current_user: User | None = None) -> dict:
    is_supervisor = current_user is not None and current_user.role == UserRole.supervisor

    # Subquery: IDs of students belonging to this supervisor (used to scope all metrics).
    if is_supervisor:
        student_ids_q = select(User.id).where(User.supervisor_id == current_user.id)
        doc_filter = Document.user_id.in_(student_ids_q)
    else:
        doc_filter = None

    def _apply(q):
        return q.where(doc_filter) if doc_filter is not None else q

    total_documents = await db.scalar(_apply(select(func.count()).select_from(Document)))
    total_users = await db.scalar(select(func.count()).select_from(User))
    total_students = await db.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.student)
        if not is_supervisor
        else select(func.count()).select_from(User).where(
            User.role == UserRole.student,
            User.supervisor_id == current_user.id,
        )
    )
    avg_violations = await db.scalar(
        _apply(
            select(func.avg(ProcessingReport.total_violations))
            .join(Document, ProcessingReport.document_id == Document.id)
        )
    )
    total_auto_fixed = await db.scalar(
        _apply(
            select(func.sum(ProcessingReport.auto_fixed))
            .join(Document, ProcessingReport.document_id == Document.id)
        )
    )

    # Daily upload counts for the last 30 days
    today = date.today()
    window_start = today - timedelta(days=29)
    daily_result = await db.execute(
        _apply(
            select(
                func.date(Document.uploaded_at).label("day"),
                func.count().label("cnt"),
            )
            .where(Document.uploaded_at >= window_start)
        )
        .group_by(func.date(Document.uploaded_at))
        .order_by(func.date(Document.uploaded_at))
    )
    daily_map = {str(r.day): r.cnt for r in daily_result.all()}
    uploads_30d = [
        {"date": str(window_start + timedelta(days=i)), "count": daily_map.get(str(window_start + timedelta(days=i)), 0)}
        for i in range(30)
    ]

    # Violation distribution by category (scoped to supervisor's students when applicable)
    viol_q = select(ViolationRecord.type, func.count().label("cnt"))
    if is_supervisor:
        viol_q = (
            viol_q
            .join(ProcessingReport, ViolationRecord.report_id == ProcessingReport.id)
            .join(Document, ProcessingReport.document_id == Document.id)
            .where(doc_filter)
        )
    viol_q = viol_q.group_by(ViolationRecord.type)
    viol_result = await db.execute(viol_q)
    cat_counts: dict[str, int] = {}
    for vtype, cnt in viol_result.all():
        cat = _violation_category(vtype)
        cat_counts[cat] = cat_counts.get(cat, 0) + cnt
    total_viol = sum(cat_counts.values()) or 1
    violations_by_category = [
        {"name": k, "count": v, "percent": round(v * 100 / total_viol)}
        for k, v in sorted(cat_counts.items(), key=lambda x: -x[1])
    ]

    # Recent uploads (last 10)
    recent_result = await db.execute(
        _apply(
            select(Document, User, ProcessingReport)
            .join(User, Document.user_id == User.id)
            .outerjoin(ProcessingReport, ProcessingReport.document_id == Document.id)
        )
        .order_by(Document.uploaded_at.desc())
        .limit(10)
    )
    recent_uploads = [
        {
            "id": str(doc.id),
            "filename": doc.original_filename,
            "owner_full_name": user.full_name,
            "uploaded_at": doc.uploaded_at.isoformat(),
            "violations": report.total_violations if report else None,
            "status": doc.status.value,
        }
        for doc, user, report in recent_result.all()
    ]

    return {
        "total_documents": int(total_documents or 0),
        "total_users": int(total_users or 0),
        "total_students": int(total_students or 0),
        "avg_violations": float(avg_violations or 0),
        "total_auto_fixed": int(total_auto_fixed or 0),
        "uploads_30d": uploads_30d,
        "violations_by_category": violations_by_category,
        "recent_uploads": recent_uploads,
    }
