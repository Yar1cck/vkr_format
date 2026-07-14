from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.core.vkr_core.db.base import Base
from services.core.vkr_core.models.enums import (
    ApprovalStatus,
    DocumentStatus,
    ProcessingMode,
    UserRole,
    ViolationStatus,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.student, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    # Не FK — при удалении руководителя студенты не теряют привязку,
    # просто показывается UUID без имени.
    supervisor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    documents: Mapped[list[Document]] = relationship(back_populates="user")


class NormativeVersion(Base):
    __tablename__ = "normative_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    rules_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    documents: Mapped[list[Document]] = relationship(back_populates="normative_version")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_format: Mapped[str] = mapped_column(String(16), nullable=False)
    original_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    processed_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), default=DocumentStatus.pending, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normative_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normative_versions.id"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC) + timedelta(days=90),
        nullable=False,
    )
    processing_mode: Mapped[ProcessingMode] = mapped_column(
        Enum(ProcessingMode), default=ProcessingMode.full, nullable=False
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # S-18 — workflow приёмки документа руководителем/деканом.
    # NULL означает «студент ещё не отправил на проверку». Допустимые значения:
    # pending_review (отправлен), approved (принят), rejected (отклонён).
    approval_status: Mapped[ApprovalStatus | None] = mapped_column(
        Enum(ApprovalStatus), nullable=True
    )
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Кто из staff принял решение. Не FK на users.id, чтобы при удалении
    # пользователя история решений не терялась — храним просто UUID.
    approval_decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="documents")
    normative_version: Mapped[NormativeVersion] = relationship(back_populates="documents")
    report: Mapped[ProcessingReport] = relationship(back_populates="document", uselist=False)
    review_rounds: Mapped[list[ReviewRound]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    comments: Mapped[list[DocumentComment]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[DocumentSnapshot]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ProcessingReport(Base):
    __tablename__ = "processing_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    total_violations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_fixed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_required: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    report_pdf_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    volume_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_pdf_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_pdf_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[Document] = relationship(back_populates="report")
    violations: Mapped[list[ViolationRecord]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class ViolationRecord(Base):
    __tablename__ = "violation_records"
    __table_args__ = (UniqueConstraint("report_id", "id", name="uq_report_violation"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processing_reports.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="warning", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    paragraph_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Каскадные нарушения нумерации заголовков ссылаются на paragraph_index
    # «корня» каскада. NULL означает самостоятельное нарушение (либо корень,
    # либо нарушение другого типа). Используется фронтом для свёртки
    # связанных нарушений в раскрывающуюся секцию.
    caused_by_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Сигналы скоринга, по которым абзац был классифицирован (например,
    # ["literal_number:1.2.1", "bold:0.95", "centered"]). Заполняется только
    # для violations, основанных на эвристическом скоринге (heading_confirm,
    # heading_recovered, possible_missed_heading). Используется UI для
    # раскрывашки «Почему это распознано как заголовок».
    detector_signals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ViolationStatus] = mapped_column(Enum(ViolationStatus), nullable=False)
    supervisor_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped[ProcessingReport] = relationship(back_populates="violations")


class ReviewRound(Base):
    __tablename__ = "review_rounds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Не FK — чтобы история сохранялась при удалении пользователя.
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # "approved" | "rejected"
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="review_rounds")


class DocumentComment(Base):
    __tablename__ = "document_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Не FK — чтобы история сохранялась при удалении пользователя.
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="comments")


class DocumentSnapshot(Base):
    """Снимок состояния обработанного документа перед ручной правкой.

    Создаётся автоматически до каждой мутирующей операции (fix-heading-number,
    revert-caption, demote-heading, promote-heading). Позволяет откатить
    документ и нарушения к любому предыдущему состоянию.

    Файлы не копируются: поскольку каждая правка создаёт новый файл с новым
    UUID-путём, старые пути в хранилище остаются валидны — достаточно
    сохранить указатели.
    """
    __tablename__ = "document_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Монотонно возрастающий порядковый номер снимка для данного документа.
    snapshot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Тип операции, ДО которой создан снимок. Используется для отображения
    # в истории изменений на фронте.
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Человекочитаемое описание для UI (например, "Номер заголовка → 2.1").
    action_description: Mapped[str] = mapped_column(Text, nullable=False)
    # Пути к файлам на момент создания снимка (не копии — оригинальные пути).
    processed_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    processed_pdf_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Полный дамп violation_records в JSON для точного восстановления.
    violation_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="snapshots")
