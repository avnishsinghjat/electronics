"""Proves the test harness itself: migrated database and per-test rollback."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_database_is_migrated_to_head(db_session: AsyncSession) -> None:
    version = (await db_session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    assert version == "0001"


async def test_server_is_postgres_16_or_newer(db_session: AsyncSession) -> None:
    num = (await db_session.execute(text("SHOW server_version_num"))).scalar_one()
    assert int(num) >= 160000


async def _insert_and_count(session: AsyncSession) -> int:
    await session.execute(text("INSERT INTO _harness_probe (note) VALUES ('x')"))
    await session.commit()  # services commit; the harness must still roll it back
    return int((await session.execute(text("SELECT count(*) FROM _harness_probe"))).scalar_one())


async def test_rollback_isolation_first(db_session: AsyncSession) -> None:
    # Run in either order, both tests only pass if the other's committed row was rolled back.
    assert await _insert_and_count(db_session) == 1


async def test_rollback_isolation_second(db_session: AsyncSession) -> None:
    assert await _insert_and_count(db_session) == 1
