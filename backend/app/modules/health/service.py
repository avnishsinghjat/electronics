"""Health checks. Each check is independent and never raises."""

import shutil
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import Settings
from app.core.db import ping
from app.modules.health.schemas import DatabaseHealth, DiskHealth, HealthResponse, LlmHealth

# Below this, uploads (photos, KiCad projects, PDFs) are at risk; report degraded.
LOW_DISK_BYTES = 1 * 1024**3


async def check_database(session: AsyncSession) -> DatabaseHealth:
    start = time.perf_counter()
    try:
        await ping(session)
    except Exception as exc:
        return DatabaseHealth(status="error", latency_ms=None, detail=type(exc).__name__)
    return DatabaseHealth(status="ok", latency_ms=round((time.perf_counter() - start) * 1000, 2))


def check_disk(data_dir: Path) -> DiskHealth:
    path = data_dir.resolve()
    if not path.is_dir():
        return DiskHealth(
            status="error",
            path=str(path),
            free_bytes=None,
            total_bytes=None,
            detail="DATA_DIR does not exist",
        )
    usage = shutil.disk_usage(path)
    low = usage.free < LOW_DISK_BYTES
    return DiskHealth(
        status="degraded" if low else "ok",
        path=str(path),
        free_bytes=usage.free,
        total_bytes=usage.total,
        detail="Less than 1 GiB free" if low else None,
    )


def check_llm() -> LlmHealth:
    # The LLM gateway (LM Studio / OpenRouter / custom providers) is delivered in Phase 9.
    # Until then no provider exists, so the honest answer is "not configured".
    return LlmHealth(
        status="not_configured",
        provider=None,
        detail="LLM gateway not configured (delivered in Phase 9)",
    )


async def get_health(session: AsyncSession, settings: Settings) -> HealthResponse:
    database = await check_database(session)
    disk = check_disk(settings.data_dir)
    overall = "ok" if database.status == "ok" and disk.status == "ok" else "degraded"
    return HealthResponse(
        status=overall,
        version=__version__,
        environment=settings.env,
        air_gapped=settings.air_gapped,
        database=database,
        disk=disk,
        llm=check_llm(),
    )
