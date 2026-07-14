"""Тесты appendix.py — валидация приложений (§5.8 / ГОСТ 7.32-2017)."""
from __future__ import annotations

from dataclasses import dataclass

from services.core.vkr_core.engine.appendix import validate_appendices
from services.core.vkr_core.engine.stats import DocStats, ParagraphStats


@dataclass
class _H:
    paragraph_index: int
    text: str
    level: int = 1


def _ps(idx: int, text: str) -> ParagraphStats:
    return ParagraphStats(
        index=idx, text=text, stripped=text.strip(), length=len(text),
        word_count=len(text.split()), alignment=None,
        first_line_indent_cm=None, left_indent_cm=None,
        max_font_size_pt=14.0, modal_font_size_pt=14.0, font_family="Times New Roman",
        bold_ratio=0.0, italic_ratio=0.0,
        ends_with_period=text.endswith("."), is_upper=text.isupper(),
        is_empty=not text.strip(), in_table=False, style_name="Normal",
        numbered=False, numbering_tokens=(), has_tab=False,
    )


def _stats(*texts: str) -> DocStats:
    return DocStats(paragraphs=[_ps(i, t) for i, t in enumerate(texts)])


def test_no_appendices_no_violations() -> None:
    stats = _stats("Введение", "Глава 1", "Заключение")
    assert validate_appendices([], stats, set()) == []


def test_valid_appendix_sequence_no_violations() -> None:
    stats = _stats(
        "Введение",
        "В приложении А приведены результаты.",
        "В приложении Б показана схема.",
        "Заключение",
        "Приложение А",
        "Приложение Б",
    )
    headings = [_H(4, "Приложение А"), _H(5, "Приложение Б")]
    violations = validate_appendices(headings, stats, set())
    assert violations == []


def test_invalid_letter_excluded_by_gost() -> None:
    # Ё, З, Й, О, Ч, Ъ, Ы, Ь — запрещены ГОСТ 7.32-2017
    stats = _stats(
        "В приложении А приведены результаты.",
        "В приложении З показана схема.",
        "Приложение А",
        "Приложение З",
    )
    headings = [_H(2, "Приложение А"), _H(3, "Приложение З")]
    violations = validate_appendices(headings, stats, set())
    invalid = [v for v in violations if v.type == "appendix_letter_invalid"]
    assert len(invalid) == 1
    assert "З" in invalid[0].description


def test_letter_gap_detected() -> None:
    stats = _stats(
        "В приложении А.",
        "В приложении В.",
        "Приложение А",
        "Приложение В",
    )
    headings = [_H(2, "Приложение А"), _H(3, "Приложение В")]
    violations = validate_appendices(headings, stats, set())
    gaps = [v for v in violations if v.type == "appendix_letter_gap"]
    assert len(gaps) == 1
    assert "Б" in gaps[0].description


def test_appendix_not_referenced() -> None:
    stats = _stats(
        "Введение без упоминаний.",
        "Заключение.",
        "Приложение А",
    )
    headings = [_H(2, "Приложение А")]
    violations = validate_appendices(headings, stats, set())
    refs = [v for v in violations if v.type == "appendix_not_referenced"]
    assert len(refs) == 1


def test_appendix_order_violation() -> None:
    # B упомянут раньше A — порядок приложений должен следовать порядку упоминания
    stats = _stats(
        "Сначала упомянем приложение Б.",
        "Потом упомянем приложение А.",
        "Приложение А",
        "Приложение Б",
    )
    headings = [_H(2, "Приложение А"), _H(3, "Приложение Б")]
    violations = validate_appendices(headings, stats, set())
    order = [v for v in violations if v.type == "appendix_order_violation"]
    assert len(order) == 1
