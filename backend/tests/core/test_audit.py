import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.context import acting_as
from app.core.repository import Repository
from app.modules.org.models import Division
from tests.factories import DivisionFactory, create, make_user


class DivisionRepo(Repository[Division]):
    model = Division


async def _audit(session: AsyncSession, entity_id: uuid.UUID) -> list[AuditLog]:
    rows = await session.execute(
        select(AuditLog).where(AuditLog.entity_id == str(entity_id)).order_by(AuditLog.id)
    )
    return list(rows.scalars())


async def test_insert_writes_after_image_and_actor(db_session: AsyncSession) -> None:
    actor = (await make_user(db_session)).id
    with acting_as(actor):
        division = await create(db_session, DivisionFactory, code="AUD-1", name="Audit test")
    [row] = await _audit(db_session, division.id)
    assert row.action == "insert"
    assert row.actor_id == actor
    assert row.entity_type == "divisions"
    assert row.before is None
    assert row.after is not None
    assert row.after["code"] == "AUD-1"
    assert row.after["name"] == "Audit test"
    assert row.after["row_version"] == 1
    assert row.after["created_by"] == str(actor)
    assert division.created_by == actor
    assert division.updated_by == actor


async def test_update_writes_before_and_after(db_session: AsyncSession) -> None:
    division = await create(db_session, DivisionFactory, code="AUD-2", name="Old name")
    editor = (await make_user(db_session)).id
    with acting_as(editor):
        await DivisionRepo(db_session).update(division, {"name": "New name"}, expected_version=1)
    rows = await _audit(db_session, division.id)
    assert [r.action for r in rows] == ["insert", "update"]
    upd = rows[1]
    assert upd.actor_id == editor
    assert upd.changed_fields == ["name"]
    assert upd.before is not None and upd.after is not None
    assert upd.before["name"] == "Old name"
    assert upd.after["name"] == "New name"
    assert upd.before["row_version"] == 1
    assert upd.after["row_version"] == 2
    assert upd.after["updated_by"] == str(editor)
    assert upd.before["code"] == upd.after["code"] == "AUD-2"


async def test_soft_delete_and_restore_are_audited(db_session: AsyncSession) -> None:
    repo = DivisionRepo(db_session)
    division = await create(db_session, DivisionFactory, code="AUD-3")
    await repo.soft_delete(division, expected_version=1)
    await repo.restore(division, expected_version=2)
    rows = await _audit(db_session, division.id)
    assert [r.action for r in rows] == ["insert", "soft_delete", "restore"]
    soft = rows[1]
    assert soft.before is not None and soft.after is not None
    assert soft.before["is_deleted"] is False
    assert soft.after["is_deleted"] is True
    assert soft.changed_fields == ["is_deleted"]


async def test_hard_delete_writes_before_image(db_session: AsyncSession) -> None:
    division = await create(db_session, DivisionFactory, code="AUD-4")
    await db_session.delete(division)
    await db_session.flush()
    rows = await _audit(db_session, division.id)
    assert rows[-1].action == "delete"
    assert rows[-1].after is None
    assert rows[-1].before is not None and rows[-1].before["code"] == "AUD-4"


async def test_noop_update_writes_nothing(db_session: AsyncSession) -> None:
    division = await create(db_session, DivisionFactory, code="AUD-5", name="Same")
    division.name = "Same"
    await db_session.flush()
    assert [r.action for r in await _audit(db_session, division.id)] == ["insert"]


async def test_audit_row_rolls_back_with_the_change(db_session: AsyncSession) -> None:
    async with db_session.begin_nested() as sp:
        division = await create(db_session, DivisionFactory, code="AUD-6")
        division_id = division.id
        await sp.rollback()
    assert await _audit(db_session, division_id) == []
