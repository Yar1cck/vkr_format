from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.api.app.routers import documents as documents_router
from services.core.vkr_core.models import DocumentStatus


class FakeSession:
    async def commit(self) -> None:
        raise AssertionError("submit-for-review must not commit without supervisor")

    async def refresh(self, _obj: object) -> None:
        raise AssertionError("submit-for-review must not refresh without supervisor")


@pytest.mark.asyncio
async def test_submit_for_review_requires_selected_supervisor(monkeypatch) -> None:
    user_id = uuid4()
    document = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=DocumentStatus.done,
    )
    current_user = SimpleNamespace(id=user_id, supervisor_id=None)

    async def fake_get_document_or_404(document_id, user, db):
        assert document_id == document.id
        assert user is current_user
        assert isinstance(db, FakeSession)
        return document

    monkeypatch.setattr(documents_router, "get_document_or_404", fake_get_document_or_404)

    with pytest.raises(HTTPException) as exc:
        await documents_router.submit_for_review(document.id, current_user, FakeSession())

    assert exc.value.status_code == 400
    assert "Выберите научного руководителя" in exc.value.detail
