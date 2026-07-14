from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.core.vkr_core.models import (
    Document,
    ProcessingReport,
    User,
    UserRole,
    ViolationRecord,
)
from services.core.vkr_core.services.document_service import (
    AccessDeniedError,
    get_violation_or_404,
)


class FakeSession:
    def __init__(self, rows: dict[tuple[type, object], object]) -> None:
        self.rows = rows

    async def get(self, model: type, row_id: object) -> object | None:
        return self.rows.get((model, row_id))


def _violation_graph(supervisor_id):
    student_id = uuid4()
    document_id = uuid4()
    report_id = uuid4()
    violation_id = uuid4()

    violation = SimpleNamespace(id=violation_id, report_id=report_id)
    report = SimpleNamespace(id=report_id, document_id=document_id)
    document = SimpleNamespace(id=document_id, user_id=student_id)
    student = SimpleNamespace(id=student_id, supervisor_id=supervisor_id)

    rows = {
        (ViolationRecord, violation_id): violation,
        (ProcessingReport, report_id): report,
        (Document, document_id): document,
        (User, student_id): student,
    }
    return violation_id, violation, rows


@pytest.mark.asyncio
async def test_get_violation_denies_supervisor_by_default() -> None:
    supervisor_id = uuid4()
    violation_id, _, rows = _violation_graph(supervisor_id)
    supervisor = SimpleNamespace(id=supervisor_id, role=UserRole.supervisor)

    with pytest.raises(AccessDeniedError):
        await get_violation_or_404(violation_id, supervisor, FakeSession(rows))


@pytest.mark.asyncio
async def test_get_violation_allows_assigned_supervisor_when_enabled() -> None:
    supervisor_id = uuid4()
    violation_id, violation, rows = _violation_graph(supervisor_id)
    supervisor = SimpleNamespace(id=supervisor_id, role=UserRole.supervisor)

    result = await get_violation_or_404(
        violation_id,
        supervisor,
        FakeSession(rows),
        allow_supervisor=True,
    )

    assert result is violation


@pytest.mark.asyncio
async def test_get_violation_denies_unassigned_supervisor() -> None:
    supervisor = SimpleNamespace(id=uuid4(), role=UserRole.supervisor)
    violation_id, _, rows = _violation_graph(supervisor_id=uuid4())

    with pytest.raises(AccessDeniedError):
        await get_violation_or_404(
            violation_id,
            supervisor,
            FakeSession(rows),
            allow_supervisor=True,
        )
