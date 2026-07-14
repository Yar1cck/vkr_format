from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.dependencies import get_current_user, oauth2_scheme
from services.api.app.rate_limit import limiter
from services.core.vkr_core.db.session import get_db
from services.core.vkr_core.models import User, UserRole
from services.core.vkr_core.schemas import (
    LoginRequest,
    LogoutRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    SupervisorOut,
    TokenPair,
    UserOut,
)
from services.core.vkr_core.services import (
    AuthError,
    list_supervisors,
    login_user,
    register_user,
    update_profile,
)
from services.core.vkr_core.services.token_revoker import is_jti_revoked, revoke_jti
from services.core.vkr_core.utils import TokenError, create_access_token, decode_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# Rate-лимиты подобраны под добросовестный сценарий + защиту от brute-force:
# обычный студент логинится <5 раз в день, регистрируется один раз. Лимиты
# применяются per-IP; за NAT целая аудитория делит общий лимит, поэтому
# /login не делаем слишком жёстким.
@router.post("/register", response_model=UserOut, summary="Регистрация студента")
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Публичная регистрация. Всегда создаёт student'а; повышение до
    supervisor/dean/admin — через `PATCH /admin/users/{id}`. Rate-limit: 5/мин на IP."""
    try:
        user = await register_user(payload, db)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenPair, summary="Вход (email + пароль)")
@limiter.limit("10/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Возвращает access (30 мин) + refresh (7 дней). Rate-limit 10/мин на IP."""
    try:
        _user, tokens = await login_user(payload, db)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    _user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> Response:
    """Отзывает access (и опционально refresh) токены.

    После logout попытка использовать те же токены вернёт 401: jti
    кладётся в Redis-blacklist с TTL до естественного истечения. Если
    пользователь не передал refresh_token, отзывается только access —
    и злоумышленник с украденным refresh сможет выписать новый access.
    Поэтому frontend должен передавать оба токена при logout.
    """
    # Access-токен уже валиден (`get_current_user` это проверил), просто
    # извлекаем его jti и exp.
    access_payload = decode_token(token)
    access_jti = access_payload.get("jti")
    access_exp = datetime.fromtimestamp(access_payload["exp"], tz=UTC)
    await revoke_jti(access_jti, access_exp)

    if body.refresh_token:
        try:
            refresh_payload = decode_token(body.refresh_token)
        except TokenError:
            # Refresh кривой — игнорируем (logout должен быть идемпотентным).
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        if refresh_payload.get("type") == "refresh":
            await revoke_jti(
                refresh_payload.get("jti"),
                datetime.fromtimestamp(refresh_payload["exp"], tz=UTC),
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Возвращает данные текущего аутентифицированного пользователя."""
    payload = UserOut.model_validate(current_user)
    if current_user.supervisor_id:
        from services.core.vkr_core.models.entities import User as UserModel
        sup = await db.get(UserModel, current_user.supervisor_id)
        if sup:
            payload = payload.model_copy(update={"supervisor_name": sup.full_name})
    return payload


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Обновляет профиль текущего пользователя: пароль и/или научрук."""
    try:
        user = await update_profile(current_user, body, db)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    payload = UserOut.model_validate(user)
    if user.supervisor_id:
        from services.core.vkr_core.models.entities import User as UserModel
        sup = await db.get(UserModel, user.supervisor_id)
        if sup:
            payload = payload.model_copy(update={"supervisor_name": sup.full_name})
    return payload


@router.get("/supervisors", response_model=list[SupervisorOut])
async def get_supervisors(
    db: AsyncSession = Depends(get_db),
) -> list[SupervisorOut]:
    """Список руководителей для выбора при регистрации и в настройках."""
    return await list_supervisors(db)


class AssignStudentRequest(BaseModel):
    student_id: UUID


@router.get("/students", response_model=list[UserOut])
async def list_all_students(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    """Список всех студентов — для руководителя, чтобы выбрать кого прикрепить."""
    if current_user.role not in (UserRole.supervisor, UserRole.dean, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только для руководителей")
    rows = await db.scalars(
        sa_select(User).where(User.role == UserRole.student).order_by(User.full_name)
    )
    return [UserOut.model_validate(u) for u in rows]


@router.get("/my-students", response_model=list[UserOut])
async def get_my_students(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    """Список студентов, привязанных к текущему руководителю."""
    if current_user.role not in (UserRole.supervisor, UserRole.dean, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только для руководителей")
    rows = await db.scalars(
        sa_select(User).where(User.supervisor_id == current_user.id)
    )
    return [UserOut.model_validate(u) for u in rows]


@router.post("/my-students", response_model=UserOut, status_code=status.HTTP_200_OK)
async def assign_student(
    body: AssignStudentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Руководитель прикрепляет студента к себе."""
    if current_user.role not in (UserRole.supervisor, UserRole.dean, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только для руководителей")
    student = await db.get(User, body.student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не найден")
    if student.role != UserRole.student:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь не является студентом")
    student.supervisor_id = current_user.id
    await db.commit()
    await db.refresh(student)
    return UserOut.model_validate(student)


@router.delete("/my-students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_student(
    student_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Руководитель открепляет студента."""
    if current_user.role not in (UserRole.supervisor, UserRole.dean, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только для руководителей")
    student = await db.get(User, student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Студент не найден")
    if student.supervisor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Студент не прикреплён к вам")
    student.supervisor_id = None
    await db.commit()


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
async def refresh(request: Request, payload: RefreshRequest) -> TokenPair:
    try:
        token_payload = decode_token(payload.refresh_token)
    except TokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # После logout refresh-токен мог быть отозван — не даём выпустить
    # новый access по нему.
    if await is_jti_revoked(token_payload.get("jti")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")

    user_id = token_payload["sub"]
    role = token_payload["role"]
    return TokenPair(
        access_token=create_access_token(user_id, role),
        refresh_token=payload.refresh_token,
    )
