from __future__ import annotations

from dataclasses import dataclass, field

from services.core.vkr_core.models.enums import ViolationStatus

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass
class PipelineViolation:
    type: str
    rule_reference: str
    description: str
    status: ViolationStatus
    severity: str = SEVERITY_WARNING
    paragraph_index: int | None = None
    section_title: str | None = None
    original_text: str | None = None
    fixed_text: str | None = None
    fix_options: list[str] | None = None
    # paragraph_index «корня» каскада нарушений нумерации. NULL для самих
    # корней и для нарушений других типов. Используется UI для группировки.
    caused_by_index: int | None = None
    # Сигналы скоринга, объясняющие почему абзац классифицирован так. Только
    # для violations, основанных на эвристическом скоринге. Пример:
    # ["literal_number:1.2.1", "bold:0.95", "centered", "isolated"].
    detector_signals: list[str] | None = None
    context: dict = field(default_factory=dict)
