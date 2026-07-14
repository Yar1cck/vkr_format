from __future__ import annotations

from importlib import import_module

__all__ = [
    "User",
    "Document",
    "ProcessingReport",
    "ViolationRecord",
    "NormativeVersion",
    "ReviewRound",
    "DocumentComment",
    "DocumentSnapshot",
    "UserRole",
    "DocumentStatus",
    "ViolationStatus",
    "ProcessingMode",
    "ApprovalStatus",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "User": ("services.core.vkr_core.models.entities", "User"),
    "Document": ("services.core.vkr_core.models.entities", "Document"),
    "ProcessingReport": ("services.core.vkr_core.models.entities", "ProcessingReport"),
    "ViolationRecord": ("services.core.vkr_core.models.entities", "ViolationRecord"),
    "NormativeVersion": ("services.core.vkr_core.models.entities", "NormativeVersion"),
    "ReviewRound": ("services.core.vkr_core.models.entities", "ReviewRound"),
    "DocumentComment": ("services.core.vkr_core.models.entities", "DocumentComment"),
    "DocumentSnapshot": ("services.core.vkr_core.models.entities", "DocumentSnapshot"),
    "UserRole": ("services.core.vkr_core.models.enums", "UserRole"),
    "DocumentStatus": ("services.core.vkr_core.models.enums", "DocumentStatus"),
    "ViolationStatus": ("services.core.vkr_core.models.enums", "ViolationStatus"),
    "ProcessingMode": ("services.core.vkr_core.models.enums", "ProcessingMode"),
    "ApprovalStatus": ("services.core.vkr_core.models.enums", "ApprovalStatus"),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if not target:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, symbol_name = target
    module = import_module(module_name)
    value = getattr(module, symbol_name)
    globals()[name] = value
    return value
