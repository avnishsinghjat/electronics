"""Test harness.

* One throwaway PostgreSQL database per test session, migrated to head with Alembic,
  dropped at the end.
* Every test runs inside a transaction that is rolled back afterwards, so tests never
  see each other's rows (services may still call ``commit()``: the session joins the
  outer transaction through a SAVEPOINT).
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app import models as _models  # noqa: F401  (registers every table)
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get(
    "FABTRACK_TEST_DATABASE_ADMIN_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
)


def _run_migrations(database_url: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["database_url"] = database_url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = make_url(ADMIN_URL).set(database=f"fabtrack_test_{uuid.uuid4().hex[:10]}")
    return url.render_as_string(hide_password=False)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    db_name = make_url(test_database_url).database
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        # Alembic's async env runs its own event loop; run it in a worker thread.
        await asyncio.to_thread(_run_migrations, test_database_url)
        eng = create_async_engine(test_database_url)
        async with eng.begin() as conn:
            # Harness-only table used to prove per-test rollback isolation.
            await conn.execute(
                text("CREATE TABLE _harness_probe (id serial PRIMARY KEY, note text NOT NULL)")
            )
        yield eng
        await eng.dispose()
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        await admin.dispose()


@pytest.fixture(scope="session")
def admin_url() -> str:
    return ADMIN_URL


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def settings(tmp_path: Path, test_database_url: str) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return Settings(
        env="test",
        database_url=test_database_url,
        data_dir=data_dir,
        log_json=True,
        worker_heartbeat_file=tmp_path / "worker.heartbeat",
    )


@pytest.fixture
def app(settings: Settings, db_session: AsyncSession) -> FastAPI:
    application = create_app(settings)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = _session_override
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest_asyncio.fixture(loop_scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
