from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from services.core.vkr_core.models.enums import ViolationStatus


class ViolationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    rule_reference: str
    severity: str
    description: str
    paragraph_index: int | None = None
    section_title: str | None = None
    original_text: str | None = None
    fixed_text: str | None = None
    fix_options: list[str] | None = None
    # paragraph_index «корня» каскада нарушений нумерации (если это
    # каскадное нарушение). Фронт сворачивает такие violations под root.
    caused_by_index: int | None = None
    # Сигналы скоринга для violation, основанных на эвристическом детекторе
    # заголовков. Фронт показывает их в раскрывашке «Почему это распознано
    # как заголовок» — это аргумент про прозрачность алгоритма.
    detector_signals: list[str] | None = None
    status: ViolationStatus
    supervisor_comment: str | None = None


class ViolationActionResponse(BaseModel):
    violation_id: UUID
    status: ViolationStatus


class ViolationCommentRequest(BaseModel):
    comment: str | None = None


class ViolationCommentResponse(BaseModel):
    violation_id: UUID
    supervisor_comment: str | None
