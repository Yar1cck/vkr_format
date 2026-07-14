"""Регресс: citation_without_source якорится на РЕАЛЬНЫЙ токен из текста.

Число может прийти из диапазона/группы («[45-50]»), литерального «[50]»
в документе нет — тогда подсветка/скролл ничего не находили. Якорь
(original_text) должен быть фактической подстрокой документа.
"""
from __future__ import annotations

from types import SimpleNamespace

from services.core.vkr_core.engine.bibliography import BibEntry, validate_bibliography
from services.core.vkr_core.engine.citations import collect_citations
from services.core.vkr_core.engine.stats import DocStats


def _stats(texts: list[str]) -> DocStats:
    s = DocStats()
    s.paragraphs = [
        SimpleNamespace(index=i, is_empty=not t.strip(), stripped=t)
        for i, t in enumerate(texts)
    ]
    return s


def test_citation_without_source_anchors_to_real_token() -> None:
    stats = _stats([
        "Вводный абзац без ссылок.",
        "Результат подтверждён в работах [45-50] по теме.",
    ])
    usages = collect_citations(stats, skip_indexes=set())
    # Есть запись только №1 — значит 45..50 окажутся без источника.
    entries = [BibEntry(paragraph_index=99, number=1, text="Иванов И. 2020. 10 с.")]

    violations = validate_bibliography(entries, usages, bounds=(0, 1))

    without = [v for v in violations if v.type == "citation_without_source"]
    assert without, "должны быть citation_without_source для 45..50"
    v50 = next(v for v in without if "[50]" in v.description)
    # Якорь — реальный токен из текста, не синтезированный "[50]".
    assert v50.original_text == "[45-50]"
    assert v50.paragraph_index == 1


def test_endash_range_is_recognised_and_anchored() -> None:
    stats = _stats([
        "Текст.",
        "См. работы [45–50] по теме нормоконтроля.",  # en-dash
    ])
    usages = collect_citations(stats, skip_indexes=set())
    assert 50 in {n for u in usages for n in u.numbers}
    entries = [BibEntry(paragraph_index=9, number=1, text="Сидоров. 2019. 9 с.")]
    violations = validate_bibliography(entries, usages, bounds=(0, 1))
    v50 = next(
        v for v in violations
        if v.type == "citation_without_source" and "[50]" in v.description
    )
    assert v50.original_text == "[45–50]"
    assert v50.paragraph_index == 1


def test_standalone_citation_anchor_is_plain() -> None:
    stats = _stats([
        "Текст.",
        "Здесь одиночная ссылка [7] на источник.",
    ])
    usages = collect_citations(stats, skip_indexes=set())
    entries = [BibEntry(paragraph_index=9, number=1, text="Петров П. 2021. 5 с.")]

    violations = validate_bibliography(entries, usages, bounds=(0, 1))
    v7 = next(
        v for v in violations
        if v.type == "citation_without_source" and "[7]" in v.description
    )
    assert v7.original_text == "[7]"
    assert v7.paragraph_index == 1
