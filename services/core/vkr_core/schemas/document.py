from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from services.core.vkr_core.models.enums import (
    ApprovalStatus,
    DocumentStatus,
    ProcessingMode,
)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    uploaded_at: datetime
    original_filename: str
    original_format: str
    status: DocumentStatus
    progress: int
    processing_mode: ProcessingMode
    processing_error: str | None = None
    # Отображаемое имя нормативной базы, по которой обрабатывался документ.
    # Заполняется из Document.normative_version.name, чтобы клиент не делал
    # отдельный запрос для подписи колонки.
    normative_version_name: str | None = None
    # Заполняется для админ/декан-листинга, чтобы управляющий UI показывал
    # владельца без второго запроса. Null для студенческих выборок.
    owner_full_name: str | None = None
    owner_email: str | None = None
    # Workflow приёмки (S-18). NULL — студент ещё не отправил на проверку.
    approval_status: ApprovalStatus | None = None
    approval_comment: str | None = None
    approval_decided_at: datetime | None = None
    # True, если по документу остались нарушения со статусом manual_required.
    # Вычисляется отдельным запросом в routers/documents.py.
    has_unresolved_violations: bool = False
    # Время последнего комментария в треде. Используется клиентом для
    # определения непрочитанных сообщений (сравнивается с localStorage).
    last_comment_at: datetime | None = None


class ApprovalDecisionRequest(BaseModel):
    # Комментарий обязателен при rejected (так логичнее — отказ без причины
    # бесит студента), для approved опционален.
    comment: str | None = None


class ReviewRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decided_by: UUID
    decided_by_name: str
    decision: str  # "approved" | "rejected"
    comment: str | None = None
    decided_at: datetime


class DocumentCommentIn(BaseModel):
    body: str


class DocumentCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID
    author_name: str
    author_role: str
    body: str
    created_at: datetime


class DocumentSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    snapshot_index: int
    action_type: str
    action_description: str
    created_at: datetime


class DocumentRollbackResponse(BaseModel):
    snapshot_id: UUID
    snapshot_index: int
    action_description: str


class DocumentStatusOut(BaseModel):
    id: UUID
    status: DocumentStatus
    progress: int
    processing_error: str | None = None


class UploadResponse(BaseModel):
    document: DocumentOut
    message: str
