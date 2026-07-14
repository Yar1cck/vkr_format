from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.core.vkr_core.config.normative_loader import load_default_rules
from services.core.vkr_core.services.document_service import _retention_days_from_rules
from services.core.vkr_core.services.normative_service import (
    _normalize_rules_shape,
    _validate_rules,
    update_normative_rules,
)
from services.core.vkr_core.utils.files import FileValidationError, validate_upload
from services.core.vkr_core.utils.security import create_access_token, decode_token


def test_rules_have_required_blocks() -> None:
    rules = load_default_rules()
    for key in [
        "page_settings",
        "body_text_style",
        "structural_elements",
        "heading_detection",
        "numbering_rules",
        "report_templates",
        "forbidden_heading_map",
        "volume_limits",
    ]:
        assert key in rules


def test_rules_defaults_match_runtime_numbering() -> None:
    rules = load_default_rules()
    assert rules["numbering_rules"]["figure_mode"] == "by_chapter"
    assert rules["numbering_rules"]["table_mode"] == "by_chapter"
    assert rules["numbering_rules"]["listing_mode"] == "by_chapter"
    assert "formula_mode" not in rules["numbering_rules"]
    assert rules["volume_limits"] == {"min": 40, "max": 120}


def test_validate_rules_normalizes_old_shape() -> None:
    rules = load_default_rules()
    rules["numbering_rules"]["figure_mode"] = "continuous"
    rules["numbering_rules"]["formula_mode"] = "continuous"
    legacy_work_type = "mas" + "ter"
    legacy_title_marker = "вкр " + "маг" + "истра"
    rules["volume_limits"] = {
        "min": 30,
        "max": 120,
        "bachelor": {"min": 40, "max": 120},
        legacy_work_type: {"min": 60, "max": 150},
    }
    rules["structural_elements"]["title_page"].append(legacy_title_marker)

    normalized = _validate_rules(rules)

    assert "formula_mode" not in normalized["numbering_rules"]
    assert normalized["numbering_rules"]["figure_mode"] == "continuous"
    assert normalized["volume_limits"] == {"min": 40, "max": 120}
    assert legacy_title_marker not in normalized["structural_elements"]["title_page"]


def test_startup_sync_forces_old_numbering_defaults() -> None:
    defaults = load_default_rules()
    legacy = load_default_rules()
    legacy["meta"]["version"] = "v1.0.0"
    legacy["numbering_rules"]["figure_mode"] = "continuous"
    legacy["numbering_rules"]["table_mode"] = "continuous"
    legacy["numbering_rules"]["listing_mode"] = "continuous"

    normalized = _normalize_rules_shape(legacy, defaults=defaults, force_defaults=True)

    assert normalized["numbering_rules"]["figure_mode"] == "by_chapter"
    assert normalized["numbering_rules"]["table_mode"] == "by_chapter"
    assert normalized["numbering_rules"]["listing_mode"] == "by_chapter"


def test_validate_rules_rejects_invalid_numbering_mode() -> None:
    rules = load_default_rules()
    rules["numbering_rules"]["figure_mode"] = "chapterish"
    with pytest.raises(ValueError, match="numbering_rules.figure_mode"):
        _validate_rules(rules)


def test_validate_rules_rejects_unknown_config_keys() -> None:
    rules = load_default_rules()
    rules["unsupported_block"] = {}
    with pytest.raises(ValueError, match="rules_config содержит неподдерживаемые ключи"):
        _validate_rules(rules)

    rules = load_default_rules()
    rules["page_settings"]["unsupported_field"] = True
    with pytest.raises(ValueError, match="page_settings содержит неподдерживаемые ключи"):
        _validate_rules(rules)


def test_retention_days_comes_from_rules() -> None:
    assert _retention_days_from_rules({"security": {"retention_days": 45}}) == 45
    assert _retention_days_from_rules({}) == 90


@pytest.mark.asyncio
async def test_update_normative_rules_syncs_version_metadata() -> None:
    class FakeDb:
        async def commit(self) -> None:
            pass

        async def refresh(self, _version) -> None:
            pass

    rules = load_default_rules()
    rules["meta"]["name"] = "Новая нормативная база"
    rules["meta"]["effective_date"] = "2026-05-27"
    version = SimpleNamespace(
        rules_config={},
        name="Старая нормативная база",
        effective_date=date(2026, 4, 1),
    )

    await update_normative_rules(version, rules, FakeDb())

    assert version.name == "Новая нормативная база"
    assert version.effective_date == date(2026, 5, 27)


def test_jwt_roundtrip() -> None:
    token = create_access_token("test-user", "student")
    payload = decode_token(token)
    assert payload["sub"] == "test-user"
    assert payload["role"] == "student"
    assert payload["type"] == "access"


def test_validate_upload_magic_bytes(tmp_path: Path) -> None:
    import zipfile

    good = tmp_path / "ok.docx"
    with zipfile.ZipFile(good, "w") as zf:
        zf.writestr("word/document.xml", "<?xml version='1.0'?><document/>")
    assert validate_upload(good, "ok.docx") == ".docx"

    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"NOTPDF")
    with pytest.raises(FileValidationError):
        validate_upload(bad, "bad.pdf")

    # ZIP без word/document.xml — spoof, должен отклоняться.
    spoof = tmp_path / "spoof.docx"
    with zipfile.ZipFile(spoof, "w") as zf:
        zf.writestr("hello.txt", "this is not docx")
    with pytest.raises(FileValidationError):
        validate_upload(spoof, "spoof.docx")

    # Битый ZIP с правильной сигнатурой PK\x03\x04, но без структуры —
    # тоже должен отклоняться (BadZipFile).
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"PK\x03\x04dummy")
    with pytest.raises(FileValidationError):
        validate_upload(broken, "broken.docx")
