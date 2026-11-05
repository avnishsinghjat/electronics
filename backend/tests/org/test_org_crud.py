from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.org.models import Project
from app.seed import seed_reference_data
from tests.factories import login, make_user


async def _admin(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    await seed_reference_data(db)
    await make_user(db, "org_admin")
    return await login(client, "org_admin")


async def _division(client: AsyncClient, h: dict[str, str], code: str = "IND") -> dict[str, Any]:
    r = await client.post(
        "/api/divisions", headers=h, json={"code": code, "name": f"{code} division"}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_full_structure_crud(client: AsyncClient, db_session: AsyncSession) -> None:
    h = await _admin(client, db_session)
    div = await _division(client, h)
    pm = await make_user(db_session, "pm_priya", roles=("project_manager",))
    r = await client.post(
        "/api/projects",
        headers=h,
        json={
            "division_id": div["id"],
            "name": "PLC Rack",
            "client_name": "Sahyadri Controls",
            "client_po_ref": "SC/118",
            "start_date": "2026-11-01",
            "due_date": "2026-12-31",
            "status": "active",
            "project_manager_id": str(pm.id),
        },
    )
    assert r.status_code == 201, r.text
    project = r.json()
    assert project["code"].startswith("PRJ-") and project["status"] == "active"

    m = await client.post(
        f"/api/projects/{project['id']}/modules",
        headers=h,
        json={"code": "MOD-CPU", "name": "CPU module", "qty_to_deliver": 25},
    )
    assert m.status_code == 201, m.text
    module = m.json()
    a = await client.post(
        f"/api/modules/{module['id']}/assemblies",
        headers=h,
        json={
            "code": "CPU1",
            "board_name": "PLC CPU board",
            "revision": "B",
            "layer_count": 4,
            "size_x_mm": "100.5",
            "size_y_mm": "80",
            "finish": "ENIG",
        },
    )
    assert a.status_code == 201, a.text
    assembly = a.json()
    assert assembly["stage_template_id"] is not None  # default template applied
    assert Decimal(assembly["size_x_mm"]) == Decimal("100.5")

    tree = (await client.get(f"/api/projects/{project['id']}/tree", headers=h)).json()
    assert tree["project"]["project_manager_name"] == "Test User"
    assert tree["project"]["module_count"] == 1
    assert tree["modules"][0]["assemblies"][0]["code"] == "CPU1"

    upd = await client.patch(
        f"/api/projects/{project['id']}",
        headers=h,
        json={"row_version": 1, "status": "on_hold", "notes": "Waiting for client approval"},
    )
    assert (
        upd.status_code == 200
        and upd.json()["status"] == "on_hold"
        and upd.json()["row_version"] == 2
    )
    stale = await client.patch(
        f"/api/projects/{project['id']}", headers=h, json={"row_version": 1, "name": "Stale"}
    )
    assert stale.status_code == 409

    upd_a = await client.patch(
        f"/api/assemblies/{assembly['id']}",
        headers=h,
        json={"row_version": 1, "revision": "C", "layer_count": 6},
    )
    assert upd_a.status_code == 200 and upd_a.json()["revision"] == "C"
    upd_m = await client.patch(
        f"/api/modules/{module['id']}", headers=h, json={"row_version": 1, "qty_to_deliver": 30}
    )
    assert upd_m.json()["qty_to_deliver"] == 30

    # Delete order is enforced: children first.
    blocked = await client.delete(f"/api/projects/{project['id']}?row_version=2", headers=h)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "has_children"
    assert (await client.delete(f"/api/modules/{module['id']}?row_version=2", headers=h)).json()[
        "error"
    ]["code"] == "has_children"
    assert (
        await client.delete(f"/api/assemblies/{assembly['id']}?row_version=2", headers=h)
    ).status_code == 204
    assert (
        await client.delete(f"/api/modules/{module['id']}?row_version=2", headers=h)
    ).status_code == 204
    assert (
        await client.delete(f"/api/projects/{project['id']}?row_version=2", headers=h)
    ).status_code == 204
    assert (await client.get(f"/api/projects/{project['id']}", headers=h)).status_code == 404
    assert (
        await client.delete(f"/api/divisions/{div['id']}?row_version=1", headers=h)
    ).status_code == 204

    actions = (
        await db_session.execute(
            select(AuditLog.entity_type, AuditLog.action).where(
                AuditLog.entity_type.in_(["projects", "modules", "pcb_assemblies", "divisions"])
            )
        )
    ).all()
    for entity in ("projects", "modules", "pcb_assemblies", "divisions"):
        assert (entity, "insert") in actions and (entity, "soft_delete") in actions, entity


async def test_validation_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    h = await _admin(client, db_session)
    div = await _division(client, h)
    base = {"division_id": div["id"], "name": "X", "client_name": "C"}
    bad_dates = await client.post(
        "/api/projects",
        headers=h,
        json={**base, "start_date": "2026-05-01", "due_date": "2026-04-01"},
    )
    assert bad_dates.status_code == 422
    bad_status = await client.post("/api/projects", headers=h, json={**base, "status": "exploded"})
    assert bad_status.status_code == 422
    inactive = await make_user(db_session, "gone_pm", roles=("project_manager",), is_active=False)
    bad_pm = await client.post(
        "/api/projects", headers=h, json={**base, "project_manager_id": str(inactive.id)}
    )
    assert bad_pm.status_code == 422 and bad_pm.json()["error"]["code"] == "invalid_manager"
    missing_div = await client.post(
        "/api/projects",
        headers=h,
        json={**base, "division_id": "00000000-0000-0000-0000-000000000009"},
    )
    assert missing_div.status_code == 404

    p = (await client.post("/api/projects", headers=h, json=base)).json()
    upd_dates = await client.patch(
        f"/api/projects/{p['id']}",
        headers=h,
        json={"row_version": 1, "due_date": "2020-01-01", "start_date": "2021-01-01"},
    )
    assert upd_dates.status_code == 422
    m1 = await client.post(
        f"/api/projects/{p['id']}/modules",
        headers=h,
        json={"code": "M1", "name": "M", "qty_to_deliver": 1},
    )
    assert m1.status_code == 201
    dup = await client.post(
        f"/api/projects/{p['id']}/modules",
        headers=h,
        json={"code": "M1", "name": "M again", "qty_to_deliver": 1},
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate"
    neg = await client.post(
        f"/api/projects/{p['id']}/modules",
        headers=h,
        json={"code": "M2", "name": "M", "qty_to_deliver": -1},
    )
    assert neg.status_code == 422
    mid = m1.json()["id"]
    bad_layers = await client.post(
        f"/api/modules/{mid}/assemblies",
        headers=h,
        json={"code": "A", "board_name": "B", "revision": "A", "layer_count": 99},
    )
    assert bad_layers.status_code == 422
    ok = await client.post(
        f"/api/modules/{mid}/assemblies",
        headers=h,
        json={"code": "A", "board_name": "B", "revision": "A"},
    )
    assert ok.status_code == 201
    same_rev = await client.post(
        f"/api/modules/{mid}/assemblies",
        headers=h,
        json={"code": "A", "board_name": "B", "revision": "A"},
    )
    assert same_rev.status_code == 409
    new_rev = await client.post(
        f"/api/modules/{mid}/assemblies",
        headers=h,
        json={"code": "A", "board_name": "B", "revision": "B"},
    )
    assert new_rev.status_code == 201
    bad_template = await client.patch(
        f"/api/assemblies/{ok.json()['id']}",
        headers=h,
        json={"row_version": 1, "stage_template_id": "00000000-0000-0000-0000-000000000009"},
    )
    assert bad_template.status_code == 422
    dup_div = await client.post(
        "/api/divisions", headers=h, json={"code": div["code"], "name": "dup"}
    )
    assert dup_div.status_code == 409
    has_projects = await client.delete(f"/api/divisions/{div['id']}?row_version=1", headers=h)
    assert has_projects.status_code == 409


async def test_project_list_filters_grouping_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    h = await _admin(client, db_session)
    a = await _division(client, h, "AAA")
    b = await _division(client, h, "BBB")
    pm = await make_user(db_session, "pm_list", roles=("project_manager",))

    async def mk(div: dict[str, Any], name: str, **extra: Any) -> dict[str, Any]:
        r = await client.post(
            "/api/projects",
            headers=h,
            json={
                "division_id": div["id"],
                "name": name,
                "client_name": extra.pop("client", "Acme"),
                **extra,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    await mk(a, "Overdue job", due_date="2020-01-31", status="active")
    await mk(a, "Done job", due_date="2020-01-31", status="completed")
    await mk(
        b,
        "Future job",
        due_date="2099-01-01",
        status="draft",
        client="Konkan E-Mobility",
        project_manager_id=str(pm.id),
    )

    async def names(qs: str) -> list[str]:
        r = await client.get(f"/api/projects?page_size=500&sort=name{qs}", headers=h)
        assert r.status_code == 200, r.text
        return [p["name"] for p in r.json()["items"]]

    assert await names("&overdue=true") == ["Overdue job"]
    assert await names(f"&division_id={b['id']}") == ["Future job"]
    assert await names(f"&project_manager_id={pm.id}") == ["Future job"]
    assert await names("&client=konkan") == ["Future job"]
    assert await names("&status=active,completed") == ["Done job", "Overdue job"]
    assert await names("&due_after=2050-01-01") == ["Future job"]
    assert await names("&due_before=2021-01-01") == ["Done job", "Overdue job"]
    item = (await client.get(f"/api/projects?division_id={b['id']}", headers=h)).json()["items"][0]
    assert (
        item["division_code"] == "BBB"
        and item["project_manager_name"] == "Test User"
        and item["module_count"] == 0
    )
    assert (await client.get("/api/projects?sort=-nope", headers=h)).status_code == 400


async def test_lookups(client: AsyncClient, db_session: AsyncSession) -> None:
    h = await _admin(client, db_session)
    templates = (await client.get("/api/stage-templates", headers=h)).json()
    assert templates[0]["name"] == "Standard PCBA" and templates[0]["is_default"] is True
    await make_user(db_session, "dir_person", roles=("stores",))
    await make_user(db_session, "dir_gone", roles=("stores",), is_active=False)
    names = [u["username"] for u in (await client.get("/api/directory/users", headers=h)).json()]
    assert "dir_person" in names and "dir_gone" not in names
    viewer = await make_user(db_session, "dir_viewer", roles=("viewer",))
    vh = await login(client, viewer.username)
    assert (await client.get("/api/directory/users", headers=vh)).status_code == 403
    assert db_session is not None and Project is not None
