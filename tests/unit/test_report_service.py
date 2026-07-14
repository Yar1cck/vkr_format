from __future__ import annotations

from pathlib import Path

from services.core.vkr_core.engine.violations import PipelineViolation
from services.core.vkr_core.models.enums import ViolationStatus
from services.core.vkr_core.services.report_service import generate_report_pdf


def test_generate_report_pdf_handles_markup_characters() -> None:
    violation = PipelineViolation(
        type="table_reference_missing",
        rule_reference="7.3.C2",
        description="Совет: добавьте ссылку <см. таблицу 1> & проверьте номер.",
        status=ViolationStatus.manual_required,
        severity="info",
        paragraph_index=2,
        original_text="табл. 1 <данные>",
    )

    path = generate_report_pdf([violation], toc_warning="Проверьте содержание & поля", volume_pages=42)

    assert Path(path).exists()
    assert Path(path).stat().st_size > 0
