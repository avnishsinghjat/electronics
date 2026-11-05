"""Authentication service: login, lockout, refresh rotation, logout, password change,
and loading the authenticated principal (roles, permissions, scopes)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, record_event
from app.core.config import Settings
from app.core.errors import AppError, PermissionDeniedError
from app.core.models import utcnow
from app.core.permissions import Role, permissions_for
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_refresh_secret,
    verify_password,
)
from app.modules.auth.models import RefreshToken, ScopeType, User, UserRole, UserScope


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class AccountLockedError(AppError):
    status_code = 423
    code = "account_locked"


class PasswordChangeRequiredError(PermissionDeniedError):
    code = "password_change_required"


@dataclass(frozen=True)
class Principal:
    """The authenticated user as seen by services (permissions and scoping)."""

    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    roles: frozenset[Role]
    permissions: frozenset[str]
    division_scope: frozenset[uuid.UUID] = field(default_factory=frozenset)
    project_scope: frozenset[uuid.UUID] = field(default_factory=frozenset)
    must_change_password: bool = False
    session_id: uuid.UUID | None = None

    @property
    def unrestricted(self) -> bool:
        """True when the user may see every division and project."""
        return Role.ADMIN in self.roles or not (self.division_scope or self.project_scope)

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionDeniedError(
                "You do not have permission to do this", details={"permission": permission}
            )


@dataclass(frozen=True)
class IssuedSession:
    principal: Principal
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


# ---------------------------------------------------------------- password policy


def validate_new_password(settings: Settings, password: str, *, username: str) -> None:
    problems = []
    if len(password) < settings.min_password_length:
        problems.append(f"at least {settings.min_password_length} characters")
    if password.lower() == username.lower() or username.lower() in password.lower():
        problems.append("must not contain the username")
    if password.isdigit() or password.isalpha():
        problems.append("mix letters with digits or symbols")
    if problems:
        raise AppError(
            "Password does not meet the policy: " + "; ".join(problems),
            code="weak_password",
            status_code=422,
            details={"requirements": problems},
        )


# ---------------------------------------------------------------- loading


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(func.lower(User.username) == username.strip().lower())
    return (await session.execute(stmt)).scalar_one_or_none()


async def load_principal(
    session: AsyncSession, user: User, *, session_id: uuid.UUID | None = None
) -> Principal:
    roles = frozenset(
        Role(r)
        for r in (
            await session.execute(
                select(UserRole.role).where(
                    UserRole.user_id == user.id, UserRole.is_deleted.is_(False)
                )
            )
        ).scalars()
    )
    scopes = (
        await session.execute(
            select(UserScope.scope_type, UserScope.scope_id).where(
                UserScope.user_id == user.id, UserScope.is_deleted.is_(False)
            )
        )
    ).all()
    return Principal(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        roles=roles,
        permissions=permissions_for(roles),
        division_scope=frozenset(s[1] for s in scopes if s[0] == ScopeType.DIVISION),
        project_scope=frozenset(s[1] for s in scopes if s[0] == ScopeType.PROJECT),
        must_change_password=user.must_change_password,
        session_id=session_id,
    )


async def session_is_active(session: AsyncSession, session_id: uuid.UUID) -> bool:
    stmt = select(func.count()).where(
        RefreshToken.family_id == session_id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > utcnow(),
    )
    return bool((await session.execute(stmt)).scalar_one())


# ---------------------------------------------------------------- sessions


async def _issue(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    family_id: uuid.UUID,
    user_agent: str | None,
    ip: str | None,
) -> tuple[RefreshToken, str]:
    secret = new_refresh_secret()
    token = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_token(secret),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        user_agent=(user_agent or "")[:255] or None,
        ip_address=ip,
    )
    session.add(token)
    await session.flush()
    return token, secret


async def _session_for(
    session: AsyncSession, settings: Settings, user: User, token: RefreshToken, secret: str
) -> IssuedSession:
    principal = await load_principal(session, user, session_id=token.family_id)
    access, expires = create_access_token(
        settings,
        user_id=user.id,
        session_id=token.family_id,
        must_change_password=user.must_change_password,
    )
    return IssuedSession(principal, access, expires, secret, token.expires_at)


async def login(
    session: AsyncSession,
    settings: Settings,
    username: str,
    password: str,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> IssuedSession:
    invalid = AuthError("Invalid username or password", code="invalid_credentials")
    user = await get_user_by_username(session, username)
    if user is None or not user.is_active or user.is_deleted:
        verify_password(DUMMY_HASH, password)  # same cost as a real check (no user enumeration)
        raise invalid

    now = utcnow()
    if user.locked_until is not None and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise AccountLockedError(
            f"Account locked after too many failed attempts. Try again in {minutes} minute(s) "
            "or ask an administrator to reset your password.",
            details={"locked_until": user.locked_until.isoformat()},
        )

    # Login bookkeeping uses Core UPDATEs: it must not bump row_version (an admin editing
    # this user would otherwise get spurious 409s). Each outcome is an explicit audit event.
    if not verify_password(user.password_hash, password):
        failures = user.failed_logins + 1
        locked_until = None
        if failures >= settings.max_failed_logins:
            locked_until = now + timedelta(minutes=settings.lockout_minutes)
            failures = 0
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(failed_logins=failures, locked_until=locked_until)
        )
        await record_event(
            session,
            AuditAction.LOCKED if locked_until else AuditAction.LOGIN_FAILED,
            entity_type="users",
            entity_id=str(user.id),
            details={"ip": ip, "user_agent": user_agent},
        )
        await session.commit()
        if locked_until is not None:
            raise AccountLockedError(
                f"Account locked for {settings.lockout_minutes} minutes after "
                f"{settings.max_failed_logins} failed attempts.",
                details={"locked_until": locked_until.isoformat()},
            )
        raise invalid

    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(failed_logins=0, locked_until=None, last_login_at=now)
    )
    await session.refresh(user)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await record_event(
        session,
        AuditAction.LOGIN,
        entity_type="users",
        entity_id=str(user.id),
        actor_id=user.id,
        details={"ip": ip, "user_agent": user_agent},
    )
    token, secret = await _issue(
        session, settings, user, family_id=uuid.uuid4(), user_agent=user_agent, ip=ip
    )
    issued = await _session_for(session, settings, user, token, secret)
    await session.commit()
    return issued


async def refresh(
    session: AsyncSession,
    settings: Settings,
    refresh_secret: str | None,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> IssuedSession:
    if not refresh_secret:
        raise AuthError("Not signed in", code="no_session")
    token = (
        await session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_secret))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if token is None:
        raise AuthError("Session expired, please sign in again", code="invalid_session")
    now = utcnow()
    if token.revoked_at is not None:
        # A rotated token was presented again: assume theft, end the whole session family.
        await revoke_family(session, token.family_id)
        await session.commit()
        raise AuthError(
            "Session ended for security reasons, please sign in again", code="refresh_token_reused"
        )
    if token.expires_at <= now:
        raise AuthError("Session expired, please sign in again", code="session_expired")
    user = await session.get(User, token.user_id)
    if user is None or not user.is_active or user.is_deleted:
        await revoke_family(session, token.family_id)
        await session.commit()
        raise AuthError("Account is not active", code="inactive_account")

    new_token, secret = await _issue(
        session, settings, user, family_id=token.family_id, user_agent=user_agent, ip=ip
    )
    token.revoked_at = now
    token.replaced_by_id = new_token.id
    issued = await _session_for(session, settings, user, new_token, secret)
    await session.commit()
    return issued


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def revoke_all_sessions(
    session: AsyncSession, user_id: uuid.UUID, *, except_family: uuid.UUID | None = None
) -> None:
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if except_family is not None:
        stmt = stmt.where(RefreshToken.family_id != except_family)
    await session.execute(stmt.values(revoked_at=utcnow()))


async def logout(
    session: AsyncSession, refresh_secret: str | None, session_id: uuid.UUID | None
) -> None:
    family: uuid.UUID | None = session_id
    user_id: uuid.UUID | None = None
    if refresh_secret:
        token = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_secret))
            )
        ).scalar_one_or_none()
        if token is not None:
            family, user_id = token.family_id, token.user_id
    if family is not None:
        await revoke_family(session, family)
    if user_id is not None:
        await record_event(
            session,
            AuditAction.LOGOUT,
            entity_type="users",
            entity_id=str(user_id),
            actor_id=user_id,
        )
    await session.commit()


async def change_password(
    session: AsyncSession, settings: Settings, principal: Principal, current: str, new: str
) -> IssuedSession | None:
    user = await session.get(User, principal.id)
    if user is None:
        raise AuthError("Account not found")
    if not verify_password(user.password_hash, current):
        raise AppError("Current password is incorrect", code="wrong_password", status_code=422)
    if verify_password(user.password_hash, new):
        raise AppError("New password must be different", code="weak_password", status_code=422)
    validate_new_password(settings, new, username=user.username)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    await revoke_all_sessions(session, user.id, except_family=principal.session_id)
    await session.flush()
    issued: IssuedSession | None = None
    if principal.session_id is not None:
        access, expires = create_access_token(
            settings, user_id=user.id, session_id=principal.session_id, must_change_password=False
        )
        p = await load_principal(session, user, session_id=principal.session_id)
        issued = IssuedSession(p, access, expires, "", datetime.now(UTC))
    await session.commit()
    return issued
