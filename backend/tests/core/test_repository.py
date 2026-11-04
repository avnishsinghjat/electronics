import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_session
from app.core.errors import ConflictError, NotFoundError
from app.core.repository import InvalidQueryError, Repository
from app.modules.org.models import Division
from tests.factories import DivisionFactory, create


class DivisionRepo(Repository[Division]):
    model = Division
    filterable = frozenset({"code", "name", "created_at"})
    sortable = frozenset({"code", "name", "created_at"})
    entity_label = "Division"


@pytest.fixture
async def divisions(db_session: AsyncSession) -> list[Division]:
    names = ["Alpha", "bravo", "Charlie", "delta", "Echo"]
    return [
        await create(db_session, DivisionFactory, code=f"R-{i}", name=n)
        for i, n in enumerate(names)
    ]


async def test_get_and_not_found(db_session: AsyncSession, divisions: list[Division]) -> None:
    repo = DivisionRepo(db_session)
    assert (await repo.get(divisions[0].id)).name == "Alpha"
    with pytest.raises(NotFoundError) as exc:
        await repo.get(uuid.uuid4())
    assert exc.value.message == "Division not found"


async def test_pagination_sorting_and_total(
    db_session: AsyncSession, divisions: list[Division]
) -> None:
    repo = DivisionRepo(db_session)
    filters = {"code__contains": "R-"}
    page1 = await repo.list(page=1, page_size=2, sort="code", filters=filters)
    page3 = await repo.list(page=3, page_size=2, sort="code", filters=filters)
    assert page1.total == 5 and page1.pages == 3
    assert [d.code for d in page1.items] == ["R-0", "R-1"]
    assert [d.code for d in page3.items] == ["R-4"]
    desc = await repo.list(sort="-code", filters=filters)
    assert [d.code for d in desc.items] == ["R-4", "R-3", "R-2", "R-1", "R-0"]


async def test_filters(db_session: AsyncSession, divisions: list[Division]) -> None:
    repo = DivisionRepo(db_session)
    assert [d.name for d in (await repo.list(filters={"name__contains": "ar"})).items] == [
        "Charlie"
    ]
    assert (await repo.list(filters={"code": "R-2"})).items[0].name == "Charlie"
    got = await repo.list(filters={"code__in": "R-1,R-3"}, sort="code")
    assert [d.code for d in got.items] == ["R-1", "R-3"]
    assert (await repo.list(filters={"code__ne": "R-1", "code__contains": "R-"})).total == 4
    assert (await repo.list(filters={"name__contains": "%"})).total == 0  # wildcard is escaped


async def test_non_whitelisted_filter_or_sort_rejected(db_session: AsyncSession) -> None:
    repo = DivisionRepo(db_session)
    with pytest.raises(InvalidQueryError):
        await repo.list(filters={"description": "x"})
    with pytest.raises(InvalidQueryError):
        await repo.list(sort="-description")
    with pytest.raises(InvalidQueryError):
        await repo.list(filters={"code__regex": "x"})
    with pytest.raises(InvalidQueryError):
        await repo.list(page_size=10_000)


async def test_soft_delete_hides_records(
    db_session: AsyncSession, divisions: list[Division]
) -> None:
    repo = DivisionRepo(db_session)
    await repo.soft_delete(divisions[1], expected_version=1)
    listed = await repo.list(filters={"code__contains": "R-"})
    assert listed.total == 4
    assert (await repo.list(filters={"code__contains": "R-"}, include_deleted=True)).total == 5
    with pytest.raises(NotFoundError):
        await repo.get(divisions[1].id)
    assert (await repo.get(divisions[1].id, include_deleted=True)).is_deleted


async def test_update_rejects_immutable_fields(
    db_session: AsyncSession, divisions: list[Division]
) -> None:
    with pytest.raises(InvalidQueryError):
        await DivisionRepo(db_session).update(
            divisions[0], {"id": uuid.uuid4()}, expected_version=1
        )


async def test_stale_row_version_raises_conflict(
    db_session: AsyncSession, divisions: list[Division]
) -> None:
    repo = DivisionRepo(db_session)
    await repo.update(divisions[0], {"name": "First edit"}, expected_version=1)
    with pytest.raises(ConflictError) as exc:
        await repo.update(divisions[0], {"name": "Second edit"}, expected_version=1)
    assert exc.value.status_code == 409
    assert exc.value.details == {"expected_row_version": 1, "current_row_version": 2}


async def test_concurrent_writers_second_gets_stale_data_conflict(engine: AsyncEngine) -> None:
    """Two sessions load the same row; the second commit fails (version_id_col)."""
    from sqlalchemy.orm.exc import StaleDataError

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s, s.begin():
        division = Division(code=f"CONC-{uuid.uuid4().hex[:6]}", name="v1")
        s.add(division)
    async with maker() as a, maker() as b:
        da = await a.get(Division, division.id)
        db_ = await b.get(Division, division.id)
        assert da is not None and db_ is not None
        da.name = "writer A"
        await a.commit()
        db_.name = "writer B"
        with pytest.raises(StaleDataError):
            await b.commit()


class _UpdateBody(BaseModel):
    name: str
    row_version: int


async def test_api_returns_409_on_stale_row_version(
    app: FastAPI, db_session: AsyncSession, divisions: list[Division]
) -> None:
    @app.patch("/api/_probe/divisions/{division_id}")
    async def patch_division(division_id: uuid.UUID, body: _UpdateBody) -> dict[str, object]:
        async for session in app.dependency_overrides[get_session]():
            repo = DivisionRepo(session)
            obj = await repo.update(
                await repo.get(division_id), {"name": body.name}, expected_version=body.row_version
            )
            return {"name": obj.name, "row_version": obj.row_version}
        raise AssertionError

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        url = f"/api/_probe/divisions/{divisions[0].id}"
        ok = await client.patch(url, json={"name": "A", "row_version": 1})
        assert ok.status_code == 200 and ok.json() == {"name": "A", "row_version": 2}
        stale = await client.patch(url, json={"name": "B", "row_version": 1})
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "stale_row_version"
        assert stale.json()["error"]["details"] == {
            "expected_row_version": 1,
            "current_row_version": 2,
        }
        missing = await client.patch(
            f"/api/_probe/divisions/{uuid.uuid4()}", json={"name": "C", "row_version": 1}
        )
        assert missing.status_code == 404
