"""Проверка порядка цитирования (ТЗ §7.5).

Правило: ссылки в квадратных скобках [N] должны появляться в тексте по
возрастанию первого упоминания. Каждый номер N, использованный в тексте,
должен иметь запись в списке источников.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

# Дефис, минус, en-dash, em-dash — любой из них как разделитель диапазона.
_DASH = r"\-‒–—−"
_SEP = rf"[,{_DASH}]"
_INNER = rf"\d+(?:\s*{_SEP}\s*\d+)*"

CITATION_RE = re.compile(rf"\[({_INNER})\]")

# Две цитаты подряд без запятой: [1][2] или [1] [2].
_CONSEC_CITATION_RE = re.compile(rf"(\[{_INNER}\])\s*(\[{_INNER}\])")

# Несколько номеров в одной скобке через запятую: [1,2,3].
# Не трогаем диапазоны с тире ([1-3]) — они обрабатываются отдельно.
_COMBINED_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)+)\]")
# Для проверки границ между run'ами.
_CITATION_END_RE = re.compile(rf"\[{_INNER}\]\s*$")
_CITATION_START_RE = re.compile(rf"^\s*\[{_INNER}\]")

# [1-100] — почти всегда опечатка вместо [1, 100], никто не цитирует 20 источников подряд.
# Без проверки validate_bibliography наплодит ложных critical.
_RANGE_INSIDE_BRACKETS_RE = re.compile(rf"(\d+)\s*[{_DASH}]\s*(\d+)")
_RANGE_SPLIT_RE = re.compile(rf"\s*[{_DASH}]\s*")
_SUSPICIOUS_RANGE_THRESHOLD = 20


@dataclass
class CitationUsage:
    paragraph_index: int
    numbers: tuple[int, ...]
    # Сырые токены как в тексте: [("[48-50]", (48, 49, 50)), ...].
    # Нужны для якоря — подсвечиваем реальную подстроку, не синтезированный "[50]".
    groups: tuple[tuple[str, tuple[int, ...]], ...] = ()


def _expand(group: str) -> list[int]:
    out: list[int] = []
    for part in group.split(","):
        part = part.strip()
        rng = _RANGE_SPLIT_RE.split(part, 1)
        if len(rng) == 2:
            try:
                start, end = int(rng[0].strip()), int(rng[1].strip())
                out.extend(range(start, end + 1))
            except ValueError:
                continue
        else:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return out


def collect_citations(
    stats: DocStats,
    skip_indexes: set[int],
    max_index: int | None = None,
) -> list[CitationUsage]:
    usages: list[CitationUsage] = []
    for ps in stats.paragraphs:
        if max_index is not None and ps.index >= max_index:
            break
        if ps.index in skip_indexes or ps.is_empty:
            continue
        numbers: list[int] = []
        groups: list[tuple[str, tuple[int, ...]]] = []
        for m in CITATION_RE.finditer(ps.stripped):
            exp = _expand(m.group(1))
            if exp:
                numbers.extend(exp)
                groups.append((m.group(0), tuple(exp)))
        if numbers:
            usages.append(CitationUsage(
                paragraph_index=ps.index,
                numbers=tuple(numbers),
                groups=tuple(groups),
            ))
    return usages


def detect_suspicious_citation_ranges(
    stats: DocStats,
    skip_indexes: set[int],
) -> list[PipelineViolation]:
    """Находит ссылки вида [N-M] с большим разбросом — почти наверняка
    опечатка вместо [N, M].

    Не отменяет расширение в `_expand` (вдруг автор действительно цитирует
    20 подряд идущих источников — теоретически возможно), но выдаёт явное
    предупреждение, чтобы пользователь увидел причину массовых
    «источник X не найден» в библиографии.
    """
    violations: list[PipelineViolation] = []
    for ps in stats.paragraphs:
        if ps.index in skip_indexes or ps.is_empty:
            continue
        for cite in CITATION_RE.findall(ps.stripped):
            for m in _RANGE_INSIDE_BRACKETS_RE.finditer(cite):
                try:
                    a, b = int(m.group(1)), int(m.group(2))
                except ValueError:
                    continue
                if b - a > _SUSPICIOUS_RANGE_THRESHOLD:
                    violations.append(
                        PipelineViolation(
                            type="citation_range_suspicious",
                            rule_reference="п. 6.15",
                            description=(
                                f"Подозрительно длинный диапазон ссылок [{a}-{b}] — "
                                f"{b - a + 1} источников подряд. Возможно, опечатка "
                                f"вместо [{a}, {b}]?"
                            ),
                            status=ViolationStatus.manual_required,
                            severity=SEVERITY_WARNING,
                            paragraph_index=ps.index,
                            original_text=f"[{a}-{b}]",
                        )
                    )
    return violations


def _add_citation_commas(text: str) -> str:
    """Добавляет запятые между подряд идущими ссылками: [1][2] → [1], [2]."""
    prev = None
    while text != prev:
        prev = text
        text = _CONSEC_CITATION_RE.sub(r"\1, \2", text)
    return text


def validate_citation_order(usages: list[CitationUsage]) -> list[PipelineViolation]:
    first_seen_order: list[int] = []
    seen: set[int] = set()
    for usage in usages:
        for n in usage.numbers:
            if n not in seen:
                seen.add(n)
                first_seen_order.append(n)

    if not first_seen_order:
        return []

    pairs = list(zip(first_seen_order, first_seen_order[1:], strict=False))
    if not pairs:
        return []

    inversions = sum(1 for a, b in pairs if a > b)
    # Срабатываем только если инверсий больше 30% — единичные нарушения
    # порядка неизбежны в многоглавных работах и не являются грубой ошибкой.
    if inversions / len(pairs) < 0.3:
        return []

    return [
        PipelineViolation(
            type="citation_sequence_issue",
            rule_reference="п. 6.15",
            description=(
                "Ссылки в тексте встречаются не в порядке возрастания. "
                f"Порядок первых появлений: {first_seen_order[:15]}..."
            ),
            status=ViolationStatus.manual_required,
            severity=SEVERITY_WARNING,
        )
    ]


def check_citation_separators(
    stats: DocStats,
    skip_indexes: set[int],
) -> list[PipelineViolation]:
    """Обнаруживает соседние ссылки без разделяющей запятой ([1][2]).

    Используется на фазе анализа (до разделения check_only / full).
    В full-режиме нарушения будут исправлены автоматически функцией
    fix_citation_separators.
    """
    violations: list[PipelineViolation] = []
    for ps in stats.paragraphs:
        if ps.index in skip_indexes or ps.is_empty:
            continue
        fixed = _add_citation_commas(ps.stripped)
        if fixed == ps.stripped:
            continue
        violations.append(
            PipelineViolation(
                type="citation_separator_missing",
                rule_reference="п. 6.15",
                description="Добавлены запятые между соседними ссылками на источники.",
                status=ViolationStatus.auto_fixed,
                severity=SEVERITY_INFO,
                paragraph_index=ps.index,
            )
        )
    return violations


def _split_combined_citation(m: re.Match) -> str:
    """[1,2,3] → [1], [2], [3]"""
    parts = [p.strip() for p in m.group(1).split(",")]
    return ", ".join(f"[{p}]" for p in parts)


def check_combined_citations(
    stats: DocStats,
    skip_indexes: set[int],
) -> list[PipelineViolation]:
    """Обнаруживает ссылки вида [1,2,3] — несколько номеров в одних скобках.
    Будут автоматически разбиты на [1], [2], [3].
    """
    violations: list[PipelineViolation] = []
    for ps in stats.paragraphs:
        if ps.index in skip_indexes or ps.is_empty:
            continue
        if _COMBINED_CITATION_RE.search(ps.stripped):
            violations.append(
                PipelineViolation(
                    type="citation_combined",
                    rule_reference="п. 6.15",
                    description="Несколько номеров источников объединены в одну скобку — разбито на отдельные ссылки.",
                    status=ViolationStatus.auto_fixed,
                    severity=SEVERITY_INFO,
                    paragraph_index=ps.index,
                )
            )
    return violations


def fix_combined_citations(
    doc,
    skip_indexes: set[int],
) -> None:
    """Исправляет [1,2,3] → [1], [2], [3] непосредственно в run'ах документа."""
    for idx, paragraph in enumerate(doc.paragraphs):
        if idx in skip_indexes:
            continue
        for run in paragraph.runs:
            if not run.text:
                continue
            new_text = _COMBINED_CITATION_RE.sub(_split_combined_citation, run.text)
            if new_text != run.text:
                run.text = new_text


def fix_citation_separators(
    doc,
    skip_indexes: set[int],
) -> None:
    """Исправляет [N][M] → [N], [M] непосредственно в run'ах документа.

    Обрабатывает как случай двух ссылок в одном run'е, так и случай, когда
    закрывающая ']' одной ссылки и открывающая '[' следующей находятся в
    разных run'ах.
    """
    for idx, paragraph in enumerate(doc.paragraphs):
        if idx in skip_indexes:
            continue

        # Исправление внутри отдельных run'ов.
        for run in paragraph.runs:
            if not run.text:
                continue
            new_text = _add_citation_commas(run.text)
            if new_text != run.text:
                run.text = new_text

        # Граница run'ов: run[i] кончается на ']', run[i+1] начинается с '[' — вставляем запятую.
        runs = paragraph.runs
        for i in range(len(runs) - 1):
            t1 = runs[i].text or ""
            t2 = runs[i + 1].text or ""
            if _CITATION_END_RE.search(t1) and _CITATION_START_RE.match(t2):
                runs[i].text = t1.rstrip() + ", "
                runs[i + 1].text = t2.lstrip()
