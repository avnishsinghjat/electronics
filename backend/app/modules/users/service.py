"""User administration. Only callers holding ``users:manage`` reach the write functions;
every function re-checks the permission (service-layer enforcement)."""

import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.core.permissions import Role
from app.core.repository import Page, Repository, check_version
from app.core.security import generate_temporary_password, hash_password
from app.modules.auth import service as auth
from app.modules.auth.models import User, UserRole, UserScope
from app.modules.auth.service import Principal
from app.modules.org import service as org
from app.modules.users.schemas import ScopeIn, UserCreate, UserOut, UserUpdate


class UserRepo(Repository[User]):
    model = User
    filterable = frozenset({"username", "full_name", "is_active"})
    sortable = frozenset({"username", "full_name", "created_at", "last_login_at"})
    default_sort = "username"
    entity_label = "User"


async def to_out(session: AsyncSession, user: User) -> UserOut:
    p = await auth.load_principal(session, user)
    return UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        locked_until=user.locked_until,
        last_login_at=user.last_login_at,
        roles=sorted(p.roles),
        scopes=[ScopeIn(scope_type="division", scope_id=s) for s in sorted(p.division_scope)]
        + [ScopeIn(scope_type="project", scope_id=s) for s in sorted(p.project_scope)],
        row_version=user.row_version,
        created_at=user.created_at,
    )


async def list_users(
    session: AsyncSession,
    actor: Principal,
    *,
    page: int,
    page_size: int,
    search: str | None,
    active: bool | None,
) -> tuple[list[UserOut], int]:
    actor.require("users:read")
    filters: dict[str, object] = {}
    if active is not None:
        filters["is_active"] = active
    repo = UserRepo(session)
    stmt = repo.base_query()
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(User.username).like(like) | func.lower(User.full_name).like(like)
        )
    result: Page[User] = await repo.list(page=page, page_size=page_size, filters=filters, stmt=stmt)
    return [await to_out(session, u) for u in result.items], result.total


async def get_user(session: AsyncSession, actor: Principal, user_id: uuid.UUID) -> User:
    actor.require("users:read")
    return await UserRepo(session).get(user_id)


async def _validate_scopes(session: AsyncSession, scopes: list[ScopeIn]) -> None:
    for scope in scopes:
        if not await org.scope_target_exists(session, scope.scope_type.value, scope.scope_id):
            raise AppError(
                f"{scope.scope_type.value.title()} not found for scope",
                code="invalid_scope",
                status_code=422,
                details={"scope_id": str(scope.scope_id)},
            )


async def _set_roles(session: AsyncSession, user: User, roles: list[Role]) -> None:
    existing = {
        r.role: r
        for r in (
            await session.execute(select(UserRole).where(UserRole.user_id == user.id))
        ).scalars()
    }
    wanted = {r.value for r in roles}
    for role, row in existing.items():
        if role not in wanted:
            await session.delete(row)
    for role in wanted - set(existing):
        session.add(UserRole(user_id=user.id, role=role))
    await session.flush()


async def _set_scopes(session: AsyncSession, user: User, scopes: list[ScopeIn]) -> None:
    existing = {
        (s.scope_type, s.scope_id): s
        for s in (
            await session.execute(select(UserScope).where(UserScope.user_id == user.id))
        ).scalars()
    }
    wanted = {(s.scope_type.value, s.scope_id) for s in scopes}
    for key, row in existing.items():
        if key not in wanted:
            await session.delete(row)
    for scope_type, scope_id in wanted - set(existing):
        session.add(UserScope(user_id=user.id, scope_type=scope_type, scope_id=scope_id))
    await session.flush()


async def _active_admin_count(session: AsyncSession, *, excluding: uuid.UUID | None = None) -> int:
    stmt = (
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .where(
            UserRole.role == Role.ADMIN.value, User.is_active.is_(True), User.is_deleted.is_(False)
        )
    )
    if excluding is not None:
        stmt = stmt.where(User.id != excluding)
    return int((await session.execute(stmt)).scalar_one())


async def create_user(
    session: AsyncSession, settings: Settings, actor: Principal, data: UserCreate
) -> tuple[User, str]:
    actor.require("users:manage")
    if await auth.get_user_by_username(session, data.username) is not None:
        raise ConflictError(
            "Username already taken", code="duplicate", details={"field": "username"}
        )
    await _validate_scopes(session, data.scopes)
    password = data.temporary_password or generate_temporary_password()
    auth.validate_new_password(settings, password, username=data.username)
    user = User(
        username=data.username,
        full_name=data.full_name,
        email=str(data.email) if data.email else None,
        password_hash=hash_password(password),
        must_change_password=True,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await _set_roles(session, user, data.roles)
    await _set_scopes(session, user, data.scopes)
    await session.commit()
    return user, password


async def update_user(
    session: AsyncSession, actor: Principal, user_id: uuid.UUID, data: UserUpdate
) -> User:
    actor.require("users:manage")
    user = await UserRepo(session).get(user_id)
    check_version(user, data.row_version)
    if data.full_name is not None:
        user.full_name = data.full_name
    if "email" in data.model_fields_set:
        user.email = str(data.email) if data.email else None
    if data.roles is not None:
        if (
            Role.ADMIN not in data.roles
            and await _active_admin_count(session, excluding=user.id) == 0
        ):
            raise ConflictError("At least one active admin must remain", code="last_admin")
        await _set_roles(session, user, data.roles)
    if data.scopes is not None:
        await _validate_scopes(session, data.scopes)
        await _set_scopes(session, user, data.scopes)
    # Role/scope changes touch only child rows; force an UPDATE of the user row so its
    # row_version always increments and a concurrent editor gets a 409.
    flag_modified(user, "updated_by")
    await session.commit()
    return user


async def reset_password(
    session: AsyncSession,
    settings: Settings,
    actor: Principal,
    user_id: uuid.UUID,
    row_version: int,
    temporary: str | None,
) -> tuple[User, str]:
    actor.require("users:manage")
    user = await UserRepo(session).get(user_id)
    check_version(user, row_version)
    password = temporary or generate_temporary_password()
    auth.validate_new_password(settings, password, username=user.username)
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    await auth.revoke_all_sessions(session, user.id)
    await session.commit()
    return user, password


async def set_active(
    session: AsyncSession, actor: Principal, user_id: uuid.UUID, row_version: int, active: bool
) -> User:
    actor.require("users:manage")
    user = await UserRepo(session).get(user_id)
    check_version(user, row_version)
    if not active:
        if user.id == actor.id:
            raise ConflictError("You cannot deactivate your own account", code="self_deactivation")
        roles = (await auth.load_principal(session, user)).roles
        if Role.ADMIN in roles and await _active_admin_count(session, excluding=user.id) == 0:
            raise ConflictError("At least one active admin must remain", code="last_admin")
        await auth.revoke_all_sessions(session, user.id)
    user.is_active = active
    await session.commit()
    return user


async def display_names(
    session: AsyncSession, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    """User id -> full name, for "created by" / "approved by" columns of other modules."""
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(select(User.id, User.full_name).where(User.id.in_(wanted)))
    return {uid: name for uid, name in rows.all()}
