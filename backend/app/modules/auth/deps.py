"""Route dependencies. Every endpoint declares exactly one of:

* ``Depends(require("perm"))`` - signed-in user holding the permission,
* ``Depends(authenticated)``   - any signed-in user (own profile, password change, logout),
* ``Depends(public)``          - anonymous (health, login, first-run setup, branding).

``tests/auth/test_permission_matrix.py`` fails if a route declares none of them.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.context import current_actor_id
from app.core.db import get_session
from app.core.errors import PermissionDeniedError
from app.core.permissions import PERMISSIONS
from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.auth.service import (
    AuthError,
    PasswordChangeRequiredError,
    Principal,
    load_principal,
    session_is_active,
)

PERMISSION_ATTR = "__fabtrack_permission__"
PUBLIC = "public"
AUTHENTICATED = "authenticated"


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Sign in required", code="not_authenticated")
    return token.strip()


async def _principal(
    request: Request, session: AsyncSession, settings: Settings, *, allow_password_change: bool
) -> Principal:
    try:
        claims = decode_access_token(settings, _bearer(request))
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid access token", code="invalid_token") from exc
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active or user.is_deleted:
        raise AuthError("Account is not active", code="inactive_account")
    if not await session_is_active(session, claims.session_id):
        raise AuthError("Session ended, please sign in again", code="session_revoked")
    principal = await load_principal(session, user, session_id=claims.session_id)
    if user.must_change_password and not allow_password_change:
        raise PasswordChangeRequiredError("Change your password to continue")
    current_actor_id.set(user.id)
    request.state.principal = principal
    return principal


def _mark(fn: Callable[..., Awaitable[Any]], value: str) -> Callable[..., Awaitable[Any]]:
    setattr(fn, PERMISSION_ATTR, value)
    return fn


def require(permission: str) -> Callable[..., Awaitable[Principal]]:
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission {permission!r}")

    async def dependency(
        request: Request,
        session: Annotated[AsyncSession, Depends(get_session)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> Principal:
        principal = await _principal(request, session, settings, allow_password_change=False)
        if not principal.can(permission):
            raise PermissionDeniedError(
                "You do not have permission to do this", details={"permission": permission}
            )
        return principal

    dependency.__name__ = f"require_{permission.replace(':', '_')}"
    return _mark(dependency, permission)


async def _authenticated(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    return await _principal(request, session, settings, allow_password_change=True)


async def _public() -> None:
    return None


authenticated = _mark(_authenticated, AUTHENTICATED)
public = _mark(_public, PUBLIC)

CurrentUser = Annotated[Principal, Depends(authenticated)]
