"""Тесты structure.py — обязательные структурные разделы (§7.7)."""
from __future__ import annotations

from dataclasses import dataclass

from services.core.vkr_core.engine.stats import DocStats, ParagraphStats
from services.core.vkr_core.engine.structure import validate_structure


@dataclass
class _H:
    paragraph_index: int
    text: str
    title_only: str = ""
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


_RULES = {
    "structural_elements": {
        "contents":     ["СОДЕРЖАНИЕ"],
        "introduction": ["ВВЕДЕНИЕ"],
        "conclusion":   ["ЗАКЛЮЧЕНИЕ"],
        "references":   ["СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"],
        "terms":        ["ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ"],
    }
}


def test_all_required_sections_no_violations() -> None:
    stats = _stats(
        "СОДЕРЖАНИЕ", "...", "ВВЕДЕНИЕ", "...",
        "Глава 1", "...", "ЗАКЛЮЧЕНИЕ", "...",
        "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", "...",
    )
    headings = [_H(0, "СОДЕРЖАНИЕ"), _H(2, "ВВЕДЕНИЕ"), _H(6, "ЗАКЛЮЧЕНИЕ"),
                _H(8, "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")]
    assert validate_structure(stats, _RULES, headings, set()) == []


def test_missing_contents_reported() -> None:
    stats = _stats("ВВЕДЕНИЕ", "...", "ЗАКЛЮЧЕНИЕ", "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")
    headings = [_H(0, "ВВЕДЕНИЕ"), _H(2, "ЗАКЛЮЧЕНИЕ"), _H(3, "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")]
    violations = validate_structure(stats, _RULES, headings, set())
    missing = [v for v in violations if v.type == "missing_structural_section"]
    assert len(missing) == 1
    assert "Содержание" in missing[0].description


def test_missing_references_not_duplicated() -> None:
    # bibliography.py отвечает за «нет списка источников», structure.py — нет.
    stats = _stats("СОДЕРЖАНИЕ", "ВВЕДЕНИЕ", "ЗАКЛЮЧЕНИЕ")
    headings = [_H(0, "СОДЕРЖАНИЕ"), _H(1, "ВВЕДЕНИЕ"), _H(2, "ЗАКЛЮЧЕНИЕ")]
    violations = validate_structure(stats, _RULES, headings, set())
    assert not any(
        v.type == "missing_structural_section" and "источников" in v.description
        for v in violations
    )


def test_order_violation_introduction_after_conclusion() -> None:
    stats = _stats("СОДЕРЖАНИЕ", "ЗАКЛЮЧЕНИЕ", "ВВЕДЕНИЕ", "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")
    headings = []
    violations = validate_structure(stats, _RULES, headings, set())
    order = [v for v in violations if v.type == "structural_order_violation"]
    assert order
    assert any("Введение" in v.description for v in order)


def test_terms_must_be_before_introduction() -> None:
    # Термины и определения после Введения — порядок нарушен
    stats = _stats(
        "СОДЕРЖАНИЕ", "ВВЕДЕНИЕ", "ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ",
        "ЗАКЛЮЧЕНИЕ", "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
    )
    violations = validate_structure(stats, _RULES, [], set())
    order = [v for v in violations if v.type == "structural_order_violation"]
    assert any("Термины" in v.description for v in order)


def test_section_found_in_sdt_text() -> None:
    # «СОДЕРЖАНИЕ» лежит внутри SDT — невидимо в paragraphs, но известно через sdt_paragraph_texts
    stats = DocStats(
        paragraphs=[_ps(0, "ВВЕДЕНИЕ"), _ps(1, "ЗАКЛЮЧЕНИЕ"),
                    _ps(2, "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")],
        sdt_paragraph_texts=frozenset({"содержание"}),
    )
    violations = validate_structure(stats, _RULES, [], set())
    missing = [v for v in violations if v.type == "missing_structural_section"
               and "Содержание" in v.description]
    assert not missing
