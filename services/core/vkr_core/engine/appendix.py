"""Валидация оформления приложений (Порядок МИИГАиК §5.8, ГОСТ 7.32-2017 §6.14).

Проверяет:
  1. Буквенную последовательность — А, Б, В… без пропусков и исключённых букв.
  2. Наличие ссылок в тексте ВКР до первого приложения.
  3. Соответствие порядка приложений порядку их первых упоминаний в тексте.
"""
from __future__ import annotations

import re

from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

# По ГОСТ 7.32-2017 §6.14: буквы А–Я за исключением Ё, З, Й, О, Ч, Ъ, Ы, Ь.
_VALID_LETTERS = "АБВГДЕЖИКЛМНПРСТУФХЦШЩЭЮЯ"
_VALID_SET = set(_VALID_LETTERS)

# Визуально идентичные латинские омоглифы → кириллица.
# Пример: студент набрал «Приложение A» латинской A — система нормализует.
_LATIN_HOMOGLYPHS: dict[str, str] = {
    'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н',
    'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т', 'X': 'Х',
}

_LETTER_RE = re.compile(r"^приложение\s+([а-яёa-zA-Z])\b", re.IGNORECASE)


def _ref_re(letter: str) -> re.Pattern[str]:
    # \w* — все падежные формы: приложение, приложения, приложению,
    # приложении, приложением, приложений.
    return re.compile(
        r"\bприложени\w*\s+" + re.escape(letter) + r"\b",
        re.IGNORECASE,
    )


def _detect_appendices(headings) -> list[tuple[int, str]]:
    """Возвращает [(para_idx, LETTER_UPPER)] для заголовков «Приложение Х»."""
    result = []
    for h in headings:
        m = _LETTER_RE.match(h.text.strip())
        if m:
            letter = m.group(1).upper()
            letter = _LATIN_HOMOGLYPHS.get(letter, letter)
            result.append((h.paragraph_index, letter))
    return result


def validate_appendices(
    headings,
    stats: DocStats,
    title_page_indexes: set[int],
) -> list[PipelineViolation]:
    """Проверяет правила оформления приложений."""
    violations: list[PipelineViolation] = []
    appendix_list = _detect_appendices(headings)
    if not appendix_list:
        return violations

    # Ссылки ищем только в тексте до первого приложения.
    first_appendix_para = appendix_list[0][0]
    body_paras = [
        ps for ps in stats.paragraphs
        if ps.index not in title_page_indexes
        and ps.index < first_appendix_para
        and not ps.is_empty
    ]

    # 1. Буквенная последовательность.
    seen: set[str] = set()
    expected_pos = 0
    for para_idx, letter in appendix_list:
        if letter not in _VALID_SET:
            violations.append(PipelineViolation(
                type="appendix_letter_invalid",
                rule_reference="п. 6.18",
                description=(
                    f"«Приложение {letter}»: буква «{letter}» не входит в допустимый ряд "
                    f"по ГОСТ 7.32-2017 §6.14 (исключены Ё, З, Й, О, Ч, Ъ, Ы, Ь)."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
                paragraph_index=para_idx,
            ))
            continue
        if letter in seen:
            violations.append(PipelineViolation(
                type="appendix_letter_gap",
                rule_reference="п. 6.18",
                description=f"«Приложение {letter}»: буква «{letter}» уже использована ранее.",
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
                paragraph_index=para_idx,
            ))
            continue
        seen.add(letter)
        cur_pos = _VALID_LETTERS.index(letter)
        if cur_pos != expected_pos:
            expected_letter = _VALID_LETTERS[expected_pos]
            violations.append(PipelineViolation(
                type="appendix_letter_gap",
                rule_reference="п. 6.18",
                description=(
                    f"«Приложение {letter}»: ожидалось «Приложение {expected_letter}» — "
                    f"нарушена последовательность обозначений приложений."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
                paragraph_index=para_idx,
            ))
        expected_pos = cur_pos + 1

    # 2. Ссылки в тексте.
    first_refs: dict[str, int] = {}
    for para_idx, letter in appendix_list:
        if letter not in _VALID_SET or letter in first_refs:
            continue
        pat = _ref_re(letter)
        ref_pos = next(
            (i for i, ps in enumerate(body_paras) if pat.search(ps.stripped)),
            None,
        )
        if ref_pos is None:
            violations.append(PipelineViolation(
                type="appendix_not_referenced",
                rule_reference="п. 6.18",
                description=f"Приложение «{letter}» не упомянуто в тексте ВКР.",
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
                paragraph_index=para_idx,
            ))
        else:
            first_refs[letter] = ref_pos

    # 3. Порядок приложений совпадает с порядком первых ссылок.
    ordered = [lt for _, lt in appendix_list if lt in _VALID_SET and lt in first_refs]
    for i in range(len(ordered) - 1):
        a, b = ordered[i], ordered[i + 1]
        if first_refs[a] > first_refs[b]:
            para_idx_b = next(idx for idx, lt in appendix_list if lt == b)
            violations.append(PipelineViolation(
                type="appendix_order_violation",
                rule_reference="п. 6.18",
                description=(
                    f"Приложение «{b}» первый раз упомянуто в тексте раньше, чем «{a}»; "
                    f"приложения должны располагаться в порядке ссылок на них в тексте."
                ),
                status=ViolationStatus.manual_required,
                severity=SEVERITY_WARNING,
                paragraph_index=para_idx_b,
            ))

    return violations
