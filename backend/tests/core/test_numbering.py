import asyncio
import re
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.errors import AppError, NotFoundError
from app.core.numbering import (
    DEFAULT_DOC_TYPES,
    DocumentNumberConfig,
    DocumentSequence,
    format_number,
    next_number,
    set_prefix,
)


async def test_default_doc_types_installed_by_migration(db_session: AsyncSession) -> None:
    for code in DEFAULT_DOC_TYPES:
        assert await db_session.get(DocumentNumberConfig, code) is not None


async def test_format_and_sequence(db_session: AsyncSession) -> None:
    first = await next_number(db_session, "PO", year=2031)
    second = await next_number(db_session, "PO", year=2031)
    assert first == "PO-2031-0001"
    assert second == "PO-2031-0002"
    # yearly reset
    assert await next_number(db_session, "PO", year=2032) == "PO-2032-0001"


async def test_prefix_is_configurable(db_session: AsyncSession) -> None:
    await set_prefix(db_session, "GRN", "gr")
    assert await next_number(db_session, "GRN", year=2033) == "GR-2033-0001"
    with pytest.raises(AppError):
        await set_prefix(db_session, "GRN", "bad prefix!")
    with pytest.raises(NotFoundError):
        await set_prefix(db_session, "NOPE", "X")


async def test_unknown_doc_type(db_session: AsyncSession) -> None:
    with pytest.raises(NotFoundError):
        await next_number(db_session, "NOPE")


def test_format_without_yearly_reset() -> None:
    assert format_number("SN", 2026, 42, 6, yearly=False) == "SN-000042"


async def test_rolled_back_number_is_reissued(db_session: AsyncSession) -> None:
    async with db_session.begin_nested() as sp:
        assert await next_number(db_session, "NCR", year=2034) == "NCR-2034-0001"
        await sp.rollback()
    assert await next_number(db_session, "NCR", year=2034) == "NCR-2034-0001"


@pytest.fixture
async def doc_type(engine: AsyncEngine) -> str:  # type: ignore[misc]
    code = f"T{uuid.uuid4().hex[:8].upper()}"
    async with AsyncSession(engine) as s, s.begin():
        s.add(
            DocumentNumberConfig(
                doc_type=code, description="concurrency test", prefix=code, padding=4
            )
        )
    yield code
    async with AsyncSession(engine) as s, s.begin():
        await s.execute(delete(DocumentSequence).where(DocumentSequence.doc_type == code))
        await s.execute(delete(DocumentNumberConfig).where(DocumentNumberConfig.doc_type == code))


async def test_200_concurrent_requests_unique_and_gap_free(
    test_database_url: str, doc_type: str
) -> None:
    eng = create_async_engine(test_database_url, pool_size=25, max_overflow=0)
    maker = async_sessionmaker(eng, expire_on_commit=False)

    async def one(i: int) -> str | None:
        async with maker() as session, session.begin():
            number = await next_number(session, doc_type, year=2026)
            if i % 10 == 0:
                await session.rollback()  # every 10th caller aborts: its number must be reused
                return None
            return number

    try:
        results = await asyncio.gather(*(one(i) for i in range(220)))
    finally:
        await eng.dispose()
    issued = [r for r in results if r is not None]
    assert len(issued) == 198
    assert len(set(issued)) == 198
    values = sorted(int(n.rsplit("-", 1)[1]) for n in issued)
    assert values == list(range(1, 199))  # gap-free
    assert all(re.fullmatch(rf"{doc_type}-2026-\d{{4}}", n) for n in issued)
