from __future__ import annotations

from services.api.app.main import app


def test_api_contract_routes_exist() -> None:
    paths = {route.path for route in app.router.routes}
    required = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/supervisors",
        "/api/v1/documents/upload",
        "/api/v1/documents/",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/status",
        "/api/v1/documents/{document_id}/download/original",
        "/api/v1/documents/{document_id}/download/processed",
        "/api/v1/documents/{document_id}/download/processed-pdf",
        "/api/v1/documents/{document_id}/report",
        "/api/v1/documents/{document_id}/submit-for-review",
        "/api/v1/documents/{document_id}/approve",
        "/api/v1/documents/{document_id}/reject",
        "/api/v1/documents/{document_id}/review-history",
        "/api/v1/documents/{document_id}/comments",
        "/api/v1/documents/{document_id}/snapshots",
        "/api/v1/documents/{document_id}/snapshots/{snapshot_id}/rollback",
        "/api/v1/violations/{document_id}",
        "/api/v1/violations/{violation_id}/accept",
        "/api/v1/violations/{violation_id}/reject",
        "/api/v1/violations/{violation_id}/fix-heading-number",
        "/api/v1/violations/{violation_id}/promote-to-heading",
        "/api/v1/violations/{violation_id}/demote-heading-to-text",
        "/api/v1/violations/{violation_id}/revert-caption",
        "/api/v1/violations/{violation_id}/revert",
        "/api/v1/violations/{violation_id}/comment",
        "/api/v1/normative/versions",
        "/api/v1/normative/{version_id}/rules",
        "/api/v1/normative/reference-docs",
        "/api/v1/normative/reference-docs/{slug}",
        "/api/v1/admin/users",
        "/api/v1/admin/users/{user_id}",
        "/api/v1/admin/stats",
        "/api/v1/admin/normative/{version_id}/rules",
    }
    assert required.issubset(paths)


def test_no_removed_routes_present() -> None:
    paths = {route.path for route in app.router.routes}
    for path in paths:
        assert "llm" not in path.lower(), f"LLM route present: {path}"
        assert "profile" not in path.lower(), f"Profile route still registered: {path}"
