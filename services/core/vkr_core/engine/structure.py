"""Проверка обязательных структурных элементов (ТЗ §7.7).

Корректная ВКР должна содержать в указанном порядке:
  1. Титульный лист
  2. Страницу задания (если задано в правилах)
  3. Содержание
  4. Введение
  5. Заголовки глав
  6. Заключение
  7. Список использованных источников
  8. (Опционально) Приложения

Этот модуль проверяет только наличие и грубый порядок — точная позиционная
проверка вне его задач, отдельные заголовки уже проверены детектором.
"""

from __future__ import annotations

from services.core.vkr_core.engine.detection import HeadingCandidate
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

REQUIRED = ("contents", "introduction", "conclusion", "references")

# Необязательные разделы, которые при наличии должны стоять ДО «Введения».
OPTIONAL_BEFORE_INTRO = ("terms",)

SECTION_DISPLAY = {
    "contents":     "Содержание",
    "introduction": "Введение",
    "conclusion":   "Заключение",
    "references":   "Список использованных источников",
    "terms":        "Термины и определения",
}


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def validate_structure(
    stats: DocStats,
    rules: dict,
    headings: list[HeadingCandidate],
    title_page_indexes: set[int],
) -> list[PipelineViolation]:
    structural = rules.get("structural_elements", {})
    violations: list[PipelineViolation] = []

    heading_texts_lower = [_norm(h.title_only or h.text) for h in headings]
    blob_texts = [
        _norm(ps.stripped) for ps in stats.paragraphs if ps.index not in title_page_indexes and not ps.is_empty
    ]

    positions: dict[str, int] = {}

    def _find_section(key: str) -> int | None:
        aliases = {_norm(a) for a in structural.get(key, [])}
        if not aliases:
            return None
        for idx, text in enumerate(blob_texts):
            if text in aliases:
                return idx
        for idx, text in enumerate(heading_texts_lower):
            if text in aliases:
                return idx
        if stats.sdt_paragraph_texts & aliases:
            return -1
        return None

    for key in REQUIRED:
        found_at = _find_section(key)
        if found_at is None:
            # «Список использованных источников» как отсутствующий раздел —
            # каноническое нарушение 7.6.B0 выдаёт bibliography.py. Дублировать
            # его здесь не нужно: иначе студент видит два одинаковых
            # критических замечания об одном и том же.
            if key == "references":
                continue
            display = SECTION_DISPLAY.get(key, key)
            violations.append(
                PipelineViolation(
                    type="missing_structural_section",
                    rule_reference="п. 5.1",
                    description=f"Отсутствует обязательный раздел «{display}».",
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_CRITICAL,
                )
            )
        else:
            positions[key] = found_at

    for key in OPTIONAL_BEFORE_INTRO:
        found_at = _find_section(key)
        if found_at is not None:
            positions[key] = found_at

    ordered_keys = [k for k in REQUIRED if k in positions]
    # strict=False — последовательность соседних пар короче списка ровно на 1.
    for a, b in zip(ordered_keys, ordered_keys[1:], strict=False):
        if positions[a] >= positions[b]:
            violations.append(
                PipelineViolation(
                    type="structural_order_violation",
                    rule_reference="п. 5.1",
                    description=(
                        f"Нарушен порядок разделов: «{SECTION_DISPLAY.get(a, a)}» "
                        f"должен располагаться до «{SECTION_DISPLAY.get(b, b)}»."
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_CRITICAL,
                )
            )

    # Проверка позиции необязательных разделов.
    intro_pos = positions.get("introduction")
    for key in OPTIONAL_BEFORE_INTRO:
        if key not in positions or intro_pos is None:
            continue
        if positions[key] >= intro_pos:
            display = SECTION_DISPLAY.get(key, key)
            violations.append(
                PipelineViolation(
                    type="structural_order_violation",
                    rule_reference="п. 5.1",
                    description=(
                        f"Раздел «{display}» должен располагаться до «Введения», "
                        f"а не после него."
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_WARNING,
                )
            )

    return violations
