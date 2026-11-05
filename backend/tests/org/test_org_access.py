from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DivisionFactory, ModuleFactory, ProjectFactory, create, login, make_user


async def test_scoped_manager_writes_only_inside_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    div_a = await create(db_session, DivisionFactory, code="ACC-A")
    div_b = await create(db_session, DivisionFactory, code="ACC-B")
    pa = await create(db_session, ProjectFactory, division_id=div_a.id)
    pb = await create(db_session, ProjectFactory, division_id=div_b.id)
    mb = await create(db_session, ModuleFactory, project_id=pb.id)
    await make_user(
        db_session, "pm_a", roles=("project_manager",), scopes=(("division", div_a.id),)
    )
    h = await login(client, "pm_a")

    ok = await client.post(
        f"/api/projects/{pa.id}/modules",
        headers=h,
        json={"code": "IN", "name": "In scope", "qty_to_deliver": 1},
    )
    assert ok.status_code == 201
    for method, url, body in [
        (
            "POST",
            f"/api/projects/{pb.id}/modules",
            {"code": "OUT", "name": "x", "qty_to_deliver": 1},
        ),
        ("PATCH", f"/api/projects/{pb.id}", {"row_version": 1, "name": "hijack"}),
        ("PATCH", f"/api/modules/{mb.id}", {"row_version": 1, "name": "hijack"}),
        (
            "POST",
            f"/api/modules/{mb.id}/assemblies",
            {"code": "X", "board_name": "x", "revision": "A"},
        ),
        ("POST", f"/api/projects/{pb.id}/clone", {"name": "copy"}),
        ("GET", f"/api/projects/{pb.id}/tree", None),
        ("GET", f"/api/projects/{pb.id}/history", None),
    ]:
        r = await client.request(method, url, json=body, headers=h)
        assert r.status_code == 404, (method, url, r.status_code)
    # Creating a project in another division is also invisible to them.
    r = await client.post(
        "/api/projects",
        headers=h,
        json={"division_id": str(div_b.id), "name": "x", "client_name": "y"},
    )
    assert r.status_code == 404
    # Moving an in-scope project into another division is refused the same way.
    r = await client.patch(
        f"/api/projects/{pa.id}", headers=h, json={"row_version": 1, "division_id": str(div_b.id)}
    )
    assert r.status_code == 404
    # Scoped users may not create divisions.
    r = await client.post("/api/divisions", headers=h, json={"code": "NEW", "name": "x"})
    assert r.status_code == 403


async def test_read_only_roles_cannot_write(client: AsyncClient, db_session: AsyncSession) -> None:
    div = await create(db_session, DivisionFactory)
    project = await create(db_session, ProjectFactory, division_id=div.id)
    for role in ("viewer", "stores", "qc_inspector"):
        await make_user(db_session, f"ro_{role}", roles=(role,))
        h = await login(client, f"ro_{role}")
        assert (await client.get(f"/api/projects/{project.id}", headers=h)).status_code == 200
        for method, url, body in [
            (
                "POST",
                "/api/projects",
                {"division_id": str(div.id), "name": "x", "client_name": "y"},
            ),
            ("PATCH", f"/api/projects/{project.id}", {"row_version": 1, "name": "x"}),
            (
                "POST",
                f"/api/projects/{project.id}/modules",
                {"code": "M", "name": "x", "qty_to_deliver": 1},
            ),
            ("POST", f"/api/projects/{project.id}/clone", {"name": "copy"}),
            ("POST", "/api/divisions", {"code": "D", "name": "x"}),
        ]:
            r = await client.request(method, url, json=body, headers=h)
            assert r.status_code == 403, (role, method, url, r.status_code)
    viewer = await login(client, "ro_viewer")
    assert (
        await client.get(f"/api/projects/{project.id}/history", headers=viewer)
    ).status_code == 403
