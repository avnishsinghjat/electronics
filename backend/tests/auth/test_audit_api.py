from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import acting_as
from app.core.repository import Repository
from app.modules.org.models import Division
from tests.factories import DivisionFactory, create, login, make_user


class DivisionRepo(Repository[Division]):
    model = Division


async def test_audit_viewer_filters_and_diff(client: AsyncClient, db_session: AsyncSession) -> None:
    auditor = await make_user(db_session, "auditor", roles=("admin",))
    editor = await make_user(db_session, "editor", roles=("project_manager",))
    with acting_as(editor.id):
        division = await create(db_session, DivisionFactory, code="AUD-V", name="Before")
        await DivisionRepo(db_session).update(division, {"name": "After"}, expected_version=1)
    headers = await login(client, "auditor")

    resp = await client.get(
        f"/api/audit?entity_type=divisions&entity_id={division.id}", headers=headers
    )
    body = resp.json()
    assert body["total"] == 2
    latest = body["items"][0]
    assert latest["action"] == "update"
    assert latest["actor_username"] == "editor"
    assert latest["changed_fields"] == ["name"]
    assert latest["before"]["name"] == "Before" and latest["after"]["name"] == "After"

    by_actor = (
        await client.get(f"/api/audit?actor_id={editor.id}&entity_type=divisions", headers=headers)
    ).json()
    assert by_actor["total"] == 2
    inserts = (
        await client.get(f"/api/audit?entity_id={division.id}&action=insert", headers=headers)
    ).json()
    assert [i["action"] for i in inserts["items"]] == ["insert"]
    today = date.today()
    window = (
        await client.get(
            f"/api/audit?entity_id={division.id}&date_from={today - timedelta(days=1)}&date_to={today + timedelta(days=1)}",
            headers=headers,
        )
    ).json()
    assert window["total"] == 2
    past = (
        await client.get(
            f"/api/audit?entity_id={division.id}&date_to={today - timedelta(days=5)}",
            headers=headers,
        )
    ).json()
    assert past["total"] == 0
    bad = await client.get(
        f"/api/audit?date_from={today}&date_to={today - timedelta(days=1)}", headers=headers
    )
    assert bad.status_code == 400
    types = (await client.get("/api/audit/entity-types", headers=headers)).json()
    assert "divisions" in types and "users" in types
    assert auditor.id
