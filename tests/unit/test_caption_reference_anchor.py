"""Регресс: ссылка на несуществующий рисунок/таблицу якорится на текст.

figure_reference_missing / table_reference_missing раньше не имели ни
paragraph_index, ни original_text — было непонятно, где искать. Теперь
якорь — реальная подстрока («рисунок 9», «табл. 8») первого упоминания.
"""
from __future__ import annotations

from types import SimpleNamespace

from services.core.vkr_core.engine.captions import validate_references
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import SEVERITY_INFO


def _stats(texts: list[str]) -> DocStats:
    s = DocStats()
    s.paragraphs = [
        SimpleNamespace(index=i, is_empty=not t.strip(), stripped=t)
        for i, t in enumerate(texts)
    ]
    return s


def test_missing_figure_reference_is_anchored() -> None:
    stats = _stats([
        "Вводный абзац.",
        "Как показано на рисунке 9, динамика растёт.",
    ])
    violations = validate_references(stats, figures=[], tables=[], skip_indexes=set())
    fr = next(v for v in violations if v.type == "figure_reference_missing")
    assert fr.paragraph_index == 1
    assert "рисунке 9" in (fr.original_text or "")


def test_missing_table_reference_is_anchored() -> None:
    stats = _stats([
        "Текст.",
        "Данные приведены в табл. 8 ниже.",
    ])
    violations = validate_references(stats, figures=[], tables=[], skip_indexes=set())
    tr = next(v for v in violations if v.type == "table_reference_missing")
    assert tr.paragraph_index == 1
    assert tr.original_text and "8" in tr.original_text
    assert tr.severity == SEVERITY_INFO
    assert "Совет:" in tr.description
