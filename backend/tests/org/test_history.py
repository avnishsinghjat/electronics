import io

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DivisionFactory, create, login, make_user


async def test_history_covers_the_project_subtree(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    div = await create(db_session, DivisionFactory)
    await make_user(db_session, "hist_pm", roles=("project_manager",))
    h = await login(client, "hist_pm")
    project = (
        await client.post(
            "/api/projects",
            headers=h,
            json={"division_id": str(div.id), "name": "History", "client_name": "C"},
        )
    ).json()
    module = (
        await client.post(
            f"/api/projects/{project['id']}/modules",
            headers=h,
            json={"code": "M1", "name": "M", "qty_to_deliver": 1},
        )
    ).json()
    asm = (
        await client.post(
            f"/api/modules/{module['id']}/assemblies",
            headers=h,
            json={"code": "A1", "board_name": "B", "revision": "A"},
        )
    ).json()
    f = await client.post(
        "/api/files",
        headers=h,
        data={"ref_type": "assembly", "ref_id": asm["id"]},
        files={"file": ("gerbers.zip", io.BytesIO(b"PK\x03\x04zip"), "application/zip")},
    )
    assert f.status_code == 201
    await client.patch(
        f"/api/projects/{project['id']}", headers=h, json={"row_version": 1, "status": "active"}
    )

    history = (await client.get(f"/api/projects/{project['id']}/history", headers=h)).json()
    labels = [(e["label"], e["action"]) for e in history]
    assert labels[0] == (f"Project {project['code']}", "update")
    assert history[0]["changed_fields"] == ["status"]
    assert history[0]["actor_name"] == "Test User"
    assert ("File gerbers.zip", "insert") in labels
    assert ("Assembly A1 rev A", "insert") in labels
    assert ("Module M1", "insert") in labels
    assert labels[-1] == (f"Project {project['code']}", "insert")
