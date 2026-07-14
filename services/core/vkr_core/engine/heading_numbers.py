"""Проверка последовательности нумерации заголовков (ТЗ §6.5).

Находит случаи, когда числовой префикс нарушает последовательность
(например, "1." появляется после "1.2") и выдаёт нарушения для ручной
проверки с тремя вариантами номера на выбор:
  [0] исходный — оставить как написано
  [1] ожидаемый на указанном в тексте уровне (правка по последовательности)
  [2] ожидаемый на соседнем уровне (на уровень выше или ниже)

Модуль работает с заголовками, уже прошедшими скоринговое обнаружение.
Различение пункта списка и заголовка выполняется выше — в
heading_scoring.py — поэтому здесь эвристик про списки больше нет.
"""

from __future__ import annotations

import re

from services.core.vkr_core.engine.detection import HeadingCandidate
from services.core.vkr_core.engine.heading_prefix import parse_heading_prefix
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import (
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus

_BARE_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _parse_number(text: str) -> tuple[str, int] | None:
    """Возвращает (raw_digits, level) или None, если числового префикса нет.

    Понимает обычный "1.2 Title", слитный "1.2.Title" и формы
    со словом-главой вроде "Глава I Title".
    """
    prefix = parse_heading_prefix(text)
    if prefix is None:
        return None
    return prefix.number, prefix.level


def _parse_number_from_candidate(candidate) -> tuple[str, int] | None:
    """Сначала пытается извлечь номер из текста заголовка. Если в тексте
    номера нет — fallback на `candidate.derived_number`, симулированный
    из `<w:numPr>`. Это закрывает кейс автонумерации Word: студент видит
    в Word номер «1.1», но в plain-тексте абзаца только «Введение», и
    без этого fallback заголовок пропускал проверку последовательности.
    """
    parsed = _parse_number(candidate.text)
    if parsed is not None:
        return parsed
    derived = getattr(candidate, "derived_number", None)
    if not derived or not _BARE_NUMBER_RE.match(derived):
        return None
    level = derived.count(".") + 1
    return derived, level


def _expected_number(counters: list[int], level: int) -> str:
    """Строит следующий ожидаемый номер на указанном уровне.

    Если родительский счётчик равен 0 (главы или раздела ещё не было),
    поднимаем уровень вверх, чтобы не выдавать бессмыслицу "0.1".
    """
    level = max(1, min(level, 3))
    if level >= 2 and counters[0] == 0:
        level = 1
    if level == 3 and counters[1] == 0:
        level = 2
    if level == 1:
        return str(counters[0] + 1)
    if level == 2:
        return f"{counters[0]}.{counters[1] + 1}"
    return f"{counters[0]}.{counters[1]}.{counters[2] + 1}"


def _advance_counters(counters: list[int], raw: str, level: int) -> None:
    """Обновляет все позиции счётчиков по наблюдаемому исходному номеру.

    Раньше писали только в `counters[level - 1]`, из-за чего родительские
    счётчики оставались устаревшими, когда документ начинался сразу с
    глубокого заголовка (например, первый заголовок "1.1" — counters[0]
    оставался 0).
    """
    parts = [int(x) for x in raw.split(".")]
    for i, part in enumerate(parts[:3]):
        counters[i] = part
    for i in range(level, 3):
        counters[i] = 0


def validate_heading_numbers(
    headings: list[HeadingCandidate],
    stats: DocStats,
) -> list[PipelineViolation]:
    """Проверяет последовательность номеров заголовков.

    Каскад: одна ошибка нумерации в начале документа сдвигает счётчики, и
    последующие заголовки тоже не сходятся с ожидаемой последовательностью —
    хотя сами они написаны правильно относительно ошибочного «соседа».
    Чтобы не показывать пользователю 15 одинаковых нарушений, помечаем все
    нарушения, идущие подряд после первого, через `caused_by_index = root`.
    UI сворачивает такие violations под раскрывающуюся секцию у корня.

    Каскад «закрывается» при первом OK-заголовке: после него начинается
    новая независимая проверка, и следующая ошибка снова считается корнем.
    Это компромисс: пользователю обычно достаточно исправить один корень,
    но если в документе действительно две независимые проблемы, они
    останутся отдельными карточками.
    """
    violations: list[PipelineViolation] = []
    counters = [0, 0, 0]
    cascade_root_index: int | None = None

    for candidate in headings:
        parsed = _parse_number_from_candidate(candidate)
        if parsed is None:
            continue

        raw, level = parsed

        option_a = _expected_number(counters, level)
        if level > 1:
            option_b = _expected_number(counters, level - 1)
        else:
            option_b = _expected_number(counters, 2) if counters[0] > 0 else None

        if raw != option_a:
            options: list[str] = [raw]
            if option_a not in options:
                options.append(option_a)
            if option_b and option_b not in options:
                options.append(option_b)

            title_only = (candidate.title_only or "").strip() or candidate.text
            alt_hint = f" Или выберите «{option_b}» (уровень выше/ниже)." if option_b and option_b != option_a else ""
            violations.append(
                PipelineViolation(
                    type="heading_number_conflict",
                    rule_reference="п. 6.11",
                    description=(
                        f"«{title_only}»: в тексте стоит «{raw}», "
                        f"по последовательности должно быть «{option_a}».{alt_hint}"
                    ),
                    status=ViolationStatus.manual_required,
                    severity=SEVERITY_WARNING,
                    paragraph_index=candidate.paragraph_index,
                    section_title=candidate.text,
                    original_text=raw,
                    fix_options=options,
                    caused_by_index=cascade_root_index,
                )
            )
            if cascade_root_index is None:
                cascade_root_index = candidate.paragraph_index
        else:
            # OK-заголовок — счётчики синхронизировались, каскад закрыт.
            cascade_root_index = None

        _advance_counters(counters, raw, level)

    return violations
