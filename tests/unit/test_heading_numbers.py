"""Тесты heading_numbers.py — последовательность нумерации заголовков (§6.5)."""
from __future__ import annotations

from dataclasses import dataclass

from services.core.vkr_core.engine.heading_numbers import validate_heading_numbers
from services.core.vkr_core.engine.stats import DocStats, ParagraphStats


@dataclass
class _H:
    paragraph_index: int
    text: str
    level: int = 1
    title_only: str = ""
    derived_number: str | None = None


def _ps(idx: int) -> ParagraphStats:
    return ParagraphStats(
        index=idx, text="", stripped="", length=0, word_count=0,
        alignment=None, first_line_indent_cm=None, left_indent_cm=None,
        max_font_size_pt=14.0, modal_font_size_pt=14.0, font_family="Times New Roman",
        bold_ratio=0.0, italic_ratio=0.0,
        ends_with_period=False, is_upper=False, is_empty=True,
        in_table=False, style_name="Normal", numbered=False,
        numbering_tokens=(), has_tab=False,
    )


def _stats(n: int = 30) -> DocStats:
    return DocStats(paragraphs=[_ps(i) for i in range(n)])


def test_correct_sequence_no_violations() -> None:
    headings = [
        _H(0, "1 Введение"),
        _H(1, "1.1 Постановка"),
        _H(2, "1.2 Обзор"),
        _H(3, "2 Глава 2"),
        _H(4, "2.1 Метод"),
    ]
    assert validate_heading_numbers(headings, _stats()) == []


def test_gap_in_h1_detected() -> None:
    # 1 → 3 — пропущена 2
    headings = [_H(0, "1 Введение"), _H(1, "3 Глава 3")]
    violations = validate_heading_numbers(headings, _stats())
    assert any(v.type == "heading_number_conflict" for v in violations)


def test_deep_first_advances_parent_counters() -> None:
    # После «1.1» счётчики 1-го уровня тоже должны быть синхронизированы,
    # чтобы «1.2» не давал ложного конфликта.
    headings = [
        _H(0, "1 Введение"),
        _H(1, "1.1 Подраздел"),
        _H(2, "1.2 Подраздел"),
    ]
    assert validate_heading_numbers(headings, _stats()) == []


def test_cascade_collapsed_to_root() -> None:
    # Одна ошибка в начале → следующие заголовки помечаются caused_by_index
    headings = [
        _H(0, "1 Введение"),
        _H(1, "3 Глава 3"),  # root
        _H(2, "4 Глава 4"),  # caused_by
        _H(3, "5 Глава 5"),  # caused_by
    ]
    violations = validate_heading_numbers(headings, _stats())
    roots = [v for v in violations if v.caused_by_index is None]
    cascaded = [v for v in violations if v.caused_by_index is not None]
    assert len(roots) == 1
    assert all(c.caused_by_index == 1 for c in cascaded)


def test_ok_heading_closes_cascade() -> None:
    headings = [
        _H(0, "1 Введение"),
        _H(1, "3 Глава 3"),  # ошибка → root
        _H(2, "4 Глава 4"),  # ok относительно сдвинутого счётчика → закрывает каскад
        _H(3, "6 Глава 6"),  # снова root (после OK)
    ]
    violations = validate_heading_numbers(headings, _stats())
    roots = [v for v in violations if v.caused_by_index is None]
    assert len(roots) == 2


def test_chapter_word_prefix_recognised() -> None:
    headings = [
        _H(0, "Глава 1. Введение"),
        _H(1, "Глава 3. Глава"),
    ]
    violations = validate_heading_numbers(headings, _stats())
    assert any(v.type == "heading_number_conflict" for v in violations)


def test_roman_chapter_prefix_recognised() -> None:
    headings = [
        _H(0, "Глава I. Введение"),
        _H(1, "Глава III. Обзор"),
    ]
    violations = validate_heading_numbers(headings, _stats())
    assert any(v.type == "heading_number_conflict" for v in violations)


def test_compact_number_prefix_recognised() -> None:
    headings = [
        _H(0, "1.Введение"),
        _H(1, "1.1.Анализ"),
        _H(2, "1.2.Проектирование"),
    ]
    assert validate_heading_numbers(headings, _stats()) == []


def test_derived_number_fallback_for_numpr() -> None:
    # В тексте нет номера, но derived_number из w:numPr задаёт «1»
    h1 = _H(0, "Введение")
    h1.derived_number = "1"
    h2 = _H(1, "Заключение")
    h2.derived_number = "3"  # gap
    violations = validate_heading_numbers([h1, h2], _stats())
    assert any(v.type == "heading_number_conflict" for v in violations)


def test_fix_options_include_alternatives() -> None:
    headings = [
        _H(0, "1 Введение"),
        _H(1, "1.2 Подраздел"),  # ожидалось 1.1, либо H1 -> 2
    ]
    violations = validate_heading_numbers(headings, _stats())
    assert violations
    opts = violations[0].fix_options
    assert "1.2" in opts and "1.1" in opts
