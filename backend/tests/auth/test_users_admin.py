from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from tests.factories import login, make_user, project_tree


async def _admin(client: AsyncClient, db_session: AsyncSession) -> dict[str, str]:
    await make_user(db_session, "boss", roles=("admin",))
    return await login(client, "boss")


async def test_create_user_returns_temp_password_and_forces_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _admin(client, db_session)
    tree = await project_tree(db_session)
    resp = await client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "priya.pm",
            "full_name": "Priya",
            "email": "priya@example.com",
            "roles": ["project_manager"],
            "scopes": [{"scope_type": "project", "scope_id": str(tree["project"].id)}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    temp = body["temporary_password"]
    assert len(temp) == 19 and temp.count("-") == 3
    assert body["user"]["must_change_password"] is True
    assert body["user"]["roles"] == ["project_manager"]
    assert body["user"]["scopes"] == [
        {"scope_type": "project", "scope_id": str(tree["project"].id)}
    ]
    client.cookies.clear()
    first = await client.post("/api/auth/login", json={"username": "priya.pm", "password": temp})
    assert first.status_code == 200 and first.json()["user"]["must_change_password"] is True


async def test_create_user_validation(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin(client, db_session)
    dup = await client.post(
        "/api/users",
        headers=headers,
        json={"username": "BOSS", "full_name": "X", "roles": ["viewer"]},
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate"
    bad_scope = await client.post(
        "/api/users",
        headers=headers,
        json={
            "username": "x_y",
            "full_name": "X",
            "roles": ["viewer"],
            "scopes": [
                {"scope_type": "project", "scope_id": "00000000-0000-0000-0000-000000000001"}
            ],
        },
    )
    assert bad_scope.status_code == 422 and bad_scope.json()["error"]["code"] == "invalid_scope"
    no_roles = await client.post(
        "/api/users", headers=headers, json={"username": "x_z", "full_name": "X", "roles": []}
    )
    assert no_roles.status_code == 422
    bad_name = await client.post(
        "/api/users",
        headers=headers,
        json={"username": "has space", "full_name": "X", "roles": ["viewer"]},
    )
    assert bad_name.status_code == 422


async def test_edit_roles_and_scopes_with_optimistic_lock(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _admin(client, db_session)
    tree = await project_tree(db_session)
    target = await make_user(db_session, "editme", roles=("viewer",))
    resp = await client.patch(
        f"/api/users/{target.id}",
        headers=headers,
        json={
            "row_version": 1,
            "roles": ["stores", "qc_inspector"],
            "scopes": [{"scope_type": "division", "scope_id": str(tree["division"].id)}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == ["qc_inspector", "stores"]
    assert resp.json()["row_version"] == 2
    stale = await client.patch(
        f"/api/users/{target.id}", headers=headers, json={"row_version": 1, "full_name": "Stale"}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_row_version"
    cleared = await client.patch(
        f"/api/users/{target.id}", headers=headers, json={"row_version": 2, "scopes": []}
    )
    assert cleared.json()["scopes"] == []
    actions = (
        await db_session.execute(
            select(AuditLog.entity_type, AuditLog.action).where(
                AuditLog.entity_type.in_(["user_roles", "user_scopes"])
            )
        )
    ).all()
    assert ("user_roles", "insert") in actions and ("user_roles", "delete") in actions
    assert ("user_scopes", "delete") in actions


async def test_last_admin_cannot_be_demoted_or_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _admin(client, db_session)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    demote = await client.patch(
        f"/api/users/{me['id']}", headers=headers, json={"row_version": 1, "roles": ["viewer"]}
    )
    assert demote.status_code == 409 and demote.json()["error"]["code"] == "last_admin"
    self_off = await client.post(
        f"/api/users/{me['id']}/deactivate", headers=headers, json={"row_version": 1}
    )
    assert self_off.status_code == 409 and self_off.json()["error"]["code"] == "self_deactivation"
    other_admin = await make_user(db_session, "admin2", roles=("admin",))
    ok = await client.post(
        f"/api/users/{other_admin.id}/deactivate", headers=headers, json={"row_version": 1}
    )
    assert ok.status_code == 200 and ok.json()["is_active"] is False


async def test_deactivate_ends_sessions_and_reactivate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _admin(client, db_session)
    target = await make_user(db_session, "temp_worker", roles=("stores",))
    worker_headers = await login(client, "temp_worker")
    off = await client.post(
        f"/api/users/{target.id}/deactivate", headers=headers, json={"row_version": 1}
    )
    assert off.status_code == 200
    assert (await client.get("/api/auth/me", headers=worker_headers)).status_code == 401
    assert (
        await client.post(
            "/api/auth/login", json={"username": "temp_worker", "password": "Factory-pass-2026"}
        )
    ).status_code == 401
    on = await client.post(
        f"/api/users/{target.id}/activate",
        headers=headers,
        json={"row_version": off.json()["row_version"]},
    )
    assert on.json()["is_active"] is True


async def test_reset_password_unlocks_and_forces_change(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _admin(client, db_session)
    target = await make_user(db_session, "forgetful", roles=("production",))
    for _ in range(5):
        await client.post(
            "/api/auth/login", json={"username": "forgetful", "password": "nope-nope-1"}
        )
    await db_session.refresh(target)
    assert target.locked_until is not None
    resp = await client.post(
        f"/api/users/{target.id}/reset-password",
        headers=headers,
        json={"row_version": target.row_version},
    )
    assert resp.status_code == 200, resp.text
    temp = resp.json()["temporary_password"]
    assert resp.json()["user"]["locked_until"] is None
    login_resp = await client.post(
        "/api/auth/login", json={"username": "forgetful", "password": temp}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["must_change_password"] is True


async def test_list_users_search_and_roles_catalogue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _admin(client, db_session)
    await make_user(db_session, "kavya.stores", roles=("stores",))
    await make_user(db_session, "inactive.one", roles=("viewer",), is_active=False)
    found = (await client.get("/api/users?q=kavya", headers=headers)).json()
    assert [u["username"] for u in found["items"]] == ["kavya.stores"]
    active = (await client.get("/api/users?active=false", headers=headers)).json()
    assert [u["username"] for u in active["items"]] == ["inactive.one"]
    roles = (await client.get("/api/users/roles", headers=headers)).json()
    assert {r["role"] for r in roles} == {
        "admin",
        "project_manager",
        "purchase",
        "stores",
        "production",
        "qc_inspector",
        "qc_lead",
        "engineer",
        "viewer",
    }
    perms = (await client.get("/api/users/permissions", headers=headers)).json()
    assert any(
        p["permission"] == "qc:approve_report" or p["permission"] == "reports:approve"
        for p in perms
    )
