"""Регресс: «Продолжение таблицы N» не считается ссылкой на таблицу.

Длинную таблицу режут и над страницей-продолжением ставят авто-надпись
«Продолжение таблицы 2». Раньше validate_references принимал её за
упоминание таблицы 2 в тексте → table_not_referenced для разрезанной
таблицы не выдавался (хотя в тексте на неё реально не ссылаются).
"""
from __future__ import annotations

from types import SimpleNamespace

from services.core.vkr_core.engine.captions import Caption, validate_references
from services.core.vkr_core.engine.stats import DocStats
from services.core.vkr_core.engine.violations import SEVERITY_INFO


def _stats(texts: list[str]) -> DocStats:
    s = DocStats()
    s.paragraphs = [
        SimpleNamespace(index=i, is_empty=not t.strip(), stripped=t)
        for i, t in enumerate(texts)
    ]
    return s


def _tbl(num: int, para_idx: int) -> Caption:
    return Caption(
        paragraph_index=para_idx,
        original_number=str(num),
        new_number=num,
        title=f"Таблица {num} — тест",
        kind="table",
    )


def test_continuation_label_is_not_a_reference() -> None:
    stats = _stats([
        "Текст без ссылок на таблицы.",
        "Таблица 1 — Первая",
        "Таблица 2 — Вторая (длинная)",
        # авто-надпись страницы-продолжения разрезанной таблицы 2:
        "Продолжение таблицы 2",
        "Ещё абзац тела без ссылок.",
    ])
    tables = [_tbl(1, 1), _tbl(2, 2)]
    violations = validate_references(stats, figures=[], tables=tables, skip_indexes=set())

    not_ref = {
        v.original_text for v in violations if v.type == "table_not_referenced"
    }
    # Обе таблицы нигде не упомянуты — обе должны быть помечены.
    assert any("Таблица 1" in (t or "") for t in not_ref), not_ref
    assert any("Таблица 2" in (t or "") for t in not_ref), not_ref
    assert all(v.severity == SEVERITY_INFO for v in violations if v.type == "table_not_referenced")
    assert all("Совет:" in v.description for v in violations if v.type == "table_not_referenced")
    # «Продолжение таблицы 2» не должно создавать table_reference_missing.
    assert not [v for v in violations if v.type == "table_reference_missing"]


def test_real_reference_still_counts() -> None:
    stats = _stats([
        "В таблице 2 приведены данные.",  # настоящая ссылка
        "Таблица 2 — Вторая",
        "Продолжение таблицы 2",
    ])
    tables = [_tbl(2, 1)]
    violations = validate_references(stats, figures=[], tables=tables, skip_indexes=set())
    # Есть реальная ссылка → таблица 2 НЕ помечается как неупомянутая.
    assert not [v for v in violations if v.type == "table_not_referenced"]
