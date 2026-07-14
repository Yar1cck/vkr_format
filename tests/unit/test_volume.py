"""Тесты volume.py — оценка объёма и проверка лимитов (§7.8)."""
from __future__ import annotations

from services.core.vkr_core.engine.stats import DocStats, ParagraphStats
from services.core.vkr_core.engine.volume import (
    CHARS_PER_PAGE,
    estimate_pages,
    validate_volume,
)


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


def test_estimate_pages_uses_calibration_constant() -> None:
    block = "А" * (CHARS_PER_PAGE * 5)
    pages = estimate_pages(_stats(block), title_page_indexes=set())
    assert pages == 5


def test_estimate_pages_skips_title_page() -> None:
    title = "Т" * CHARS_PER_PAGE
    body = "Б" * (CHARS_PER_PAGE * 3)
    pages = estimate_pages(_stats(title, body), title_page_indexes={0})
    assert pages == 3


def test_estimate_pages_floor_is_one() -> None:
    assert estimate_pages(_stats("короткий"), set()) == 1


def test_validate_volume_below_minimum() -> None:
    rules = {"volume_limits": {"min": 60, "max": 120}}
    v = validate_volume(50, rules)
    assert len(v) == 1
    assert v[0].type == "volume_below_minimum"
    assert "бакалаврской" in v[0].description


def test_validate_volume_above_maximum() -> None:
    rules = {"volume_limits": {"min": 80, "max": 100}}
    v = validate_volume(150, rules)
    assert len(v) == 1
    assert v[0].type == "volume_above_maximum"
    assert "бакалаврской" in v[0].description


def test_validate_volume_in_range_no_violations() -> None:
    rules = {"volume_limits": {"min": 60, "max": 120}}
    assert validate_volume(80, rules) == []


def test_validate_volume_flat_format() -> None:
    rules = {"volume_limits": {"min": 60, "max": 120}}
    assert validate_volume(50, rules)[0].type == "volume_below_minimum"
    assert validate_volume(150, rules)[0].type == "volume_above_maximum"
    assert validate_volume(80, rules) == []


def test_validate_volume_no_limits_no_violations() -> None:
    assert validate_volume(50, {}) == []
