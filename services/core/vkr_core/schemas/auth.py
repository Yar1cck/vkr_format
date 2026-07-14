from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    # extra="ignore": если клиент попробует подделать запрос полем `role`,
    # оно молча отбрасывается. Все, кто проходит публичную регистрацию,
    # становятся студентами; повышение прав делает только админ через
    # /admin/users/{id}.
    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    supervisor_id: UUID | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    # Опционально передаём refresh_token, чтобы отозвать его одновременно
    # с access. Без этого refresh жил бы до своего истечения (7 дней),
    # позволяя злоумышленнику с украденным refresh выпускать новые
    # access-токены, несмотря на logout.
    refresh_token: str | None = None
