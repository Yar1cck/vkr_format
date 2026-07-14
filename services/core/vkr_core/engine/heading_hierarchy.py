"""Проверка иерархии заголовков и восстановление пропусков (ТЗ §6.5).

После того как `score_all` вернул HeadingScore по абзацам, этот модуль:

  1. Принимает HIGH-кандидатов без условий.
  2. MEDIUM-кандидатов НЕ принимает: абзац остаётся обычным текстом, а
     manual_required-нарушение heading_confirm просит студента при желании
     оформить его как заголовок (дефолт — «это просто текст»).
  3. Восстанавливает LOW-кандидатов, заполняющих дырки в нумерованной
     иерархии (пример: 1.1.1 HIGH, [LOW 1.1.2], 1.1.3 HIGH → 1.1.2
     повышается до принятых) — это единственный авто-приём ниже HIGH.
  4. Для оставшихся LOW "семантических" кандидатов (короткие изолированные
     неоформленные строки) тоже выдаёт heading_confirm без автоприёма.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.core.vkr_core.engine.heading_scoring import (
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    HeadingScore,
)
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*$")

# СОДЕРЖАНИЕ/ОГЛАВЛЕНИЕ — раздел конвейера, не кандидат на заголовок.
# Также используется в detection._find_afterheading_candidates.
_TOC_TITLE_RE = re.compile(r"^(содержание|оглавление)$", re.IGNORECASE)


@dataclass
class HierarchyResult:
    accepted: list[HeadingScore]
    soft_violations: list[PipelineViolation]


def _parse_number(derived: str | None) -> tuple[int, ...] | None:
    if not derived or not _NUMBER_RE.match(derived):
        return None
    try:
        return tuple(int(p) for p in derived.split("."))
    except ValueError:
        return None


def _truncate(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _is_gap_fill(
    candidate: HeadingScore,
    accepted_numbers: list[tuple[int, tuple[int, ...]]],
) -> bool:
    """Проверяет, заполняет ли candidate.derived_number дыру между двумя
    принятыми заголовками той же глубины, у которых совпадает префикс."""
    cand_num = _parse_number(candidate.derived_number)
    if cand_num is None:
        return False

    prefix = cand_num[:-1]
    last = cand_num[-1]

    before: tuple[int, tuple[int, ...]] | None = None
    after: tuple[int, tuple[int, ...]] | None = None
    for idx, num in accepted_numbers:
        if len(num) != len(cand_num) or num[:-1] != prefix:
            continue
        if num[-1] < last:
            if before is None or idx > before[0]:
                before = (idx, num)
        elif num[-1] > last:
            if after is None or idx < after[0]:
                after = (idx, num)

    if before is None or after is None:
        return False
    return before[0] < candidate.index < after[0]


def _has_visual_heading_signal(candidate: HeadingScore) -> bool:
    sig_names = {s.split(":", 1)[0] for s in candidate.signals}
    return bool(
        sig_names
        & {
            "native_style",
            "outline_level",
            "numpr_ilvl",
            "bold",
            "bold_partial",
            "centered",
            "all_caps",
            "font_large",
            "font_small",
            "page_break_before",
        }
    )


def _is_first_child_fill(
    candidate: HeadingScore,
    accepted_numbers: list[tuple[int, tuple[int, ...]]],
) -> bool:
    """Восстановление первого подраздела: parent=1, candidate=1.1, next=1.2.

    Это уже не "дыра между двумя соседями" (у 1.1 нет предыдущего sibling),
    поэтому проверяем родителя и следующий sibling. Требуем визуальный
    заголовочный сигнал, чтобы обычная фраза "1.1 Текст." не повышалась
    только из-за номера.
    """
    cand_num = _parse_number(candidate.derived_number)
    if cand_num is None or len(cand_num) < 2 or cand_num[-1] != 1:
        return False
    if not _has_visual_heading_signal(candidate):
        return False

    parent_num = cand_num[:-1]
    parent: tuple[int, tuple[int, ...]] | None = None
    next_sibling: tuple[int, tuple[int, ...]] | None = None
    for idx, num in accepted_numbers:
        if num == parent_num and idx < candidate.index:
            if parent is None or idx > parent[0]:
                parent = (idx, num)
        elif len(num) == len(cand_num) and num[:-1] == parent_num and num[-1] > 1:
            if idx > candidate.index and (
                next_sibling is None or idx < next_sibling[0]
            ):
                next_sibling = (idx, num)

    return parent is not None and next_sibling is not None


def _is_semantic_candidate(score: HeadingScore) -> bool:
    """True, если LOW-скор — короткая изолированная строка без форматирования.

    Показываем пользователю на проверку, но не принимаем автоматически.
    """
    sig_names = {s.split(":", 1)[0] for s in score.signals}
    return "isolated" in sig_names and "short" in sig_names and "no_period" in sig_names


def apply_hierarchy(
    scores: list[HeadingScore],
    stats: DocStats,
) -> HierarchyResult:
    scores_by_index = sorted(scores, key=lambda s: s.index)

    accepted: list[HeadingScore] = []
    accepted_indexes: set[int] = set()
    soft_violations: list[PipelineViolation] = []

    for s in scores_by_index:
        if s.tier == TIER_HIGH:
            accepted.append(s)
            accepted_indexes.add(s.index)
        elif s.tier == TIER_MEDIUM:
            # MEDIUM — не принимаем автоматически. Абзац остаётся телом,
            # пользователь нажимает «Оформить как заголовок» если нужно.
            # Ложный заголовок ломает структуру; promote = только явное действие.
            text = stats.paragraphs[s.index].stripped
            if _TOC_TITLE_RE.match(text.strip()):
                continue  # «СОДЕРЖАНИЕ»/«ОГЛАВЛЕНИЕ» — раздел конвейера, не шумим
            soft_violations.append(
                PipelineViolation(
                    type="heading_confirm",
                    rule_reference="п. 6.11",
                    description=(
                        f"Возможный заголовок «{_truncate(text)}» оставлен "
                        f"обычным текстом. Если это раздел — нажмите "
                        f"«Оформить как заголовок»."
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_WARNING,
                    paragraph_index=s.index,
                    section_title=text,
                    original_text=text,
                    detector_signals=list(s.signals),
                )
            )

    accepted_numbers: list[tuple[int, tuple[int, ...]]] = []
    for s in accepted:
        num = _parse_number(s.derived_number)
        if num is not None:
            accepted_numbers.append((s.index, num))
    accepted_numbers.sort()

    for s in scores_by_index:
        if s.tier != TIER_LOW or s.index in accepted_indexes:
            continue
        text = stats.paragraphs[s.index].stripped
        if _TOC_TITLE_RE.match(text.strip()):
            continue  # «СОДЕРЖАНИЕ»/«ОГЛАВЛЕНИЕ» — раздел конвейера, не шумим
        if _is_gap_fill(s, accepted_numbers) or _is_first_child_fill(
            s, accepted_numbers
        ):
            accepted.append(s)
            accepted_indexes.add(s.index)
            soft_violations.append(
                PipelineViolation(
                    type="heading_recovered",
                    rule_reference="п. 6.11",
                    description=(
                        f"Восстановлен пропущенный заголовок «{_truncate(text)}» "
                        f"между соседями в иерархии."
                    ),
                    status=ViolationStatus.auto_fixed,
                    severity=SEVERITY_INFO,
                    paragraph_index=s.index,
                    section_title=text,
                    original_text=text,
                    detector_signals=list(s.signals),
                )
            )
        elif _is_semantic_candidate(s):
            # Как и MEDIUM — не принимаем; абзац остаётся телом.
            soft_violations.append(
                PipelineViolation(
                    type="heading_confirm",
                    rule_reference="п. 6.11",
                    description=(
                        f"Возможный заголовок «{_truncate(text)}» оставлен "
                        f"обычным текстом. Если это раздел — нажмите "
                        f"«Оформить как заголовок»."
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_WARNING,
                    paragraph_index=s.index,
                    section_title=text,
                    original_text=text,
                    detector_signals=list(s.signals),
                )
            )

    accepted.sort(key=lambda s: s.index)
    return HierarchyResult(accepted=accepted, soft_violations=soft_violations)
