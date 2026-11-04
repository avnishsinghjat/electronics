"""DB-backed background jobs (no Redis): CSV import, PDF build, LLM calls, KiCad runs.

* ``enqueue`` inserts a row in the caller's transaction (the job only becomes visible
  when the business change that requested it commits).
* Workers claim with ``SELECT ... FOR UPDATE SKIP LOCKED`` so several workers never
  run the same job.
* Failures retry with exponential backoff up to ``max_attempts``; jobs whose worker
  died (``locked_at`` older than the lease) are reclaimed.
"""

import enum
import logging
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.context import acting_as
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.models import Base, JsonB, enum_check, utcnow

logger = logging.getLogger("fabtrack.jobs")


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        enum_check("status", JobStatus),
        Index("ix_jobs_claim", "status", "run_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED.value, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonB, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class JobContext:
    job_id: uuid.UUID
    payload: dict[str, Any]
    session: AsyncSession
    attempt: int


Handler = Callable[[JobContext], Awaitable[dict[str, Any] | None]]
_HANDLERS: dict[str, Handler] = {}


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if kind in _HANDLERS and _HANDLERS[kind] is not fn:
            raise ValueError(f"Job handler for {kind!r} already registered")
        _HANDLERS[kind] = fn
        return fn

    return register


def registered_kinds() -> list[str]:
    return sorted(_HANDLERS)


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    max_attempts: int = 3,
    created_by: uuid.UUID | None = None,
) -> Job:
    if kind not in _HANDLERS:
        raise AppError(f"No handler registered for job kind {kind!r}", code="unknown_job_kind")
    job = Job(kind=kind, payload=payload or {}, max_attempts=max_attempts, created_by=created_by)
    session.add(job)
    await session.flush()
    return job


def backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(2**attempt * 5, 600))


async def claim_next(
    session: AsyncSession, worker_id: str, *, lease: timedelta = timedelta(minutes=15)
) -> Job | None:
    now = utcnow()
    stmt = (
        select(Job)
        .where(
            or_(
                (Job.status == JobStatus.QUEUED.value) & (Job.run_after <= now),
                (Job.status == JobStatus.RUNNING.value) & (Job.locked_at < now - lease),
            )
        )
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.RUNNING.value
    job.locked_at = now
    job.locked_by = worker_id
    job.attempts += 1
    await session.commit()
    return job


async def run_one(sessionmaker: async_sessionmaker[AsyncSession], worker_id: str) -> bool:
    """Claim and execute one job. Returns False when the queue is empty."""
    async with sessionmaker() as session:
        job = await claim_next(session, worker_id)
        if job is None:
            return False
        job_id, kind, payload, attempt = job.id, job.kind, dict(job.payload), job.attempts
        created_by = job.created_by

    handler = _HANDLERS.get(kind)
    async with sessionmaker() as session:
        try:
            if handler is None:
                raise AppError(f"No handler registered for job kind {kind!r}")
            with acting_as(created_by):
                result = await handler(JobContext(job_id, payload, session, attempt))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.exception("job_failed", extra={"job_id": str(job_id), "kind": kind})
            await _record_failure(sessionmaker, job_id, exc)
            return True

    async with sessionmaker() as session:
        job_row = await session.get(Job, job_id, with_for_update=True)
        assert job_row is not None
        job_row.status = JobStatus.SUCCEEDED.value
        job_row.result = result
        job_row.progress = 100
        job_row.error = None
        job_row.finished_at = utcnow()
        job_row.locked_at = None
        await session.commit()
    logger.info("job_succeeded", extra={"job_id": str(job_id), "kind": kind})
    return True


async def _record_failure(
    sessionmaker: async_sessionmaker[AsyncSession], job_id: uuid.UUID, exc: Exception
) -> None:
    async with sessionmaker() as session:
        job = await session.get(Job, job_id, with_for_update=True)
        assert job is not None
        job.error = "".join(traceback.format_exception_only(exc)).strip()[:4000]
        job.locked_at = None
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED.value
            job.finished_at = utcnow()
        else:
            job.status = JobStatus.QUEUED.value
            job.run_after = utcnow() + backoff(job.attempts)
        await session.commit()


async def cancel(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id, with_for_update=True)
    if job is None:
        raise AppError("Job not found", code="not_found", status_code=404)
    if job.status != JobStatus.QUEUED.value:
        raise AppError(
            "Only queued jobs can be cancelled", code="job_not_cancellable", status_code=409
        )
    job.status = JobStatus.CANCELLED.value
    job.finished_at = utcnow()
    await session.flush()
    return job
