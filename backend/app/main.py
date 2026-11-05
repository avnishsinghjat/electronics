"""FastAPI application factory."""

import asyncio
import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.modules.attachments.router import router as attachments_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.boq.router import router as boq_router
from app.modules.health.router import router as health_router
from app.modules.org.router import router as org_router
from app.modules.parts.router import router as parts_router
from app.modules.settings.router import router as settings_router
from app.modules.users.router import router as users_router

API_PREFIX = "/api"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    importlib.import_module("app.handlers")  # job kinds must be registered to enqueue them
    configure_logging(settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        stop = asyncio.Event()
        task = None
        if settings.run_jobs_in_api:
            from app.worker import run as run_worker

            task = asyncio.create_task(run_worker(settings, stop))
        yield
        if task is not None:
            stop.set()
            await task
        await dispose_engine()

    app = FastAPI(
        title="FabTrack API",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        # Swagger UI / ReDoc load their assets from a CDN, which the offline rule forbids.
        # The machine-readable schema is served at /api/openapi.json instead.
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    for router in (
        health_router,
        auth_router,
        settings_router,
        users_router,
        audit_router,
        org_router,
        attachments_router,
        parts_router,
        boq_router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    return app


app = create_app()
