from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProcessingReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    created_at: datetime
    total_violations: int
    auto_fixed: int
    manual_required: int
    report_storage_path: str
    report_pdf_storage_path: str | None = None
    diff_storage_path: str | None = None
    volume_pages: int | None = None
    # Путь PDF-превью обработанного документа. Меняется (новый uuid-файл)
    # каждый раз, когда фоновая финализация перерисовала превью — фронт по
    # его смене понимает, что пора обновить превью (а не гадать таймером).
    processed_pdf_storage_path: str | None = None
