"""Оценка объёма (ТЗ §7.8).

Звать LibreOffice для разбивки по страницам в горячем пути нельзя. Вместо
этого оцениваем число страниц по количеству символов в теле документа с
калибровочной константой (~1800 символов на страницу при TNR 14pt,
интервал 1.5, A4 с полями из ТЗ). Оценка идёт как рекомендация — жёсткого
отказа никогда не вызывает.
"""

from __future__ import annotations

from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

CHARS_PER_PAGE = 1800  # ~A4, TNR 14pt, интервал 1.5, поля из ТЗ


def estimate_pages(
    stats: DocStats,
    title_page_indexes: set[int],
    extra_chars: int = 0,
) -> int:
    total_chars = sum(
        ps.length for ps in stats.paragraphs if ps.index not in title_page_indexes
    ) + extra_chars
    return max(1, round(total_chars / CHARS_PER_PAGE))


def validate_volume(pages: int, rules: dict) -> list[PipelineViolation]:
    limits_config = rules.get("volume_limits", {})
    min_pages = int(limits_config.get("min", 0))
    max_pages = int(limits_config.get("max", 0))

    violations: list[PipelineViolation] = []
    work_label = "бакалаврской работы"

    if min_pages and pages < min_pages:
        violations.append(
            PipelineViolation(
                type="volume_below_minimum",
                rule_reference="п. 5.1",
                description=(
                    f"Оценочный объём {work_label} ({pages} стр.) ниже минимального ({min_pages})."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
            )
        )

    if max_pages and pages > max_pages:
        violations.append(
            PipelineViolation(
                type="volume_above_maximum",
                rule_reference="п. 5.1",
                description=(
                    f"Оценочный объём {work_label} ({pages} стр.) превышает максимум ({max_pages})."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
            )
        )

    return violations
