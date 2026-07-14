"""Реестр запрещённых заголовков (ТЗ §7.4).

Реестр приходит ТОЛЬКО из нормативных правил (rules.forbidden_heading_map).
Никаких хардкод-defaults в коде нет — единственный источник правды это
нормативная база (БД-копия NormativeVersion.rules_config), которая при
первом запуске сидится из rules_v1.yaml и потом редактируется через
админку.

Формат записи в forbidden_heading_map:
    {ключ_в_нижнем_регистре: замена | None}

  • замена — строка, на которую заголовок переименовывается автоматически
    (пример: "оглавление" → "СОДЕРЖАНИЕ")
  • None — заголовок запрещён без замены, требует ручной правки
"""

from __future__ import annotations

from services.core.vkr_core.engine.detection import HeadingCandidate
from services.core.vkr_core.engine.violations import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    PipelineViolation,
)
from services.core.vkr_core.models.enums import ViolationStatus


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _registry(rules: dict) -> dict[str, str | None]:
    """Возвращает forbidden_heading_map из rules с нормализованными ключами."""
    raw = rules.get("forbidden_heading_map") or {}
    return {_norm(k): v for k, v in raw.items()}


def check_forbidden(
    headings: list[HeadingCandidate],
    rules: dict,
) -> list[PipelineViolation]:
    registry = _registry(rules)
    violations: list[PipelineViolation] = []
    for candidate in headings:
        normalized = _norm(candidate.title_only or candidate.text)
        if normalized not in registry:
            continue
        replacement = registry[normalized]
        if replacement:
            description = "Приведён к нормативному названию (см. Было/Стало)."
            status = ViolationStatus.auto_fixed
        else:
            description = "Запрещён нормативной базой — удалите или переименуйте вручную."
            status = ViolationStatus.manual_required
        violations.append(
            PipelineViolation(
                type="forbidden_heading",
                rule_reference="п. 6.9",
                description=description,
                status=status,
                severity=SEVERITY_CRITICAL,
                paragraph_index=candidate.paragraph_index,
                section_title=candidate.text,
                original_text=candidate.text,
                fixed_text=replacement,
            )
        )
    return violations


# Структурные разделы, у которых название должно быть каноническим. Канон —
# ПЕРВЫЙ алиас в rules.structural_elements[key], в верхнем регистре (как
# принято для замен в forbidden_heading_map: «оглавление» → «СОДЕРЖАНИЕ»).
_CANONICAL_SECTION_KEYS = (
    "contents", "introduction", "conclusion", "references", "terms",
)


def _canonical_section_map(rules: dict) -> dict[str, str]:
    """{нормализованный не-канонический алиас: КАНОНИЧЕСКОЕ_ИМЯ}.

    Канонический алиас (первый в списке) в карту НЕ попадает — заголовок,
    уже названный канонически, не трогаем.
    """
    structural = rules.get("structural_elements", {})
    mapping: dict[str, str] = {}
    for key in _CANONICAL_SECTION_KEYS:
        aliases = [a for a in structural.get(key, []) if a and a.strip()]
        if len(aliases) < 2:
            continue
        canonical = aliases[0].strip().upper()
        canonical_norm = _norm(aliases[0])
        for alias in aliases[1:]:
            alias_norm = _norm(alias)
            if alias_norm and alias_norm != canonical_norm:
                mapping[alias_norm] = canonical
    return mapping


def check_section_titles(
    headings: list[HeadingCandidate],
    rules: dict,
) -> list[PipelineViolation]:
    """Проверяет, что заголовки структурных разделов названы канонически.

    Заголовок-синоним («Список использованной литературы» вместо
    «Список использованных источников») переименовывается автоматически в
    каноническую форму. Источник синонимов и канона — нормативная база
    (structural_elements), редактируемая в админке.
    """
    canonical = _canonical_section_map(rules)
    forbidden = _registry(rules)
    violations: list[PipelineViolation] = []
    for candidate in headings:
        normalized = _norm(candidate.title_only or candidate.text)
        if normalized not in canonical:
            continue
        # Если этот же заголовок уже разбирает forbidden_heading_map —
        # не дублируем нарушение.
        if normalized in forbidden:
            continue
        replacement = canonical[normalized]
        violations.append(
            PipelineViolation(
                type="heading_rename",
                rule_reference="п. 6.9",
                description="Приведён к канонической форме по нормативной базе (см. Было/Стало).",
                status=ViolationStatus.auto_fixed,
                severity=SEVERITY_WARNING,
                paragraph_index=candidate.paragraph_index,
                section_title=candidate.text,
                original_text=candidate.text,
                fixed_text=replacement,
            )
        )
    return violations


def apply_section_title_canonicalization(
    doc, headings: list[HeadingCandidate], rules: dict
) -> None:
    """Переписывает заголовки-синонимы структурных разделов в канон."""
    canonical = _canonical_section_map(rules)
    forbidden = _registry(rules)
    for candidate in headings:
        normalized = _norm(candidate.title_only or candidate.text)
        if normalized not in canonical or normalized in forbidden:
            continue
        if candidate.paragraph_index >= len(doc.paragraphs):
            continue
        paragraph = doc.paragraphs[candidate.paragraph_index]
        from services.core.vkr_core.engine.formatter import overwrite_paragraph_text
        overwrite_paragraph_text(paragraph, canonical[normalized])


def apply_forbidden_replacements(doc, headings: list[HeadingCandidate], rules: dict) -> None:
    """Переименовывает запрещённые заголовки, для которых задана замена
    (например, ОГЛАВЛЕНИЕ → СОДЕРЖАНИЕ)."""
    registry = _registry(rules)
    for candidate in headings:
        normalized = _norm(candidate.title_only or candidate.text)
        replacement = registry.get(normalized)
        if not replacement:
            continue
        if candidate.paragraph_index >= len(doc.paragraphs):
            continue
        paragraph = doc.paragraphs[candidate.paragraph_index]
        from services.core.vkr_core.engine.formatter import overwrite_paragraph_text
        overwrite_paragraph_text(paragraph, replacement)
