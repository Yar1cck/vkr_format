from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from docx import Document as WordDocument
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from services.api.app.dependencies import get_current_user
from services.api.app.queue import enqueue_document_processing
from services.core.vkr_core.config.settings import get_settings
from services.core.vkr_core.db.session import AsyncSessionLocal, get_db
from services.core.vkr_core.engine.formatter import overwrite_paragraph_text
from services.core.vkr_core.models import (
    ApprovalStatus,
    Document,
    DocumentComment,
    DocumentStatus,
    ProcessingMode,
    ProcessingReport,
    ReviewRound,
    User,
    UserRole,
    ViolationRecord,
    ViolationStatus,
)
from services.core.vkr_core.schemas import (
    ApprovalDecisionRequest,
    DocumentCommentIn,
    DocumentCommentOut,
    DocumentOut,
    DocumentRollbackResponse,
    DocumentSnapshotOut,
    DocumentStatusOut,
    ProcessingReportOut,
    ReviewRoundOut,
    UploadResponse,
)
from services.core.vkr_core.services import (
    AccessDeniedError,
    NotFoundError,
    delete_document,
    get_document_or_404,
    get_document_report,
    list_documents_for_user,
    list_snapshots,
    rollback_to_snapshot,
    save_uploaded_document,
)
from services.core.vkr_core.services.processing_service import process_document_async
from services.core.vkr_core.services.snapshot_service import create_snapshot
from services.core.vkr_core.services.storage_service import StorageService
from services.core.vkr_core.utils import FileValidationError

settings = get_settings()
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
_logger = logging.getLogger(__name__)


def _cleanup_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass



def _build_download_response(storage: StorageService, storage_path: str, filename: str) -> FileResponse:
    if settings.use_s3:
        temp_path = storage.load_to_local_path(storage_path)
        return FileResponse(
            path=temp_path,
            filename=filename,
            background=BackgroundTask(_cleanup_temp_file, temp_path),
        )
    return FileResponse(path=storage_path, filename=filename)


def _processed_filename(original_filename: str) -> str:
    stem = Path(original_filename).stem or "document"
    return f"processed_{stem}.docx"


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    mode: ProcessingMode = Form(default=ProcessingMode.full),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    try:
        document = await save_uploaded_document(current_user, file, mode, db)
    except FileValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if settings.sync_processing:
        await process_document_async(document.id, db)
    else:
        enqueue_document_processing(str(document.id))

    return UploadResponse(
        document=DocumentOut.model_validate(document),
        message="Файл загружен и поставлен в обработку",
    )


@router.get("/", response_model=list[DocumentOut])
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    docs = await list_documents_for_user(current_user, db)
    include_owner = current_user.role in {UserRole.admin, UserRole.dean, UserRole.supervisor}

    doc_ids = [d.id for d in docs]
    unresolved_counts: dict[UUID, int] = {}
    last_comment_at_map: dict[UUID, object] = {}

    if doc_ids:
        # Bulk: manual_required нарушений per document
        rows = await db.execute(
            sa_select(
                ProcessingReport.document_id,
                sa_func.count(ViolationRecord.id).label("cnt"),
            )
            .join(ViolationRecord, ViolationRecord.report_id == ProcessingReport.id)
            .where(
                ProcessingReport.document_id.in_(doc_ids),
                ViolationRecord.status == ViolationStatus.manual_required,
            )
            .group_by(ProcessingReport.document_id)
        )
        for document_id, cnt in rows:
            unresolved_counts[document_id] = cnt

        # Bulk: время последнего комментария per document
        comment_rows = await db.execute(
            sa_select(
                DocumentComment.document_id,
                sa_func.max(DocumentComment.created_at).label("last_at"),
            )
            .where(DocumentComment.document_id.in_(doc_ids))
            .group_by(DocumentComment.document_id)
        )
        for document_id, last_at in comment_rows:
            last_comment_at_map[document_id] = last_at

    output: list[DocumentOut] = []
    for doc in docs:
        payload = DocumentOut.model_validate(doc)
        updates: dict = {}
        if doc.normative_version is not None:
            updates["normative_version_name"] = doc.normative_version.name
        if include_owner and doc.user is not None:
            updates["owner_full_name"] = doc.user.full_name
            updates["owner_email"] = doc.user.email
        updates["has_unresolved_violations"] = unresolved_counts.get(doc.id, 0) > 0
        updates["last_comment_at"] = last_comment_at_map.get(doc.id)
        payload = payload.model_copy(update=updates)
        output.append(payload)
    return output


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await delete_document(document_id, current_user, db)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AccessDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    try:
        doc = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    # Подгружаем имя нормативной версии, чтобы клиенту не делать
    # отдельный запрос ради подписи поля "Норм. база".
    await db.refresh(doc, attribute_names=["normative_version"])
    payload = DocumentOut.model_validate(doc)
    if doc.normative_version is not None:
        payload = payload.model_copy(update={"normative_version_name": doc.normative_version.name})
    return payload


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
async def get_document_status(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentStatusOut:
    try:
        doc = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return DocumentStatusOut(id=doc.id, status=doc.status, progress=doc.progress, processing_error=doc.processing_error)


@router.get("/{document_id}/download/original")
async def download_original(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    storage = StorageService()
    return _build_download_response(storage, doc.original_storage_path, doc.original_filename)


@router.get("/{document_id}/download/processed")
async def download_processed(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        doc = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if not doc.processed_storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processed file not available yet")

    storage = StorageService()
    return _build_download_response(storage, doc.processed_storage_path, _processed_filename(doc.original_filename))


@router.get("/{document_id}/download/processed-pdf")
async def download_processed_pdf(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """PDF исправленного документа (LibreOffice-рендер, включает все ручные правки)."""
    try:
        doc = await get_document_or_404(document_id, current_user, db)
        report = await get_document_report(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if not report.processed_pdf_storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF не сгенерирован — документ ещё обрабатывается или LibreOffice недоступен",
        )

    filename = _processed_filename(doc.original_filename).replace(".docx", ".pdf")
    storage = StorageService()
    response = _build_download_response(storage, report.processed_pdf_storage_path, filename)
    response.media_type = "application/pdf"
    return response


@router.get("/{document_id}/preview/{kind}")
async def download_preview_pdf(
    document_id: UUID,
    kind: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if kind not in {"original", "processed"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown preview kind")

    try:
        report = await get_document_report(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    path = report.original_pdf_storage_path if kind == "original" else report.processed_pdf_storage_path
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview PDF not available")

    storage = StorageService()
    response = _build_download_response(storage, path, f"{kind}_{document_id}.pdf")
    response.media_type = "application/pdf"
    # После ручной правки нарушения preview-PDF переписывается, но URL не
    # меняется. Без явного no-cache браузер/прокси могут отдать старый
    # кешированный PDF; cache-busting query string на фронте — first line
    # of defence, no-cache header — second.
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@router.get("/{document_id}/report")
async def download_report(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        report = await get_document_report(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    path = report.report_pdf_storage_path or report.report_storage_path
    if not path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отчёт не найден")

    storage = StorageService()

    # Берём имя исходного файла, чтобы отчёт назывался понятно
    try:
        doc = await get_document_or_404(document_id, current_user, db)
        stem = Path(doc.original_filename).stem if doc.original_filename else "ВКР"
    except Exception:
        stem = "ВКР"
    report_filename = f"Отчёт — {stem}.pdf"

    response = _build_download_response(storage, path, report_filename)
    response.media_type = "application/pdf"
    return response


@router.get("/{document_id}/report/meta", response_model=ProcessingReportOut)
async def get_report_meta(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProcessingReportOut:
    try:
        report = await get_document_report(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return ProcessingReportOut.model_validate(report)


# ── S-18: Workflow приёмки руководителем ────────────────────────────────────


@router.post("/{document_id}/submit-for-review", response_model=DocumentOut)
async def submit_for_review(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    """Студент отправляет свой документ на проверку руководителю.

    Доступно только владельцу документа и только если документ обработан
    (`status=done`). Сбрасывает предыдущие комментарии руководителя — это
    новая итерация проверки.
    """
    try:
        document = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="На проверку может отправлять только владелец документа",
        )
    if document.status != DocumentStatus.done:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Документ ещё не обработан — сначала дождитесь окончания обработки",
        )
    if current_user.supervisor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Выберите научного руководителя в настройках перед отправкой на проверку",
        )
    document.approval_status = ApprovalStatus.pending_review
    document.approval_comment = None
    document.approval_decided_at = None
    document.approval_decided_by = None
    await db.commit()
    await db.refresh(document)
    return DocumentOut.model_validate(document)


@router.post("/{document_id}/approve", response_model=DocumentOut)
async def approve_document(
    document_id: UUID,
    body: ApprovalDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    """Руководитель/декан принимает документ.

    Принять можно только документ в статусе `pending_review` (это защита от
    случайного «принятия» документа, который студент ещё не отправил —
    или того, что уже принят: повторное принятие было бы шумом в audit-логе).
    """
    if current_user.role not in {UserRole.supervisor, UserRole.dean, UserRole.admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только руководитель, декан или админ может принимать документы",
        )
    try:
        document = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if document.approval_status != ApprovalStatus.pending_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Принять можно только документ, отправленный на проверку",
        )
    document.approval_status = ApprovalStatus.approved
    document.approval_comment = (body.comment or "").strip() or None
    document.approval_decided_at = datetime.now(UTC)
    document.approval_decided_by = current_user.id
    db.add(ReviewRound(
        document_id=document.id,
        decided_by=current_user.id,
        decided_by_name=current_user.full_name,
        decision="approved",
        comment=document.approval_comment,
        decided_at=document.approval_decided_at,
    ))
    await db.commit()
    await db.refresh(document)
    return DocumentOut.model_validate(document)


@router.post("/{document_id}/reject", response_model=DocumentOut)
async def reject_document(
    document_id: UUID,
    body: ApprovalDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    """Руководитель/декан отклоняет документ. Комментарий обязателен —
    студент должен понимать причину отказа."""
    if current_user.role not in {UserRole.supervisor, UserRole.dean, UserRole.admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только руководитель, декан или админ может отклонять документы",
        )
    comment = (body.comment or "").strip()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите причину отклонения",
        )
    try:
        document = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if document.approval_status != ApprovalStatus.pending_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Отклонить можно только документ, отправленный на проверку",
        )
    document.approval_status = ApprovalStatus.rejected
    document.approval_comment = comment
    document.approval_decided_at = datetime.now(UTC)
    document.approval_decided_by = current_user.id
    db.add(ReviewRound(
        document_id=document.id,
        decided_by=current_user.id,
        decided_by_name=current_user.full_name,
        decision="rejected",
        comment=comment,
        decided_at=document.approval_decided_at,
    ))
    await db.commit()
    await db.refresh(document)
    return DocumentOut.model_validate(document)


# ── Коммуникация: история раундов и тред комментариев ───────────────────────


@router.get("/{document_id}/review-history", response_model=list[ReviewRoundOut])
async def get_review_history(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewRoundOut]:
    try:
        await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    rows = await db.scalars(
        sa_select(ReviewRound)
        .where(ReviewRound.document_id == document_id)
        .order_by(ReviewRound.decided_at)
    )
    return [ReviewRoundOut.model_validate(r) for r in rows.all()]


@router.get("/{document_id}/comments", response_model=list[DocumentCommentOut])
async def get_comments(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentCommentOut]:
    try:
        await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    rows = await db.scalars(
        sa_select(DocumentComment)
        .where(DocumentComment.document_id == document_id)
        .order_by(DocumentComment.created_at)
    )
    return [DocumentCommentOut.model_validate(c) for c in rows.all()]


@router.post("/{document_id}/comments", response_model=DocumentCommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    document_id: UUID,
    body: DocumentCommentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentCommentOut:
    try:
        await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Комментарий не может быть пустым")

    comment = DocumentComment(
        document_id=document_id,
        author_id=current_user.id,
        author_name=current_user.full_name,
        author_role=current_user.role.value,
        body=text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return DocumentCommentOut.model_validate(comment)


# ── История правок (undo/rollback) ──────────────────────────────────────────


@router.get("/{document_id}/snapshots", response_model=list[DocumentSnapshotOut])
async def get_document_snapshots(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentSnapshotOut]:
    """Возвращает историю ручных правок документа (новые первыми).

    Каждый элемент — состояние ДО применения соответствующей правки.
    Используется для отображения timeline-панели «История изменений»
    и кнопки «Отменить последнее действие».
    """
    try:
        await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    snapshots = await list_snapshots(document_id, db)
    return [DocumentSnapshotOut.model_validate(s) for s in snapshots]


@router.post(
    "/{document_id}/snapshots/{snapshot_id}/rollback",
    response_model=DocumentRollbackResponse,
)
async def rollback_document_to_snapshot(
    document_id: UUID,
    snapshot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentRollbackResponse:
    """Откатывает документ к выбранному снимку (undo до конкретной правки).

    Восстанавливает обработанный .docx, PDF-превью и полный список нарушений
    в том состоянии, каким они были ДО правки, породившей этот снимок.
    Все снимки «новее» выбранного удаляются (линейная история: после отката
    redo недоступен — новая правка начнёт историю заново).

    Доступно только владельцу документа (студенту). Руководитель может
    смотреть историю, но менять файл не вправе.
    """
    try:
        document = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if document.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Откатить изменения может только владелец документа",
        )

    if document.status != DocumentStatus.done:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Откат возможен только для полностью обработанного документа",
        )

    # Захватываем row-lock, как и при любой мутирующей операции.
    await db.execute(
        sa_select(document.__class__.id)
        .where(document.__class__.id == document_id)
        .with_for_update()
    )
    await db.refresh(document)

    report = await db.scalar(
        sa_select(ProcessingReport).where(ProcessingReport.document_id == document_id)
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Отчёт обработки не найден",
        )

    try:
        snapshot = await rollback_to_snapshot(document, report, snapshot_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    await db.commit()

    return DocumentRollbackResponse(
        snapshot_id=snapshot.id,
        snapshot_index=snapshot.snapshot_index,
        action_description=snapshot.action_description,
    )


# ── Правка текста абзаца ──────────────────────────────────────────────────────

class ParagraphPatchRequest(BaseModel):
    text: str


def _do_patch_paragraph_sync(local_path: Path, paragraph_index: int, new_text: str) -> None:
    doc = WordDocument(str(local_path))
    paragraphs = doc.paragraphs
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        raise IndexError(
            f"paragraph_index {paragraph_index} вне диапазона (0–{len(paragraphs) - 1})"
        )
    overwrite_paragraph_text(paragraphs[paragraph_index], new_text)
    doc.save(str(local_path))


async def _regen_pdf_after_patch(report_id: UUID, storage_path: str) -> None:
    storage = StorageService()
    local = storage.load_to_local_path(storage_path)
    try:
        from services.core.vkr_core.engine.preview import convert_docx_to_pdf
        pdf_local = await asyncio.to_thread(convert_docx_to_pdf, local)
        pdf_storage = storage.save_file(pdf_local, "previews", ".pdf")
        shutil.rmtree(pdf_local.parent, ignore_errors=True)
        async with AsyncSessionLocal() as s:
            await s.execute(
                sa_update(ProcessingReport)
                .where(ProcessingReport.id == report_id)
                .values(processed_pdf_storage_path=pdf_storage)
            )
            await s.commit()
    except Exception:
        _logger.warning("PDF regen failed after paragraph patch", exc_info=True)
    finally:
        local.unlink(missing_ok=True)


@router.patch("/{document_id}/paragraphs/{paragraph_index}", summary="Исправить текст абзаца")
async def patch_paragraph_text(
    document_id: UUID,
    paragraph_index: int,
    body: ParagraphPatchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        document = await get_document_or_404(document_id, current_user, db)
    except (NotFoundError, AccessDeniedError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if document.status != DocumentStatus.done:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Документ ещё не обработан",
        )

    if not document.processed_storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обработанный файл не найден",
        )

    # Row-lock: сериализует параллельные правки того же документа.
    await db.execute(
        sa_select(Document.id)
        .where(Document.id == document_id)
        .with_for_update()
    )
    await db.refresh(document)

    if not document.processed_storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Обработанный файл не найден",
        )

    report = await db.scalar(
        sa_select(ProcessingReport).where(ProcessingReport.document_id == document_id)
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отчёт не найден")

    violations = list(await db.scalars(
        sa_select(ViolationRecord).where(ViolationRecord.report_id == report.id)
    ))
    await create_snapshot(
        document, report, violations,
        "patch_paragraph",
        f"Правка текста абзаца {paragraph_index}",
        db,
    )

    storage = StorageService()
    local_path = storage.load_to_local_path(document.processed_storage_path)

    try:
        await asyncio.to_thread(
            _do_patch_paragraph_sync, local_path, paragraph_index, body.text.strip()
        )
    except IndexError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    new_storage = storage.save_file(local_path, "processed", ".docx")
    await db.execute(
        sa_update(Document)
        .where(Document.id == document_id)
        .values(processed_storage_path=new_storage)
    )
    await db.commit()

    background_tasks.add_task(_regen_pdf_after_patch, report.id, new_storage)
    local_path.unlink(missing_ok=True)

    return {"ok": True}
