from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NormativeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    effective_date: date
    is_active: bool
    created_at: datetime


class NormativeRulesOut(BaseModel):
    version_id: UUID
    rules_config: dict


class NormativeRulesUpdate(BaseModel):
    rules_config: dict
