from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.api.app.dependencies import require_roles
from services.core.vkr_core.models.enums import UserRole


class DummyUser:
    def __init__(self, role: UserRole):
        self.role = role


@pytest.mark.asyncio
async def test_require_roles_allows_admin() -> None:
    checker = require_roles(UserRole.admin)
    user = DummyUser(UserRole.admin)
    result = await checker(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_roles_denies_student() -> None:
    checker = require_roles(UserRole.admin)
    user = DummyUser(UserRole.student)
    with pytest.raises(HTTPException):
        await checker(current_user=user)
