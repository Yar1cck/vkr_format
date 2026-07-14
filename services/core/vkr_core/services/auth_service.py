from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.core.vkr_core.models import User, UserRole
from services.core.vkr_core.schemas.auth import LoginRequest, RegisterRequest, TokenPair
from services.core.vkr_core.schemas.user import ProfileUpdateRequest, SupervisorOut
from services.core.vkr_core.utils import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)


class AuthError(Exception):
    pass


async def register_user(payload: RegisterRequest, db: AsyncSession) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise AuthError("Email already registered")

    # Публичная регистрация всегда создаёт студента. Повышение до
    # supervisor / dean / admin делается админом через /admin/users/{id}.
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.student,
        supervisor_id=payload.supervisor_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_supervisors(db: AsyncSession) -> list[SupervisorOut]:
    rows = await db.scalars(
        select(User)
        .where(User.role == UserRole.supervisor)
        .order_by(User.full_name)
    )
    return [SupervisorOut.model_validate(u) for u in rows.all()]


async def update_profile(
    user: User,
    payload: ProfileUpdateRequest,
    db: AsyncSession,
) -> User:
    if payload.new_password is not None:
        if not payload.current_password:
            raise AuthError("current_password обязателен при смене пароля")
        if not verify_password(payload.current_password, user.hashed_password):
            raise AuthError("Текущий пароль неверен")
        user.hashed_password = hash_password(payload.new_password)

    if "supervisor_id" in payload.model_fields_set:
        user.supervisor_id = payload.supervisor_id

    await db.commit()
    await db.refresh(user)
    return user


async def login_user(payload: LoginRequest, db: AsyncSession) -> tuple[User, TokenPair]:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise AuthError("Invalid email or password")

    tokens = TokenPair(
        access_token=create_access_token(str(user.id), user.role.value),
        refresh_token=create_refresh_token(str(user.id), user.role.value),
    )
    return user, tokens
