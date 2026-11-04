"""Background worker process.

Phase 0 provides the process, its lifecycle and its health signal: it verifies the
database connection on every cycle and writes a heartbeat file that the Docker health
check reads. The DB-backed job table and job handlers plug into ``run_cycle`` in Phase 1.
"""

import asyncio
import logging
import signal
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.db import dispose_engine, get_sessionmaker, ping
from app.core.logging import configure_logging

logger = logging.getLogger("fabtrack.worker")


def write_heartbeat(path: Path, *, db_ok: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(f"{time.time():.3f} {'db_ok' if db_ok else 'db_error'}\n", encoding="utf-8")
    tmp.replace(path)


def heartbeat_is_fresh(path: Path, max_age_s: float) -> bool:
    try:
        stamp, state = path.read_text(encoding="utf-8").split()
    except (OSError, ValueError):
        return False
    return state == "db_ok" and (time.time() - float(stamp)) <= max_age_s


async def run_cycle(sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
    """One worker cycle. Returns True when the database is reachable."""
    try:
        async with sessionmaker() as session:
            await ping(session)
    except Exception as exc:
        logger.warning("worker_db_unreachable", extra={"error": type(exc).__name__})
        return False
    return True


async def run(
    settings: Settings,
    stop: asyncio.Event,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> None:
    maker = sessionmaker or get_sessionmaker()
    logger.info("worker_started", extra={"poll_interval_s": settings.worker_poll_interval_s})
    try:
        while not stop.is_set():
            db_ok = await run_cycle(maker)
            write_heartbeat(settings.worker_heartbeat_file, db_ok=db_ok)
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_s)
            except TimeoutError:
                continue
    finally:
        await dispose_engine()
        logger.info("worker_stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    stop = asyncio.Event()

    async def _main() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await run(settings, stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
