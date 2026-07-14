from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from uuid import UUID

from docx import Document as WordDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.vkr_core.config.settings import get_settings
from services.core.vkr_core.engine import process_document
from services.core.vkr_core.engine.preview import convert_docx_to_pdf, convert_multiple_docx_to_pdf
from services.core.vkr_core.models import (
    Document,
    DocumentStatus,
    NormativeVersion,
    ProcessingMode,
    ProcessingReport,
    ViolationRecord,
)
from services.core.vkr_core.services.report_service import (
    generate_diff_text,
    generate_report_pdf,
)
from services.core.vkr_core.services.storage_service import StorageService

settings = get_settings()
_logger = logging.getLogger(__name__)


def _extract_text_from_docx(path: Path) -> str:
    doc = WordDocument(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _is_storage_tmp_file(path: Path) -> bool:
    """True, если путь — временный файл, скачанный StorageService из S3
    (`<local_storage_path>/tmp/<uuid>`). Такой файл нужно удалить, но НЕ его
    родительский каталог — `tmp/` общий для всех параллельных загрузок.

    В local-режиме StorageService возвращает реальный файл из ./storage/...
    — его удалять нельзя, это постоянное хранилище."""
    try:
        local_root = Path(settings.local_storage_path).resolve()
        tmp_root = (local_root / "tmp").resolve()
        return tmp_root in path.resolve().parents
    except Exception:
        return False


async def process_document_async(document_id: UUID, db: AsyncSession) -> None:
    storage = StorageService()
    document = await db.get(Document, document_id)
    if not document:
        return

    # Все временные пути, созданные в ходе обработки. Чистятся в finally,
    # чтобы /tmp и storage/tmp не копили десятки МБ на каждый документ
    # (pipeline working dir + report docx + report pdf + 2 preview PDF +
    # скачанные из S3 файлы).
    tmp_dirs: list[Path] = []   # mkdtemp-каталоги — rmtree
    tmp_files: list[Path] = []  # отдельные файлы из storage/tmp — unlink

    try:
        document.status = DocumentStatus.processing
        document.progress = 10
        document.processing_error = None
        await db.commit()

        normative = await db.get(NormativeVersion, document.normative_version_id)
        if not normative:
            raise RuntimeError("Normative version not found")

        original_local = storage.load_to_local_path(document.original_storage_path)
        if _is_storage_tmp_file(original_local):
            tmp_files.append(original_local)

        pipeline_result = process_document(
            source_path=original_local,
            rules=normative.rules_config,
            check_only=document.processing_mode == ProcessingMode.check_only,
        )
        tmp_dirs.append(pipeline_result.processed_docx_path.parent)

        document.progress = 75
        await db.commit()

        if document.processing_mode == ProcessingMode.full:
            processed_storage_path = storage.save_file(
                pipeline_result.processed_docx_path, "processed", ".docx"
            )
            document.processed_storage_path = processed_storage_path

        original_text_local = storage.load_to_local_path(document.original_storage_path)
        if _is_storage_tmp_file(original_text_local):
            tmp_files.append(original_text_local)
        original_text = _extract_text_from_docx(original_text_local)
        processed_text = _extract_text_from_docx(pipeline_result.processed_docx_path)

        report_pdf = generate_report_pdf(
            pipeline_result.violations,
            pipeline_result.toc_warning,
            pipeline_result.volume_pages,
        )
        tmp_dirs.append(report_pdf.parent)
        diff_text = generate_diff_text(original_text, processed_text)

        report_pdf_path = storage.save_file(report_pdf, "reports", ".pdf")
        diff_path = storage.save_bytes(diff_text.encode("utf-8"), "reports", ".diff")

        document.progress = 85
        await db.commit()

        # Рендерим PDF-превью под Word одним запуском LibreOffice для обоих файлов.
        # Ошибка не фатальна — фронтенд покажет "превью недоступно".
        original_pdf_storage_path: str | None = None
        processed_pdf_storage_path: str | None = None
        try:
            if document.original_format == ".docx":
                original_docx_for_preview = storage.load_to_local_path(
                    document.original_storage_path
                )
                if _is_storage_tmp_file(original_docx_for_preview):
                    tmp_files.append(original_docx_for_preview)
            else:
                original_docx_for_preview = pipeline_result.processed_docx_path

            need_processed = document.processing_mode == ProcessingMode.full
            processed_docx = pipeline_result.processed_docx_path

            # Если оба файла разные — конвертируем одним запуском LO (экономим 3–5 с).
            if need_processed and original_docx_for_preview != processed_docx:
                pdfs = convert_multiple_docx_to_pdf(
                    [original_docx_for_preview, processed_docx]
                )
                orig_pdf, proc_pdf = pdfs[0], pdfs[1]
                if orig_pdf:
                    tmp_dirs.append(orig_pdf.parent)
                    original_pdf_storage_path = storage.save_file(orig_pdf, "previews", ".pdf")
                if proc_pdf:
                    processed_pdf_storage_path = storage.save_file(proc_pdf, "previews", ".pdf")
            else:
                orig_pdf = convert_docx_to_pdf(original_docx_for_preview)
                tmp_dirs.append(orig_pdf.parent)
                original_pdf_storage_path = storage.save_file(orig_pdf, "previews", ".pdf")
                if need_processed:
                    proc_pdf = convert_docx_to_pdf(processed_docx)
                    tmp_dirs.append(proc_pdf.parent)
                    processed_pdf_storage_path = storage.save_file(proc_pdf, "previews", ".pdf")
        except Exception:
            _logger.warning(
                "Failed to render PDF preview(s) for document %s",
                document.id,
                exc_info=True,
            )

        document.progress = 92
        await db.commit()

        existing_report = await db.scalar(
            select(ProcessingReport).where(ProcessingReport.document_id == document.id)
        )
        if existing_report:
            await db.delete(existing_report)
            await db.flush()

        auto_fixed = sum(
            1 for v in pipeline_result.violations if v.status.value == "auto_fixed"
        )
        manual_required = sum(
            1 for v in pipeline_result.violations if v.status.value == "manual_required"
        )

        report = ProcessingReport(
            document_id=document.id,
            total_violations=len(pipeline_result.violations),
            auto_fixed=auto_fixed,
            manual_required=manual_required,
            report_storage_path=report_pdf_path,      # поле переиспользуется под PDF
            report_pdf_storage_path=report_pdf_path,
            diff_storage_path=diff_path,
            volume_pages=pipeline_result.volume_pages,
            original_pdf_storage_path=original_pdf_storage_path,
            processed_pdf_storage_path=processed_pdf_storage_path,
        )
        db.add(report)
        await db.flush()

        for violation in pipeline_result.violations:
            db.add(
                ViolationRecord(
                    report_id=report.id,
                    type=violation.type,
                    rule_reference=violation.rule_reference,
                    severity=violation.severity,
                    description=violation.description,
                    paragraph_index=violation.paragraph_index,
                    section_title=violation.section_title,
                    original_text=violation.original_text,
                    fixed_text=violation.fixed_text,
                    fix_options=violation.fix_options,
                    caused_by_index=violation.caused_by_index,
                    detector_signals=violation.detector_signals,
                    status=violation.status,
                )
            )

        document.status = DocumentStatus.done
        document.progress = 100
        await db.commit()
    except Exception as exc:
        document.status = DocumentStatus.error
        document.progress = 100
        document.processing_error = str(exc)
        await db.commit()
        raise
    finally:
        # Удаляем все временные пути, накопленные в ходе обработки. Файлы и
        # каталоги обрабатываем отдельно: storage/tmp/<uuid> — файл в общем
        # каталоге (parent трогать нельзя), а pipeline/report/preview каталоги
        # созданы через mkdtemp и удаляются целиком.
        seen_files: set[Path] = set()
        for path in tmp_files:
            if path in seen_files:
                continue
            seen_files.add(path)
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
        seen_dirs: set[Path] = set()
        for path in tmp_dirs:
            if path in seen_dirs:
                continue
            seen_dirs.add(path)
            shutil.rmtree(path, ignore_errors=True)


def process_document_sync(document_id: UUID, session_factory) -> None:
    async def _runner() -> None:
        async with session_factory() as db:
            await process_document_async(document_id, db)

    asyncio.run(_runner())
