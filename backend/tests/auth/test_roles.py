"""Table-driven: every role tries every protected endpoint; allowed iff the role matrix
grants the endpoint's permission. Checked at the API and at the service layer."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDeniedError
from app.core.permissions import ROLE_PERMISSIONS, Role
from app.modules.auth.service import load_principal
from app.modules.settings.models import CompanySettings
from app.modules.users import service as users_service
from app.modules.users.schemas import UserCreate
from tests.factories import login, make_user, project_tree

# (method, path, json body, permission)
CASES: list[tuple[str, str, dict[str, Any] | None, str]] = [
    ("GET", "/api/users", None, "users:read"),
    ("GET", "/api/users/roles", None, "users:read"),
    (
        "POST",
        "/api/users",
        {"username": "x_new", "full_name": "X", "roles": ["viewer"]},
        "users:manage",
    ),
    ("GET", "/api/audit", None, "audit:read"),
    ("GET", "/api/settings/company", None, "settings:read"),
    ("GET", "/api/settings/numbering", None, "settings:read"),
    ("PUT", "/api/settings/numbering/PO", {"prefix": "PUR"}, "settings:manage"),
    ("PUT", "/api/settings/company", {"row_version": 1, "company_name": "Acme"}, "settings:manage"),
    ("GET", "/api/projects", None, "projects:read"),
    ("GET", "/api/divisions", None, "projects:read"),
]


@pytest.mark.parametrize("role", list(Role))
async def test_role_can_and_cannot(
    client: AsyncClient, db_session: AsyncSession, role: Role
) -> None:
    db_session.add(CompanySettings(company_name="Test Co"))
    await project_tree(db_session)
    user = await make_user(db_session, f"r_{role.value}", roles=(role.value,))
    headers = await login(client, user.username)
    results = {}
    for method, path, body, perm in CASES:
        resp = await client.request(method, path, json=body, headers=headers)
        allowed = perm in ROLE_PERMISSIONS[role]
        results[(method, path)] = resp.status_code
        if allowed:
            assert resp.status_code != 403, (role, method, path, resp.text)
            assert resp.status_code < 500, (role, method, path, resp.text)
        else:
            assert resp.status_code == 403, (role, method, path, resp.status_code)
            assert resp.json()["error"] == {
                "code": "forbidden",
                "message": "You do not have permission to do this",
                "details": {"permission": perm},
            }
    assert results


async def test_user_with_two_roles_gets_the_union(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, "dual", roles=("viewer", "project_manager"))
    headers = await login(client, "dual")
    assert (await client.get("/api/users", headers=headers)).status_code == 200  # from PM
    assert (
        await client.post(
            "/api/users",
            headers=headers,
            json={"username": "zz_z", "full_name": "Z", "roles": ["viewer"]},
        )
    ).status_code == 403
    assert user.id


async def test_service_layer_enforces_permissions_without_the_router(
    db_session: AsyncSession, settings: Any
) -> None:
    viewer = await make_user(db_session, "svc_viewer", roles=("viewer",))
    principal = await load_principal(db_session, viewer)
    with pytest.raises(PermissionDeniedError):
        await users_service.create_user(
            db_session,
            settings,
            principal,
            UserCreate(username="sneaky", full_name="S", roles=[Role.ADMIN]),
        )
    with pytest.raises(PermissionDeniedError):
        await users_service.get_user(db_session, principal, uuid.uuid4())
