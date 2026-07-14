from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.dependencies import require_roles
from services.core.vkr_core.db.session import get_db
from services.core.vkr_core.models import User, UserRole
from services.core.vkr_core.schemas import (
    NormativeRulesOut,
    NormativeRulesUpdate,
    UserOut,
    UserUpdateRole,
)
from services.core.vkr_core.services import (
    get_admin_stats,
    get_normative_by_id,
    update_normative_rules,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut], summary="Список пользователей")
async def list_users(
    _admin: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    """Возвращает всех пользователей, новые первыми. Доступно только admin."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = list(result.scalars().all())
    return [UserOut.model_validate(user) for user in users]


@router.patch("/users/{user_id}", response_model=UserOut, summary="Сменить роль пользователя")
async def update_user_role(
    user_id: UUID,
    payload: UserUpdateRole,
    _admin: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Меняет роль пользователя (student → supervisor/dean/admin). Только admin."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = payload.role
    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/stats", summary="Агрегаты для дашборда")
async def stats(
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.dean, UserRole.supervisor)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Сводная статистика для дашборда: total_documents, total_users,
    total_students, avg_violations, uploads_30d, violations_by_category,
    recent_uploads. Доступно admin/dean/supervisor.
    Руководитель видит только своих студентов; admin/dean — всех."""
    return await get_admin_stats(db, current_user=current_user)


@router.put("/normative/{version_id}/rules", response_model=NormativeRulesOut, summary="Обновить правила нормативной базы")
async def put_normative_rules(
    version_id: UUID,
    payload: NormativeRulesUpdate,
    _admin: User = Depends(require_roles(UserRole.admin)),
    db: AsyncSession = Depends(get_db),
) -> NormativeRulesOut:
    """Заменяет rules_config выбранной нормативной версии. Применяется к
    будущим обработкам — для уже обработанных документов rules фиксируется
    при создании ProcessingReport."""
    version = await get_normative_by_id(version_id, db)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Normative version not found")

    try:
        version = await update_normative_rules(version, payload.rules_config, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return NormativeRulesOut(version_id=version.id, rules_config=version.rules_config)
