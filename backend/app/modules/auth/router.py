from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.security import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.modules.auth import service
from app.modules.auth.deps import authenticated, public
from app.modules.auth.schemas import ChangePasswordRequest, LoginRequest, MeOut, ScopeOut, TokenOut
from app.modules.auth.service import IssuedSession, Principal

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def me_out(p: Principal) -> MeOut:
    return MeOut(
        id=p.id,
        username=p.username,
        full_name=p.full_name,
        email=p.email,
        roles=sorted(p.roles),
        permissions=sorted(p.permissions),
        scopes=[ScopeOut(scope_type="division", scope_id=s) for s in sorted(p.division_scope)]
        + [ScopeOut(scope_type="project", scope_id=s) for s in sorted(p.project_scope)],
        must_change_password=p.must_change_password,
    )


def set_refresh_cookie(response: Response, settings: Settings, issued: IssuedSession) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def token_out(issued: IssuedSession) -> TokenOut:
    return TokenOut(
        access_token=issued.access_token,
        expires_at=issued.access_expires_at,
        user=me_out(issued.principal),
    )


def _client(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


@router.post("/login", response_model=TokenOut, dependencies=[Depends(public)], summary="Sign in")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenOut:
    """Returns a 15-minute access token and sets the httpOnly refresh cookie.
    401 `invalid_credentials`; 423 `account_locked` after repeated failures."""
    ua, ip = _client(request)
    issued = await service.login(
        session, settings, body.username, body.password, user_agent=ua, ip=ip
    )
    set_refresh_cookie(response, settings, issued)
    return token_out(issued)


@router.post(
    "/refresh",
    response_model=TokenOut,
    dependencies=[Depends(public)],
    summary="Renew the access token",
)
async def refresh(
    request: Request, response: Response, session: SessionDep, settings: SettingsDep
) -> TokenOut:
    """Rotates the refresh cookie. Presenting an already-rotated cookie ends the session."""
    ua, ip = _client(request)
    try:
        issued = await service.refresh(
            session, settings, request.cookies.get(REFRESH_COOKIE), user_agent=ua, ip=ip
        )
    except service.AuthError:
        response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
        raise
    set_refresh_cookie(response, settings, issued)
    return token_out(issued)


@router.post("/logout", status_code=204, dependencies=[Depends(public)], summary="Sign out")
async def logout(request: Request, response: Response, session: SessionDep) -> Response:
    await service.logout(session, request.cookies.get(REFRESH_COOKIE), None)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut, summary="Current user")
async def me(principal: Annotated[Principal, Depends(authenticated)]) -> MeOut:
    return me_out(principal)


@router.post("/change-password", response_model=TokenOut, summary="Change own password")
async def change_password(
    body: ChangePasswordRequest,
    principal: Annotated[Principal, Depends(authenticated)],
    session: SessionDep,
    settings: SettingsDep,
) -> TokenOut:
    """Also ends the user's other sessions. Returns a fresh access token for this one."""
    issued = await service.change_password(
        session, settings, principal, body.current_password, body.new_password
    )
    assert issued is not None
    return token_out(issued)
