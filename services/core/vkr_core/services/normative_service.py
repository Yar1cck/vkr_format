"""Управление активной нормативной базой.

Единый источник правды для правил оформления — это БД-запись
NormativeVersion (поле rules_config). При первом старте БД сидится из
rules_v1.yaml. На последующих стартах выполняется *аддитивный* merge
YAML в БД: ключи, отсутствующие в БД, добавляются из YAML; ключи,
которые админ менял через UI, остаются в его варианте.

Так достигается единая модель: pipeline всегда читает rules из БД, а
доставка новых правил из репозитория не ломает админ-правки.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.vkr_core.config.normative_loader import load_default_rules
from services.core.vkr_core.models import NormativeVersion

_NUMBERING_MODES = {"continuous", "by_chapter"}
_PAPER_SIZES = {"A4", "A5", "Letter"}
_ORIENTATIONS = {"portrait", "landscape"}
_ALIGNMENTS = {"justify", "left", "right", "center"}
_HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")
_ALLOWED_TOP_LEVEL_KEYS = {
    "meta",
    "page_settings",
    "body_text_style",
    "heading_detection",
    "structural_elements",
    "forbidden_heading_map",
    "numbering_rules",
    "caption_style",
    "volume_limits",
    "report_templates",
    "security",
}
_ALLOWED_SECTION_KEYS = {
    "meta": {"version", "name", "effective_date", "reference"},
    "page_settings": {
        "paper",
        "margin_left_mm",
        "margin_right_mm",
        "margin_top_mm",
        "margin_bottom_mm",
        "orientation",
    },
    "body_text_style": {
        "font_name",
        "font_size_pt",
        "line_spacing",
        "font_color",
        "alignment",
        "first_line_indent_cm",
        "space_before_pt",
        "space_after_pt",
    },
    "heading_detection": {
        "max_length",
        "max_words",
        "font_jump_pt",
        "neighbour_long_threshold",
    },
    "structural_elements": {
        "title_page",
        "task",
        "contents",
        "introduction",
        "conclusion",
        "references",
        "terms",
        "appendix_regex",
    },
    "numbering_rules": {
        "figure_mode",
        "table_mode",
        "listing_mode",
        "validate_citation_sequence",
    },
    "caption_style": {"table_first_line_indent_cm"},
    "volume_limits": {"min", "max"},
    "report_templates": {"warning_toc", "warning_toc_lo_failed"},
    "security": {"retention_days"},
}
_NON_BACHELOR_TITLE_MARKERS = {
    "\u043c\u0430\u0433\u0438\u0441\u0442\u0435\u0440\u0441\u043a\u0430\u044f \u0434\u0438\u0441\u0441\u0435\u0440\u0442\u0430\u0446\u0438\u044f",
    "\u043c\u0430\u0433\u0438\u0441\u0442\u0435\u0440\u0441\u043a\u0430\u044f \u0440\u0430\u0431\u043e\u0442\u0430",
    "\u0432\u043a\u0440 \u043c\u0430\u0433\u0438\u0441\u0442\u0440\u0430",
}


def _is_blank(value: object) -> bool:
    """True, если значение функционально пусто: None, пустая строка,
    пустой список, пустой словарь.

    Нужно для merge: блёклые значения в БД (null / "") — почти всегда
    результат «админ нажал Save с пустым полем», а не осознанное «сделай
    null». YAML в таких случаях должен победить, иначе тихо ломается
    pipeline (классический кейс — "оглавление": null → отбрасывается до
    замены).
    """
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _merge_lists(current: list, defaults: list) -> tuple[list, bool]:
    """Объединяет два списка с дедупликацией, сохраняя порядок current.

    Используется для алиасов (structural_elements.contents и т.п.):
    если админ удалил один синоним, а в YAML добавили новый — оба
    оказываются в итоговом списке. Иначе YAML-обновления молча теряются.
    """
    out = list(current)
    seen = {item for item in current if isinstance(item, (str, int, float, bool))}
    changed = False
    for item in defaults:
        if isinstance(item, (str, int, float, bool)):
            if item not in seen:
                out.append(item)
                seen.add(item)
                changed = True
        elif item not in current:
            out.append(item)
            changed = True
    return out, changed


def _merge_overlay(base: dict, defaults: dict) -> tuple[dict, bool]:
    """Deep-merge defaults в base со следующими правилами:

      1. Ключ есть в defaults, но отсутствует в base — добавляется из defaults.
      2. Ключ есть в обоих, но в base пустой (_is_blank) — берётся defaults.
      3. Ключ есть в обоих, в base непустое скалярное значение — оставляется.
      4. Оба значения — словари — рекурсивно мержатся по тем же правилам.
      5. Оба значения — списки — объединяются с дедупликацией. Это
         предотвращает потерю новых алиасов, добавленных в YAML после
         первого сидера.

    Так админ может **сознательно** переопределить значение через UI
    (вписать новое имя, новую замену) — оно сохранится. Но если поле было
    случайно очищено или ключ просто не появился в админ-форме, YAML-
    значение восстанавливается. Это устраняет ситуацию, когда в БД лежит
    null, а pipeline молча работает не так, как ожидает админ.

    Возвращает (merged, changed): итоговый словарь и флаг изменений (нужен,
    чтобы избежать ненужного UPDATE в БД).
    """
    merged: dict = dict(base)
    changed = False
    for key, default_value in defaults.items():
        if key not in merged:
            merged[key] = default_value
            changed = True
            continue
        current = merged[key]
        if isinstance(current, dict) and isinstance(default_value, dict):
            sub_merged, sub_changed = _merge_overlay(current, default_value)
            if sub_changed:
                merged[key] = sub_merged
                changed = True
            continue
        if isinstance(current, list) and isinstance(default_value, list):
            sub_list, sub_changed = _merge_lists(current, default_value)
            if sub_changed:
                merged[key] = sub_list
                changed = True
            continue
        if _is_blank(current) and not _is_blank(default_value):
            merged[key] = default_value
            changed = True
    return merged, changed


def _norm_text(value: object) -> str:
    return " ".join(str(value).strip().lower().split())


def _dict(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{path} должен быть словарём")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} должен быть непустой строкой")
    return value.strip()


def _number(value: Any, path: str, *, min_value: float | None = None) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} должен быть числом")
    if min_value is not None and value < min_value:
        raise ValueError(f"{path} должен быть >= {min_value:g}")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} должен быть списком строк")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path} должен содержать только непустые строки")
        cleaned.append(item.strip())
    return cleaned


def _reject_unknown_keys(mapping: dict, allowed: set[str], path: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ValueError(f"{path} содержит неподдерживаемые ключи: {', '.join(unknown)}")


def _normalize_rules_shape(
    rules_config: dict,
    *,
    defaults: dict | None = None,
    force_defaults: bool = False,
) -> dict:
    """Приводит старые/скрытые поля к текущей рабочей форме.

    Это не заменяет всю админскую конфигурацию: осознанные правки сохраняются.
    Принудительно обновляем defaults только при переходе со старой версии
    конфигурации, где UI показывал значения, не совпадавшие с поведением кода.
    """
    out = deepcopy(rules_config)

    if defaults and force_defaults:
        out["meta"] = deepcopy(defaults.get("meta", {}))

    structural = out.get("structural_elements")
    if isinstance(structural, dict):
        title_page = structural.get("title_page")
        if isinstance(title_page, list):
            structural["title_page"] = [
                item for item in title_page
                if _norm_text(item) not in _NON_BACHELOR_TITLE_MARKERS
            ]

    numbering = out.setdefault("numbering_rules", {})
    if isinstance(numbering, dict):
        numbering.pop("formula_mode", None)
        if force_defaults:
            default_numbering = (defaults or {}).get("numbering_rules", {})
            numbering["figure_mode"] = default_numbering.get("figure_mode", "by_chapter")
            numbering["table_mode"] = default_numbering.get("table_mode", "by_chapter")
            numbering["listing_mode"] = default_numbering.get("listing_mode", "by_chapter")
        numbering.setdefault("figure_mode", "by_chapter")
        numbering.setdefault("table_mode", "by_chapter")
        numbering.setdefault("listing_mode", "by_chapter")
        numbering.setdefault("validate_citation_sequence", True)

    volume = out.get("volume_limits")
    if isinstance(volume, dict):
        if isinstance(volume.get("bachelor"), dict):
            bachelor = volume["bachelor"]
            out["volume_limits"] = {
                "min": bachelor.get("min", 40),
                "max": bachelor.get("max", 120),
            }
        else:
            out["volume_limits"] = {
                "min": volume.get("min", 40),
                "max": volume.get("max", 120),
            }

    return out


def _validate_and_normalize_rules(rules_config: Any) -> dict:
    if not isinstance(rules_config, dict):
        raise ValueError("rules_config должен быть словарём")

    out = _normalize_rules_shape(rules_config)
    _reject_unknown_keys(out, _ALLOWED_TOP_LEVEL_KEYS, "rules_config")

    meta = _dict(out.get("meta"), "meta")
    _reject_unknown_keys(meta, _ALLOWED_SECTION_KEYS["meta"], "meta")
    for key in ("version", "name", "effective_date", "reference"):
        meta[key] = _string(meta.get(key), f"meta.{key}")
    try:
        date.fromisoformat(meta["effective_date"])
    except ValueError:
        raise ValueError("meta.effective_date должен быть датой YYYY-MM-DD")

    page = _dict(out.get("page_settings"), "page_settings")
    _reject_unknown_keys(page, _ALLOWED_SECTION_KEYS["page_settings"], "page_settings")
    if page.get("paper") not in _PAPER_SIZES:
        raise ValueError("page_settings.paper должен быть A4, A5 или Letter")
    if page.get("orientation") not in _ORIENTATIONS:
        raise ValueError("page_settings.orientation должен быть portrait или landscape")
    for key in ("margin_left_mm", "margin_right_mm", "margin_top_mm", "margin_bottom_mm"):
        page[key] = _number(page.get(key), f"page_settings.{key}", min_value=0)

    body = _dict(out.get("body_text_style"), "body_text_style")
    _reject_unknown_keys(body, _ALLOWED_SECTION_KEYS["body_text_style"], "body_text_style")
    body["font_name"] = _string(body.get("font_name"), "body_text_style.font_name")
    body["font_size_pt"] = _number(body.get("font_size_pt"), "body_text_style.font_size_pt", min_value=1)
    body["line_spacing"] = _number(body.get("line_spacing"), "body_text_style.line_spacing", min_value=0.1)
    body["first_line_indent_cm"] = _number(body.get("first_line_indent_cm"), "body_text_style.first_line_indent_cm", min_value=0)
    body["space_before_pt"] = _number(body.get("space_before_pt"), "body_text_style.space_before_pt", min_value=0)
    body["space_after_pt"] = _number(body.get("space_after_pt"), "body_text_style.space_after_pt", min_value=0)
    body["font_color"] = _string(body.get("font_color"), "body_text_style.font_color")
    if not _HEX_COLOR_RE.match(body["font_color"]):
        raise ValueError("body_text_style.font_color должен быть HEX RGB без #, например 000000")
    if body.get("alignment") not in _ALIGNMENTS:
        raise ValueError("body_text_style.alignment должен быть justify, left, right или center")

    heading = _dict(out.get("heading_detection"), "heading_detection")
    _reject_unknown_keys(heading, _ALLOWED_SECTION_KEYS["heading_detection"], "heading_detection")
    heading["max_length"] = _number(heading.get("max_length"), "heading_detection.max_length", min_value=1)
    heading["max_words"] = _number(heading.get("max_words"), "heading_detection.max_words", min_value=1)
    heading["font_jump_pt"] = _number(heading.get("font_jump_pt"), "heading_detection.font_jump_pt", min_value=0.1)
    heading["neighbour_long_threshold"] = _number(
        heading.get("neighbour_long_threshold"),
        "heading_detection.neighbour_long_threshold",
        min_value=1,
    )

    structural = _dict(out.get("structural_elements"), "structural_elements")
    _reject_unknown_keys(structural, _ALLOWED_SECTION_KEYS["structural_elements"], "structural_elements")
    for key in ("title_page", "task", "contents", "introduction", "conclusion", "references", "terms"):
        structural[key] = _string_list(structural.get(key, []), f"structural_elements.{key}")
    appendix_regex = _string(structural.get("appendix_regex"), "structural_elements.appendix_regex")
    try:
        re.compile(appendix_regex)
    except re.error as exc:
        raise ValueError(f"structural_elements.appendix_regex невалиден: {exc}")
    structural["appendix_regex"] = appendix_regex

    fmap = out.get("forbidden_heading_map")
    if fmap is not None:
        if not isinstance(fmap, dict):
            raise ValueError("forbidden_heading_map должен быть словарём")
        cleaned: dict[str, str | None] = {}
        for key, value in fmap.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                cleaned[key.strip()] = None
            elif isinstance(value, str):
                cleaned[key.strip()] = value.strip()
            else:
                raise ValueError(f"forbidden_heading_map[{key!r}]: значение должно быть строкой или null")
        out["forbidden_heading_map"] = cleaned
    else:
        out["forbidden_heading_map"] = {}

    numbering = _dict(out.get("numbering_rules"), "numbering_rules")
    _reject_unknown_keys(numbering, _ALLOWED_SECTION_KEYS["numbering_rules"], "numbering_rules")
    for key in ("figure_mode", "table_mode", "listing_mode"):
        if numbering.get(key) not in _NUMBERING_MODES:
            raise ValueError(f"numbering_rules.{key} должен быть continuous или by_chapter")
    if not isinstance(numbering.get("validate_citation_sequence"), bool):
        raise ValueError("numbering_rules.validate_citation_sequence должен быть boolean")

    caption = _dict(out.get("caption_style"), "caption_style")
    _reject_unknown_keys(caption, _ALLOWED_SECTION_KEYS["caption_style"], "caption_style")
    caption["table_first_line_indent_cm"] = _number(
        caption.get("table_first_line_indent_cm"),
        "caption_style.table_first_line_indent_cm",
        min_value=0,
    )

    volume = _dict(out.get("volume_limits"), "volume_limits")
    _reject_unknown_keys(volume, _ALLOWED_SECTION_KEYS["volume_limits"], "volume_limits")
    volume["min"] = _number(volume.get("min"), "volume_limits.min", min_value=0)
    volume["max"] = _number(volume.get("max"), "volume_limits.max", min_value=0)
    if volume["min"] > volume["max"]:
        raise ValueError("volume_limits.min должен быть <= volume_limits.max")

    reports = _dict(out.get("report_templates"), "report_templates")
    _reject_unknown_keys(reports, _ALLOWED_SECTION_KEYS["report_templates"], "report_templates")
    reports["warning_toc"] = _string(reports.get("warning_toc"), "report_templates.warning_toc")
    if "warning_toc_lo_failed" in reports and reports["warning_toc_lo_failed"] is not None:
        reports["warning_toc_lo_failed"] = _string(
            reports["warning_toc_lo_failed"],
            "report_templates.warning_toc_lo_failed",
        )

    security = _dict(out.get("security"), "security")
    _reject_unknown_keys(security, _ALLOWED_SECTION_KEYS["security"], "security")
    security["retention_days"] = int(
        _number(security.get("retention_days"), "security.retention_days", min_value=1)
    )

    return out


async def ensure_default_normative(db: AsyncSession) -> NormativeVersion:
    """Гарантирует наличие активной нормативной базы в БД.

    Если в БД нет активной версии — создаёт из YAML.
    Если есть — выполняет аддитивный merge YAML в её rules_config: новые
    ключи из YAML появляются в БД, а админ-правки сохраняются.

    Имя и дата активной версии синхронизируются с meta внутри итогового
    rules_config, чтобы список нормативных баз показывал те же данные,
    которые админ видит и редактирует в конфигурации.
    """
    yaml_rules = _validate_and_normalize_rules(load_default_rules())
    meta = yaml_rules.get("meta") or {}
    yaml_name: str = meta.get("name") or "МИИГАиК"

    current = await db.scalar(select(NormativeVersion).where(NormativeVersion.is_active.is_(True)))
    if current is not None:
        current_meta_version = ((current.rules_config or {}).get("meta") or {}).get("version")
        force_defaults = bool(meta.get("version")) and current_meta_version != meta.get("version")
        merged, changed = _merge_overlay(current.rules_config or {}, yaml_rules)
        normalized = _normalize_rules_shape(
            merged,
            defaults=yaml_rules,
            force_defaults=force_defaults,
        )
        if normalized != merged:
            merged = normalized
            changed = True
        merged_meta = merged.get("meta") or {}
        merged_name = merged_meta.get("name") or yaml_name
        merged_effective_date = date.fromisoformat(
            merged_meta.get("effective_date", meta.get("effective_date", date.today().isoformat()))
        )
        dirty = False
        if changed:
            current.rules_config = merged
            dirty = True
        if current.name != merged_name:
            current.name = merged_name
            dirty = True
        if current.effective_date != merged_effective_date:
            current.effective_date = merged_effective_date
            dirty = True
        if dirty:
            await db.commit()
            await db.refresh(current)
        return current

    normative = NormativeVersion(
        name=yaml_name,
        effective_date=date.fromisoformat(meta.get("effective_date", date.today().isoformat())),
        rules_config=yaml_rules,
        is_active=True,
    )
    db.add(normative)
    await db.commit()
    await db.refresh(normative)
    return normative


async def list_normative_versions(db: AsyncSession) -> list[NormativeVersion]:
    result = await db.execute(select(NormativeVersion).order_by(NormativeVersion.created_at.desc()))
    return list(result.scalars().all())


async def get_normative_by_id(version_id: UUID, db: AsyncSession) -> NormativeVersion | None:
    return await db.get(NormativeVersion, version_id)


async def get_active_normative(db: AsyncSession) -> NormativeVersion:
    current = await db.scalar(select(NormativeVersion).where(NormativeVersion.is_active.is_(True)))
    if not current:
        return await ensure_default_normative(db)
    return current


def _validate_rules(rules_config: Any) -> dict:
    """Валидирует и нормализует rules_config перед записью в БД."""
    return _validate_and_normalize_rules(rules_config)


async def update_normative_rules(version: NormativeVersion, rules_config: dict, db: AsyncSession) -> NormativeVersion:
    normalized = _validate_rules(rules_config)
    meta = normalized.get("meta") or {}
    version.rules_config = normalized
    version.name = meta.get("name") or version.name
    version.effective_date = date.fromisoformat(meta["effective_date"])
    await db.commit()
    await db.refresh(version)
    return version
