from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.core.vkr_core.models.enums import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    created_at: datetime
    supervisor_id: UUID | None = None
    # Имя руководителя — заполняется в роутере при наличии.
    supervisor_name: str | None = None


class UserUpdateRole(BaseModel):
    role: UserRole


class SupervisorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str


class ProfileUpdateRequest(BaseModel):
    supervisor_id: UUID | None = None
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=128)
