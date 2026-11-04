import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import jobs
from app.core.errors import AppError
from app.core.jobs import Job, JobContext, JobStatus
from app.core.models import utcnow
from app.modules.org.models import Division

CALLS: list[dict[str, object]] = []


@jobs.job_handler("test.echo")
async def _echo(ctx: JobContext) -> dict[str, object]:
    CALLS.append(ctx.payload)
    ctx.session.add(Division(code=f"JOB-{uuid.uuid4().hex[:6]}", name=str(ctx.payload.get("name"))))
    return {"echo": ctx.payload, "attempt": ctx.attempt}


@jobs.job_handler("test.fail")
async def _fail(ctx: JobContext) -> None:
    ctx.session.add(Division(code=f"FAIL-{uuid.uuid4().hex[:6]}", name="must roll back"))
    await ctx.session.flush()
    raise ValueError(f"boom on attempt {ctx.attempt}")


@pytest.fixture
async def maker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    m = async_sessionmaker(engine, expire_on_commit=False)
    async with m() as s, s.begin():
        await s.execute(delete(Job))  # committed job tests share one queue
    yield m
    async with m() as s, s.begin():
        await s.execute(delete(Job))


async def _enqueue(maker: async_sessionmaker[AsyncSession], kind: str, **kw: object) -> uuid.UUID:
    async with maker() as s, s.begin():
        job = await jobs.enqueue(s, kind, kw.pop("payload", {}), **kw)  # type: ignore[arg-type]
        return job.id


async def test_enqueue_unknown_kind_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(AppError):
        await jobs.enqueue(db_session, "nope")
    assert "test.echo" in jobs.registered_kinds()


async def test_job_runs_and_records_result(maker: async_sessionmaker[AsyncSession]) -> None:
    job_id = await _enqueue(maker, "test.echo", payload={"name": "hello"})
    assert await jobs.run_one(maker, "w1") is True
    assert await jobs.run_one(maker, "w1") is False  # queue empty
    async with maker() as s:
        job = await s.get(Job, job_id)
    assert job is not None
    assert job.status == JobStatus.SUCCEEDED
    assert job.result == {"echo": {"name": "hello"}, "attempt": 1}
    assert job.progress == 100 and job.finished_at is not None and job.locked_by == "w1"


async def test_failure_rolls_back_work_and_retries_then_fails(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    job_id = await _enqueue(maker, "test.fail", max_attempts=2)
    assert await jobs.run_one(maker, "w1")
    async with maker() as s:
        job = await s.get(Job, job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED and job.attempts == 1
        assert "boom on attempt 1" in (job.error or "")
        assert job.run_after > utcnow()
        # make it due now
        await s.execute(update(Job).where(Job.id == job_id).values(run_after=utcnow()))
        await s.commit()
    assert await jobs.run_one(maker, "w1")
    async with maker() as s:
        job = await s.get(Job, job_id)
        assert job is not None and job.status == JobStatus.FAILED and job.attempts == 2
        from sqlalchemy import func, select

        leaked = (
            await s.execute(select(func.count()).where(Division.name == "must roll back"))
        ).scalar_one()
        assert leaked == 0


async def test_two_workers_never_claim_the_same_job(
    maker: async_sessionmaker[AsyncSession],
) -> None:
    for i in range(6):
        await _enqueue(maker, "test.echo", payload={"name": f"n{i}"})
    claimed: list[uuid.UUID] = []

    async def claimer(worker: str) -> None:
        while True:
            async with maker() as s:
                job = await jobs.claim_next(s, worker)
                if job is None:
                    return
                claimed.append(job.id)

    await asyncio.gather(claimer("a"), claimer("b"), claimer("c"))
    assert len(claimed) == 6 == len(set(claimed))


async def test_stale_running_job_is_reclaimed(maker: async_sessionmaker[AsyncSession]) -> None:
    job_id = await _enqueue(maker, "test.echo")
    async with maker() as s:
        job = await jobs.claim_next(s, "dead-worker")
        assert job is not None
    async with maker() as s:
        assert await jobs.claim_next(s, "w2") is None  # lease still valid
    async with maker() as s:
        await s.execute(
            update(Job).where(Job.id == job_id).values(locked_at=utcnow() - timedelta(hours=1))
        )
        await s.commit()
    async with maker() as s:
        again = await jobs.claim_next(s, "w2")
        assert again is not None and again.id == job_id and again.attempts == 2


async def test_cancel_only_queued(maker: async_sessionmaker[AsyncSession]) -> None:
    job_id = await _enqueue(maker, "test.echo")
    async with maker() as s, s.begin():
        assert (await jobs.cancel(s, job_id)).status == JobStatus.CANCELLED
    async with maker() as s, s.begin():
        with pytest.raises(AppError):
            await jobs.cancel(s, job_id)
    assert await jobs.run_one(maker, "w1") is False


def test_duplicate_handler_registration_rejected() -> None:
    with pytest.raises(ValueError, match="already registered"):

        @jobs.job_handler("test.echo")
        async def _other(ctx: JobContext) -> None:
            return None


def test_backoff_is_capped() -> None:
    assert jobs.backoff(1) == timedelta(seconds=10)
    assert jobs.backoff(20) == timedelta(seconds=600)
