from __future__ import annotations

from importlib import import_module

__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "RefreshRequest",
    "LogoutRequest",
    "TokenPair",
    "UserOut",
    "UserUpdateRole",
    "SupervisorOut",
    "ProfileUpdateRequest",
    "DocumentOut",
    "DocumentStatusOut",
    "DocumentSnapshotOut",
    "DocumentRollbackResponse",
    "UploadResponse",
    "ApprovalDecisionRequest",
    "ReviewRoundOut",
    "DocumentCommentIn",
    "DocumentCommentOut",
    "ViolationOut",
    "ViolationActionResponse",
    "ViolationCommentRequest",
    "ViolationCommentResponse",
    "ProcessingReportOut",
    "NormativeVersionOut",
    "NormativeRulesOut",
    "NormativeRulesUpdate",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "RegisterRequest": ("services.core.vkr_core.schemas.auth", "RegisterRequest"),
    "LoginRequest": ("services.core.vkr_core.schemas.auth", "LoginRequest"),
    "RefreshRequest": ("services.core.vkr_core.schemas.auth", "RefreshRequest"),
    "LogoutRequest": ("services.core.vkr_core.schemas.auth", "LogoutRequest"),
    "TokenPair": ("services.core.vkr_core.schemas.auth", "TokenPair"),
    "UserOut": ("services.core.vkr_core.schemas.user", "UserOut"),
    "UserUpdateRole": ("services.core.vkr_core.schemas.user", "UserUpdateRole"),
    "SupervisorOut": ("services.core.vkr_core.schemas.user", "SupervisorOut"),
    "ProfileUpdateRequest": ("services.core.vkr_core.schemas.user", "ProfileUpdateRequest"),
    "DocumentOut": ("services.core.vkr_core.schemas.document", "DocumentOut"),
    "DocumentStatusOut": ("services.core.vkr_core.schemas.document", "DocumentStatusOut"),
    "DocumentSnapshotOut": ("services.core.vkr_core.schemas.document", "DocumentSnapshotOut"),
    "DocumentRollbackResponse": ("services.core.vkr_core.schemas.document", "DocumentRollbackResponse"),
    "UploadResponse": ("services.core.vkr_core.schemas.document", "UploadResponse"),
    "ApprovalDecisionRequest": ("services.core.vkr_core.schemas.document", "ApprovalDecisionRequest"),
    "ReviewRoundOut": ("services.core.vkr_core.schemas.document", "ReviewRoundOut"),
    "DocumentCommentIn": ("services.core.vkr_core.schemas.document", "DocumentCommentIn"),
    "DocumentCommentOut": ("services.core.vkr_core.schemas.document", "DocumentCommentOut"),
    "ViolationOut": ("services.core.vkr_core.schemas.violation", "ViolationOut"),
    "ViolationActionResponse": ("services.core.vkr_core.schemas.violation", "ViolationActionResponse"),
    "ViolationCommentRequest": ("services.core.vkr_core.schemas.violation", "ViolationCommentRequest"),
    "ViolationCommentResponse": ("services.core.vkr_core.schemas.violation", "ViolationCommentResponse"),
    "ProcessingReportOut": ("services.core.vkr_core.schemas.report", "ProcessingReportOut"),
    "NormativeVersionOut": ("services.core.vkr_core.schemas.normative", "NormativeVersionOut"),
    "NormativeRulesOut": ("services.core.vkr_core.schemas.normative", "NormativeRulesOut"),
    "NormativeRulesUpdate": ("services.core.vkr_core.schemas.normative", "NormativeRulesUpdate"),
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
