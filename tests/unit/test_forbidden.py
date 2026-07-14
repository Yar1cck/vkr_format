"""Тесты forbidden.py — запрещённые заголовки и канонизация (§7.4)."""
from __future__ import annotations

from dataclasses import dataclass

from services.core.vkr_core.engine.forbidden import (
    check_forbidden,
    check_section_titles,
)


@dataclass
class _H:
    paragraph_index: int
    text: str
    title_only: str = ""
    level: int = 1


def test_forbidden_with_replacement_auto_fixed() -> None:
    rules = {"forbidden_heading_map": {"оглавление": "СОДЕРЖАНИЕ"}}
    violations = check_forbidden([_H(0, "ОГЛАВЛЕНИЕ", title_only="ОГЛАВЛЕНИЕ")], rules)
    assert len(violations) == 1
    v = violations[0]
    assert v.type == "forbidden_heading"
    assert v.fixed_text == "СОДЕРЖАНИЕ"
    assert v.status.value == "auto_fixed"


def test_forbidden_without_replacement_manual_required() -> None:
    rules = {"forbidden_heading_map": {"глава первая": None}}
    violations = check_forbidden([_H(0, "Глава первая", title_only="Глава первая")], rules)
    assert len(violations) == 1
    assert violations[0].status.value == "manual_required"
    assert violations[0].fixed_text is None


def test_forbidden_case_insensitive_match() -> None:
    rules = {"forbidden_heading_map": {"оглавление": "СОДЕРЖАНИЕ"}}
    h = _H(0, "  Оглавление  ", title_only="оглавление")
    assert len(check_forbidden([h], rules)) == 1


def test_forbidden_no_match_no_violations() -> None:
    rules = {"forbidden_heading_map": {"оглавление": "СОДЕРЖАНИЕ"}}
    assert check_forbidden([_H(0, "Введение", title_only="Введение")], rules) == []


def test_forbidden_empty_rules() -> None:
    assert check_forbidden([_H(0, "Любой", title_only="Любой")], {}) == []


def test_section_title_canonicalization() -> None:
    rules = {
        "structural_elements": {
            "references": [
                "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
                "Список использованной литературы",
                "Литература",
            ]
        }
    }
    h = _H(0, "Список использованной литературы", title_only="Список использованной литературы")
    violations = check_section_titles([h], rules)
    assert len(violations) == 1
    assert violations[0].type == "heading_rename"
    assert violations[0].fixed_text == "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"


def test_canonical_already_no_violation() -> None:
    rules = {
        "structural_elements": {
            "references": ["СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", "Литература"]
        }
    }
    h = _H(0, "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", title_only="СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")
    assert check_section_titles([h], rules) == []


def test_canonicalization_skipped_when_forbidden_handles_it() -> None:
    # Если для алиаса уже есть запись в forbidden_heading_map —
    # check_section_titles не должен дублировать нарушение.
    rules = {
        "forbidden_heading_map": {"литература": "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"},
        "structural_elements": {
            "references": ["СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", "Литература"]
        }
    }
    h = _H(0, "Литература", title_only="Литература")
    assert check_section_titles([h], rules) == []
