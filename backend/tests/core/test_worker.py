import asyncio
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.worker import heartbeat_is_fresh, run, run_cycle, write_heartbeat


def test_heartbeat_roundtrip(tmp_path: Path) -> None:
    hb = tmp_path / "sub" / "hb"
    write_heartbeat(hb, db_ok=True)
    assert heartbeat_is_fresh(hb, max_age_s=5)


def test_heartbeat_with_db_error_is_unhealthy(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    write_heartbeat(hb, db_ok=False)
    assert not heartbeat_is_fresh(hb, max_age_s=5)


def test_stale_or_missing_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    assert not heartbeat_is_fresh(hb, max_age_s=5)
    hb.write_text(f"{time.time() - 100:.3f} db_ok\n")
    assert not heartbeat_is_fresh(hb, max_age_s=5)
    hb.write_text("garbage")
    assert not heartbeat_is_fresh(hb, max_age_s=5)


async def test_run_cycle_true_against_real_database(engine: AsyncEngine) -> None:
    assert await run_cycle(async_sessionmaker(engine)) is True


async def test_run_cycle_false_when_database_unreachable() -> None:
    bad = create_async_engine(
        "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none", connect_args={"timeout": 1}
    )
    try:
        assert await run_cycle(async_sessionmaker(bad)) is False
    finally:
        await bad.dispose()


async def test_worker_loop_writes_heartbeat_and_stops(
    engine: AsyncEngine, settings: Settings
) -> None:
    settings.worker_poll_interval_s = 0.05
    stop = asyncio.Event()
    task = asyncio.create_task(run(settings, stop, async_sessionmaker(engine)))
    for _ in range(100):
        if settings.worker_heartbeat_file.exists():
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert heartbeat_is_fresh(settings.worker_heartbeat_file, max_age_s=5)


async def test_run_cycle_executes_queued_jobs(engine: AsyncEngine) -> None:
    from sqlalchemy import delete

    from app.core import jobs
    from app.core.jobs import Job, JobContext, JobStatus

    @jobs.job_handler("test.worker_cycle")
    async def _handler(ctx: JobContext) -> dict[str, int]:
        return {"ok": 1}

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s, s.begin():
        await s.execute(delete(Job))
        job = await jobs.enqueue(s, "test.worker_cycle")
    assert await run_cycle(maker) is True
    async with maker() as s:
        done = await s.get(Job, job.id)
        assert done is not None and done.status == JobStatus.SUCCEEDED
        await s.execute(delete(Job))
        await s.commit()
