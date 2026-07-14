from __future__ import annotations

from services.api.app.routers.violations import _needs_full_table_split


def test_needs_full_table_split_false_without_comparable_data() -> None:
    assert _needs_full_table_split(None, [1, 2]) is False
    assert _needs_full_table_split([1, 2], None) is False


def test_needs_full_table_split_true_when_baked_pages_changed() -> None:
    assert _needs_full_table_split([1, 2, 3], [1, 4, 3]) is True
    assert _needs_full_table_split([1, 2], [1, 2]) is False
