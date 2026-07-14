"""Детерминированное обнаружение заголовков (ТЗ §6.5).

Скоринговое одно-проходное обнаружение, заменяющее старый 5-проходный
пайплайн. Алгоритм разнесён по двум модулям:

  heading_scoring.py   — чистый скоринг по абзацу (сильные + слабые + отрицательные).
  heading_hierarchy.py — построение дерева, восстановление пропусков,
                          выдача soft-нарушений.

Этот модуль — тонкая публичная точка входа: связывает два модуля и
возвращает HeadingCandidate, с которым работает остальной engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.core.vkr_core.engine.heading_hierarchy import _TOC_TITLE_RE, apply_hierarchy
from services.core.vkr_core.engine.heading_prefix import (
    parse_heading_prefix,
    strip_heading_prefix,
)
from services.core.vkr_core.engine.heading_scoring import (
    _CAPTION_RE,
    TIER_HIGH,
    TIER_MEDIUM,
    HeadingScore,
    score_all,
    score_paragraph,
)
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import SEVERITY_INFO, PipelineViolation
from services.core.vkr_core.models.enums import ViolationStatus


def _truncate(text: str, max_len: int = 80) -> str:
    return text[: max_len - 1] + "…" if len(text) > max_len else text


# Подтверждающие сигналы для after_heading-кандидата.
# Зеркалит heading_scoring._STRONG — держать в синхроне.
# short/isolated/no_period не включены: тавтология с фильтрами _find_afterheading_candidates.
_AFTERHEADING_CORROBORATING = {
    "native_style", "outline_level", "chapter_word", "appendix",
    "structural_keyword", "literal_number", "numpr_ilvl",
    "bold", "bold_partial", "centered", "all_caps",
    "font_large", "page_break_before",
}


def _find_afterheading_candidates(
    stats: DocStats,
    accepted_indexes: set[int],
    skip: set[int],
    rules: dict,
) -> list[PipelineViolation]:
    """Второй проход: ищет заголовки, стоящие сразу после принятого заголовка.

    Такие абзацы получают score=2 (NONE) в первом проходе, потому что их
    предыдущий непустой сосед — сам родительский заголовок (короткий),
    поэтому сигнал `isolated` не срабатывает. Они полностью выпадают из
    apply_hierarchy и не получают даже possible_missed_heading.

    Критерии кандидата:
    - первый непустой абзац после принятого заголовка (среди не-skip);
    - ещё не принят как заголовок;
    - короткий (≤ 100 символов, ≤ 14 слов);
    - не заканчивается точкой / ! / ? / двоеточием;
    - не подпись (рисунок, таблица…);
    - начинается с заглавной буквы;
    - не в таблице;
    - за ним следует длинный абзац (≥ 60 символов) или другой принятый заголовок.
    """
    violations: list[PipelineViolation] = []
    flagged: set[int] = set()

    for heading_idx in sorted(accepted_indexes):
        candidate_ps = None
        for j in range(heading_idx + 1, min(heading_idx + 12, len(stats.paragraphs))):
            jp = stats.paragraphs[j]
            if jp.index in skip:
                continue
            if jp.is_empty:
                continue
            if jp.index in accepted_indexes:
                break  # другой заголовок — кандидата здесь нет
            candidate_ps = jp
            break

        if candidate_ps is None or candidate_ps.index in flagged:
            continue

        ps = candidate_ps

        if ps.in_table:
            continue
        if ps.length > 100 or ps.word_count > 14:
            continue
        if ps.stripped.endswith((".", "!", "?", ":")):
            continue
        if _CAPTION_RE.match(ps.stripped):
            continue
        if _TOC_TITLE_RE.match(ps.stripped.strip()):
            continue
        if not ps.stripped or not ps.stripped[0].isupper():
            continue
        # Пункт списка Word (numPr) в большой группе — это список, не заголовок
        if ps.numpr_num_id is not None and ps.numpr_ilvl is not None:
            continue

        # Следующий непустой абзац: тело текста (длинный) или принятый заголовок
        next_len = 0
        next_is_heading = False
        for k in range(ps.index + 1, len(stats.paragraphs)):
            kp = stats.paragraphs[k]
            if kp.is_empty or kp.index in skip:
                continue
            if kp.index in accepted_indexes:
                next_is_heading = True
            else:
                next_len = kp.length
            break

        if not next_is_heading and next_len < 60:
            continue

        parent_prefix = parse_heading_prefix(stats.paragraphs[heading_idx].stripped)
        after_bare_chapter = (
            parent_prefix is not None
            and parent_prefix.kind == "chapter_word"
            and not parent_prefix.title
        )

        # Соседство с заголовком — только маркер метода, не признак заголовка.
        # Требуем ≥1 реального сигнала от скорера. Исключение — split-heading:
        # строка "ГЛАВА 1" и следующая строка-название главы.
        score = score_paragraph(ps, stats, rules, skip)
        corroborating = sorted(
            {s.split(":", 1)[0] for s in score.signals} & _AFTERHEADING_CORROBORATING
        )
        if not corroborating and not after_bare_chapter:
            continue

        flagged.add(ps.index)
        text = ps.stripped
        detector_signals = ["after_heading", *corroborating]
        if after_bare_chapter:
            detector_signals.append("after_bare_chapter")
        violations.append(
            PipelineViolation(
                type="possible_missed_heading",
                rule_reference="п. 6.11",
                description=(
                    f"Возможный пропущенный заголовок: «{_truncate(text)}». "
                    f"Если это заголовок — оформите его явно (стилем или номером)."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_INFO,
                paragraph_index=ps.index,
                section_title=text,
                original_text=text,
                detector_signals=detector_signals,
            )
        )

    return violations


# Значения source — уровни уверенности. Оставлены как константы для совместимости.
HEADING_SOURCE_HIGH = "high"
HEADING_SOURCE_MEDIUM = "medium"
HEADING_SOURCE_RECOVERED = "low_recovered"


@dataclass
class HeadingCandidate:
    paragraph_index: int
    level: int
    text: str
    source: str
    signals: list[str] = field(default_factory=list)
    title_only: str = ""
    # Номер из текстового префикса или из w:numPr.
    # Нужен для validate_heading_numbers — заголовки с numPr без текстового номера иначе выпадают из проверки.
    derived_number: str | None = None


def _strip_numbering(text: str) -> str:
    return strip_heading_prefix(text)


def _score_to_candidate(score: HeadingScore, text: str, tier_override: str | None = None) -> HeadingCandidate:
    if tier_override is not None:
        source = tier_override
    elif score.tier == TIER_HIGH:
        source = HEADING_SOURCE_HIGH
    elif score.tier == TIER_MEDIUM:
        source = HEADING_SOURCE_MEDIUM
    else:
        source = HEADING_SOURCE_RECOVERED
    return HeadingCandidate(
        paragraph_index=score.index,
        level=score.level,
        text=text,
        source=source,
        signals=list(score.signals),
        title_only=_strip_numbering(text),
        derived_number=score.derived_number,
    )


def detect_headings_full(
    stats: DocStats,
    rules: dict,
    title_page_indexes: set[int],
) -> tuple[list[HeadingCandidate], list[PipelineViolation]]:
    """Возвращает кортеж (headings, soft_violations).

    Soft-нарушения — это manual_required для подтверждения MEDIUM-кандидатов,
    info-сообщения о восстановленных через gap recovery заголовках и заметки
    "possible missed heading" для неоформленных семантических кандидатов.
    """
    scores = score_all(stats, rules, title_page_indexes)
    hierarchy = apply_hierarchy(scores, stats)

    # Индексы, принятые через gap recovery (LOW → принят).
    recovered_indexes = {
        v.paragraph_index
        for v in hierarchy.soft_violations
        if v.type == "heading_recovered"
    }

    candidates: list[HeadingCandidate] = []
    seen_texts: set[str] = set()
    for score in hierarchy.accepted:
        text = stats.paragraphs[score.index].stripped
        norm_text = " ".join(text.lower().split())
        if norm_text and norm_text in seen_texts:
            continue  # два одинаковых абзаца-заголовка — пропускаем дубликат
        seen_texts.add(norm_text)
        override = HEADING_SOURCE_RECOVERED if score.index in recovered_indexes else None
        candidates.append(_score_to_candidate(score, text, tier_override=override))

    accepted_indexes = {c.paragraph_index for c in candidates}
    already_flagged = {v.paragraph_index for v in hierarchy.soft_violations}
    afterheading = [
        v for v in _find_afterheading_candidates(stats, accepted_indexes, title_page_indexes, rules)
        if v.paragraph_index not in already_flagged
    ]

    return candidates, hierarchy.soft_violations + afterheading


def detect_headings(
    stats: DocStats,
    rules: dict,
    title_page_indexes: set[int],
) -> list[HeadingCandidate]:
    """Старая точка входа — для вызывающих, которым soft-нарушения не нужны."""
    headings, _ = detect_headings_full(stats, rules, title_page_indexes)
    return headings
