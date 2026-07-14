"""Тесты title_page.py — определение границы титульного листа (§6.1)."""
from __future__ import annotations

from docx.enum.text import WD_ALIGN_PARAGRAPH

from services.core.vkr_core.engine.stats import DocStats, ParagraphStats
from services.core.vkr_core.engine.title_page import detect_title_page_end


def _ps(idx: int, text: str, *, centred: bool = False,
        outline_level: int | None = None, numpr_ilvl: int | None = None) -> ParagraphStats:
    return ParagraphStats(
        index=idx, text=text, stripped=text.strip(), length=len(text),
        word_count=len(text.split()),
        alignment=WD_ALIGN_PARAGRAPH.CENTER if centred else WD_ALIGN_PARAGRAPH.LEFT,
        first_line_indent_cm=None, left_indent_cm=None,
        max_font_size_pt=14.0, modal_font_size_pt=14.0, font_family="Times New Roman",
        bold_ratio=0.0, italic_ratio=0.0,
        ends_with_period=text.endswith("."), is_upper=text.isupper(),
        is_empty=not text.strip(), in_table=False, style_name="Normal",
        numbered=False, numbering_tokens=(), has_tab=False,
        outline_level=outline_level, numpr_ilvl=numpr_ilvl,
    )


_RULES = {
    "structural_elements": {
        "title_page": [],
        "task": ["ЗАДАНИЕ НА ВЫПУСКНУЮ КВАЛИФИКАЦИОННУЮ РАБОТУ"],
        "contents": ["СОДЕРЖАНИЕ"],
        "introduction": ["ВВЕДЕНИЕ"],
    }
}


def test_no_title_marker_returns_zero() -> None:
    stats = DocStats(paragraphs=[_ps(0, "Просто текст"), _ps(1, "Ещё текст")])
    assert detect_title_page_end(stats, _RULES) == 0


def test_explicit_marker_then_contents() -> None:
    stats = DocStats(paragraphs=[
        _ps(0, "Выпускная квалификационная работа"),
        _ps(1, "Иванов И. И."),
        _ps(2, "СОДЕРЖАНИЕ"),
        _ps(3, "..."),
    ])
    end = detect_title_page_end(stats, _RULES)
    assert end == 2  # граница указывает на «СОДЕРЖАНИЕ»


def test_marker_then_h1_numbered() -> None:
    stats = DocStats(paragraphs=[
        _ps(0, "Бакалаврская работа"),
        _ps(1, "1 Введение"),
        _ps(2, "Текст"),
    ])
    assert detect_title_page_end(stats, _RULES) == 1


def test_task_marker_then_h1_numbered() -> None:
    stats = DocStats(paragraphs=[
        _ps(0, "Задание на выпускную квалификационную работу"),
        _ps(1, "1 Введение"),
        _ps(2, "Текст"),
    ])
    assert detect_title_page_end(stats, _RULES) == 1


def test_marker_via_outline_level() -> None:
    # Заголовок без текстового номера, но с outline_level=0 (numPr автонумерация)
    stats = DocStats(paragraphs=[
        _ps(0, "ВКР"),
        _ps(1, "Заголовок", outline_level=0),
    ])
    assert detect_title_page_end(stats, _RULES) == 1


def test_fallback_via_centered_and_context() -> None:
    # Без явного маркера, но 4+ центрированных коротких + 2 контекстных слова
    stats = DocStats(paragraphs=[
        _ps(0, "Министерство", centred=True),
        _ps(1, "Университет", centred=True),
        _ps(2, "Факультет", centred=True),
        _ps(3, "Кафедра", centred=True),
        _ps(4, "По дисциплине"),
        _ps(5, "1 Введение"),
    ])
    end = detect_title_page_end(stats, _RULES)
    assert end == 5
