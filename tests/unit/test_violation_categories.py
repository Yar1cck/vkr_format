from __future__ import annotations

import ast
from pathlib import Path

from services.core.vkr_core.services.document_service import _violation_category


def _engine_violation_types() -> set[str]:
    types: set[str] = set()
    engine_dir = Path("services/core/vkr_core/engine")
    for path in engine_dir.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.keyword)
                and node.arg == "type"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                types.add(node.value.value)
    return types


def test_known_engine_violation_types_have_specific_categories() -> None:
    uncategorized = sorted(
        vtype for vtype in _engine_violation_types()
        if _violation_category(vtype) == "Прочее"
    )
    assert uncategorized == []


def test_unknown_violation_type_falls_back_to_other() -> None:
    assert _violation_category("new_unknown_violation") == "Прочее"


def test_violation_category_examples() -> None:
    assert _violation_category("missing_structural_section") == "Структура"
    assert _violation_category("figure_reference_missing") == "Рисунки и таблицы"
    assert _violation_category("formula_without_explanation") == "Формулы"
    assert _violation_category("appendix_letter_gap") == "Приложения"
    assert _violation_category("volume_above_maximum") == "Объём"
    assert _violation_category("paragraph_spacing") == "Шрифт и абзацы"
