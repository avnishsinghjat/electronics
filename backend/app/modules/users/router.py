import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.permissions import PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS, Role
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.users import service
from app.modules.users.schemas import (
    PermissionInfo,
    ResetPasswordIn,
    RoleInfo,
    UserCreate,
    UserOut,
    UserPage,
    UserUpdate,
    UserWithPassword,
    VersionIn,
)

router = APIRouter(prefix="/users", tags=["users"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[Principal, Depends(require("users:read"))]
Manager = Annotated[Principal, Depends(require("users:manage"))]


@router.get("/roles", response_model=list[RoleInfo], summary="Roles and their permissions")
async def roles(_: Reader) -> list[RoleInfo]:
    return [
        RoleInfo(role=r, label=ROLE_LABELS[r], permissions=sorted(ROLE_PERMISSIONS[r]))
        for r in Role
    ]


@router.get("/permissions", response_model=list[PermissionInfo], summary="All permissions")
async def permissions(_: Reader) -> list[PermissionInfo]:
    return [PermissionInfo(permission=p, description=d) for p, d in PERMISSIONS.items()]


@router.get("", response_model=UserPage, summary="List users")
async def list_users(
    actor: Reader,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
    q: Annotated[str | None, Query(max_length=100)] = None,
    active: bool | None = None,
) -> UserPage:
    items, total = await service.list_users(
        session, actor, page=page, page_size=page_size, search=q, active=active
    )
    return UserPage(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=UserWithPassword, status_code=201, summary="Create a user")
async def create_user(
    body: UserCreate, actor: Manager, session: SessionDep, settings: SettingsDep
) -> UserWithPassword:
    """The user must change the returned temporary password at first sign-in."""
    user, password = await service.create_user(session, settings, actor, body)
    return UserWithPassword(user=await service.to_out(session, user), temporary_password=password)


@router.get("/{user_id}", response_model=UserOut, summary="Get a user")
async def get_user(user_id: uuid.UUID, actor: Reader, session: SessionDep) -> UserOut:
    return await service.to_out(session, await service.get_user(session, actor, user_id))


@router.patch("/{user_id}", response_model=UserOut, summary="Edit a user, roles and scopes")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, actor: Manager, session: SessionDep
) -> UserOut:
    return await service.to_out(session, await service.update_user(session, actor, user_id, body))


@router.post(
    "/{user_id}/reset-password", response_model=UserWithPassword, summary="Reset a password"
)
async def reset_password(
    user_id: uuid.UUID,
    body: ResetPasswordIn,
    actor: Manager,
    session: SessionDep,
    settings: SettingsDep,
) -> UserWithPassword:
    """Sets a temporary password, unlocks the account and ends the user's sessions."""
    user, password = await service.reset_password(
        session, settings, actor, user_id, body.row_version, body.temporary_password
    )
    return UserWithPassword(user=await service.to_out(session, user), temporary_password=password)


@router.post("/{user_id}/deactivate", response_model=UserOut, summary="Deactivate a user")
async def deactivate(
    user_id: uuid.UUID, body: VersionIn, actor: Manager, session: SessionDep
) -> UserOut:
    return await service.to_out(
        session, await service.set_active(session, actor, user_id, body.row_version, False)
    )


@router.post("/{user_id}/activate", response_model=UserOut, summary="Re-activate a user")
async def activate(
    user_id: uuid.UUID, body: VersionIn, actor: Manager, session: SessionDep
) -> UserOut:
    return await service.to_out(
        session, await service.set_active(session, actor, user_id, body.row_version, True)
    )
