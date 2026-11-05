from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DivisionFactory, ProjectFactory, create, login, make_user


async def _two_divisions(session: AsyncSession) -> dict[str, Any]:
    div_a = await create(session, DivisionFactory, code="SCOPE-A")
    div_b = await create(session, DivisionFactory, code="SCOPE-B")
    a1 = await create(session, ProjectFactory, division_id=div_a.id, name="A1")
    a2 = await create(session, ProjectFactory, division_id=div_a.id, name="A2")
    b1 = await create(session, ProjectFactory, division_id=div_b.id, name="B1")
    return {"div_a": div_a, "div_b": div_b, "a1": a1, "a2": a2, "b1": b1}


async def test_project_scoped_user_gets_404_outside_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    w = await _two_divisions(db_session)
    await make_user(
        db_session, "scoped_pm", roles=("project_manager",), scopes=(("project", w["a1"].id),)
    )
    headers = await login(client, "scoped_pm")

    ok = await client.get(f"/api/projects/{w['a1'].id}", headers=headers)
    assert ok.status_code == 200 and ok.json()["name"] == "A1"
    for other in ("a2", "b1"):
        resp = await client.get(f"/api/projects/{w[other].id}", headers=headers)
        assert resp.status_code == 404, other
        assert resp.json()["error"]["code"] == "not_found"

    listed = (await client.get("/api/projects", headers=headers)).json()
    assert [p["name"] for p in listed["items"]] == ["A1"]
    assert listed["total"] == 1
    divisions = (await client.get("/api/divisions", headers=headers)).json()
    assert [d["code"] for d in divisions] == ["SCOPE-A"]


async def test_division_scope_includes_all_its_projects(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    w = await _two_divisions(db_session)
    await make_user(
        db_session, "div_viewer", roles=("viewer",), scopes=(("division", w["div_a"].id),)
    )
    headers = await login(client, "div_viewer")
    names = sorted(
        p["name"]
        for p in (await client.get("/api/projects?page_size=500", headers=headers)).json()["items"]
    )
    assert names == ["A1", "A2"]
    assert (await client.get(f"/api/projects/{w['b1'].id}", headers=headers)).status_code == 404


async def test_unscoped_and_admin_users_see_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    w = await _two_divisions(db_session)
    await make_user(db_session, "global_pm", roles=("project_manager",))
    # An admin with a scope row is still unrestricted.
    await make_user(db_session, "scoped_admin", roles=("admin",), scopes=(("project", w["a1"].id),))
    for name in ("global_pm", "scoped_admin"):
        headers = await login(client, name)
        resp = await client.get(f"/api/projects/{w['b1'].id}", headers=headers)
        assert resp.status_code == 200, name


async def test_project_filters_and_pagination(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    w = await _two_divisions(db_session)
    await make_user(db_session, "filt", roles=("viewer",))
    headers = await login(client, "filt")
    resp = await client.get(f"/api/projects?division_id={w['div_b'].id}", headers=headers)
    assert [p["name"] for p in resp.json()["items"]] == ["B1"]
    resp = await client.get("/api/projects?q=A&sort=name&page_size=1&page=2", headers=headers)
    body = resp.json()
    assert body["page"] == 2 and body["page_size"] == 1
    assert body["items"][0]["name"] in {"A1", "A2"}
    bad = await client.get("/api/projects?sort=-secret_column", headers=headers)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_query"
