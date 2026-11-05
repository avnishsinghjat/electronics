from datetime import timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.config import Settings
from app.core.models import utcnow
from app.core.security import REFRESH_COOKIE, create_access_token
from app.modules.auth.models import RefreshToken, User
from tests.factories import DEFAULT_PASSWORD, login, make_user


async def _login(client: AsyncClient, username: str, password: str = DEFAULT_PASSWORD) -> Any:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


# ---------------------------------------------------------------- login


async def test_login_success_returns_token_profile_and_httponly_cookie(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, "meena.qc", roles=("qc_inspector",))
    resp = await _login(client, "MEENA.QC")  # usernames are case-insensitive
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "meena.qc"
    assert body["user"]["roles"] == ["qc_inspector"]
    assert "qc:inspect" in body["user"]["permissions"]
    assert "users:manage" not in body["user"]["permissions"]
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{REFRESH_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/auth" in cookie
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200 and me.json()["id"] == str(user.id)
    await db_session.refresh(user)
    assert user.last_login_at is not None


@pytest.mark.parametrize(
    ("username", "password"), [("ravi", "wrong-password-1"), ("nobody", DEFAULT_PASSWORD)]
)
async def test_bad_credentials_same_generic_401(
    client: AsyncClient, db_session: AsyncSession, username: str, password: str
) -> None:
    await make_user(db_session, "ravi")
    resp = await _login(client, username, password)
    assert resp.status_code == 401
    assert resp.json()["error"] == {
        "code": "invalid_credentials",
        "message": "Invalid username or password",
        "details": None,
    }


async def test_inactive_user_cannot_login(client: AsyncClient, db_session: AsyncSession) -> None:
    await make_user(db_session, "gone", is_active=False)
    assert (await _login(client, "gone")).status_code == 401


async def test_lockout_after_five_failures_then_unlock(
    client: AsyncClient, db_session: AsyncSession, settings: Settings
) -> None:
    user = await make_user(db_session, "arjun")
    for i in range(4):
        resp = await _login(client, "arjun", "bad-pass-123")
        assert resp.status_code == 401, i
    fifth = await _login(client, "arjun", "bad-pass-123")
    assert fifth.status_code == 423
    assert fifth.json()["error"]["code"] == "account_locked"
    # Correct password is refused while locked.
    locked = await _login(client, "arjun")
    assert locked.status_code == 423
    assert "Try again in" in locked.json()["error"]["message"]
    # Once the lock expires the correct password works and the counter resets.
    await db_session.refresh(user)
    user.locked_until = utcnow() - timedelta(seconds=1)
    await db_session.flush()
    assert (await _login(client, "arjun")).status_code == 200
    await db_session.refresh(user)
    assert user.failed_logins == 0 and user.locked_until is None
    assert settings.max_failed_logins == 5


async def test_login_events_are_audited_without_bumping_row_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, "events")
    await _login(client, "events", "bad-pass-123")
    await _login(client, "events")
    await client.post("/api/auth/logout")
    rows = (
        (
            await db_session.execute(
                select(AuditLog.action)
                .where(AuditLog.entity_id == str(user.id))
                .order_by(AuditLog.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows == ["insert", "login_failed", "login", "logout"]
    await db_session.refresh(user)
    assert user.row_version == 1  # login bookkeeping does not version the record


async def test_password_hash_never_reaches_the_audit_log(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, "audited")
    headers = await login(client, "audited")
    await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "Changed-pass-2026"},
    )
    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == str(user.id), AuditLog.action.in_(["insert", "update"])
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    for row in rows:
        for image in (row.before, row.after):
            if image:
                assert image["password_hash"] == "[redacted]"


# ---------------------------------------------------------------- tokens


async def test_missing_tampered_and_expired_tokens_rejected(
    client: AsyncClient, db_session: AsyncSession, settings: Settings
) -> None:
    user = await make_user(db_session, "tok")
    assert (await client.get("/api/auth/me")).json()["error"]["code"] == "not_authenticated"
    headers = await login(client, "tok")
    token = headers["Authorization"].split()[1]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "invalid_token"
    forged = jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(user.id),
            "typ": "access",
            "iss": "fabtrack",
            "iat": 0,
            "exp": 9999999999,
        },
        "an-attacker-guessed-secret-of-32-chars!",
        algorithm="HS256",
    )
    assert (
        await client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    ).status_code == 401
    session_id = (
        await db_session.execute(
            select(RefreshToken.family_id).where(RefreshToken.user_id == user.id)
        )
    ).scalar_one()
    expired_settings = settings.model_copy(update={"access_token_minutes": 1})
    expired, _ = create_access_token(
        expired_settings, user_id=user.id, session_id=session_id, must_change_password=False
    )
    decoded = jwt.decode(
        expired, settings.secret_key, algorithms=["HS256"], options={"verify_exp": False}
    )
    decoded["exp"] = decoded["iat"] - 10
    stale = jwt.encode(decoded, settings.secret_key, algorithm="HS256")
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"})
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "token_expired"


async def test_refresh_rotates_cookie_and_detects_reuse(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, "rot")
    first = await _login(client, "rot")
    old_cookie = first.cookies[REFRESH_COOKIE]
    access1 = first.json()["access_token"]

    refreshed = await client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    new_cookie = refreshed.cookies[REFRESH_COOKIE]
    assert new_cookie != old_cookie
    access2 = refreshed.json()["access_token"]
    assert (
        await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access2}"})
    ).status_code == 200

    # Replaying the rotated cookie (e.g. stolen) ends the whole session.
    client.cookies.set(REFRESH_COOKIE, old_cookie, path="/api/auth")
    reuse = await client.post("/api/auth/refresh")
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "refresh_token_reused"
    for access in (access1, access2):
        resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert resp.json()["error"]["code"] == "session_revoked"
    client.cookies.set(REFRESH_COOKIE, new_cookie, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_refresh_without_cookie(client: AsyncClient) -> None:
    resp = await client.post("/api/auth/refresh")
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "no_session"


async def test_expired_refresh_token(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, "old")
    await _login(client, "old")
    token = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalar_one()
    token.expires_at = utcnow() - timedelta(minutes=1)
    await db_session.flush()
    resp = await client.post("/api/auth/refresh")
    assert resp.json()["error"]["code"] == "session_expired"


async def test_logout_revokes_session_and_clears_cookie(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, "bye")
    headers = await login(client, "bye")
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 204
    assert (
        f'{REFRESH_COOKIE}=""' in resp.headers["set-cookie"]
        or "Max-Age=0" in resp.headers["set-cookie"]
    )
    assert (await client.get("/api/auth/me", headers=headers)).json()["error"][
        "code"
    ] == "session_revoked"
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_deactivated_user_token_stops_working(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, "leaver")
    headers = await login(client, "leaver")
    user.is_active = False
    await db_session.flush()
    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "inactive_account"


# ---------------------------------------------------------------- passwords


async def test_forced_password_change_blocks_everything_else(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, "newbie", roles=("admin",), must_change_password=True)
    headers = await login(client, "newbie")
    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    blocked = await client.get("/api/users", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"

    changed = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "Brand-new-pass-77"},
    )
    assert changed.status_code == 200
    new_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert changed.json()["user"]["must_change_password"] is False
    assert (await client.get("/api/users", headers=new_headers)).status_code == 200
    assert (await _login(client, "newbie", "Brand-new-pass-77")).status_code == 200
    assert (await _login(client, "newbie")).status_code == 401


@pytest.mark.parametrize(
    ("current", "new", "code"),
    [
        ("wrong-current-1", "Brand-new-pass-77", "wrong_password"),
        (DEFAULT_PASSWORD, "short1", "weak_password"),
        (DEFAULT_PASSWORD, "onlyletterspassword", "weak_password"),
        (DEFAULT_PASSWORD, "pwuser-is-in-here-1", "weak_password"),
        (DEFAULT_PASSWORD, DEFAULT_PASSWORD, "weak_password"),
    ],
)
async def test_password_change_validation(
    client: AsyncClient, db_session: AsyncSession, current: str, new: str, code: str
) -> None:
    await make_user(db_session, "pwuser")
    headers = await login(client, "pwuser")
    resp = await client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": current, "new_password": new},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == code


async def test_password_change_ends_other_sessions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, "multi")
    laptop = await login(client, "multi")
    client.cookies.clear()
    tablet = await login(client, "multi")
    resp = await client.post(
        "/api/auth/change-password",
        headers=tablet,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "Another-pass-2026"},
    )
    assert resp.status_code == 200
    assert (await client.get("/api/auth/me", headers=laptop)).json()["error"][
        "code"
    ] == "session_revoked"
    assert (
        await client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
        )
    ).status_code == 200
    user = (await db_session.execute(select(User).where(User.username == "multi"))).scalar_one()
    await db_session.refresh(user)
    assert user.password_changed_at is not None
