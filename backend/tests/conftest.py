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
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

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
async def db_conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """One connection and outer transaction per test, rolled back at the end."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _savepoint_session(conn: AsyncConnection) -> AsyncSession:
    return AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_conn: AsyncConnection) -> AsyncIterator[AsyncSession]:
    session = _savepoint_session(db_conn)
    try:
        yield session
    finally:
        await session.close()


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
def app(settings: Settings, db_conn: AsyncConnection, db_session: AsyncSession) -> FastAPI:
    application = create_app(settings)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        # Like production, every request gets its own session (here on the test's
        # connection, inside a savepoint): a failed request rolls back only its own work
        # and never touches objects the test holds in db_session.
        await db_session.flush()
        session = _savepoint_session(db_conn)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    application.dependency_overrides[get_session] = _session_override
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest_asyncio.fixture(loop_scope="session")
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture(loop_scope="session")
async def run_jobs(db_conn: AsyncConnection, settings: Settings):
    """Drain queued background jobs on the test connection (the worker equivalent)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core import jobs

    maker = async_sessionmaker(
        bind=db_conn, join_transaction_mode="create_savepoint", expire_on_commit=False
    )

    async def drain() -> int:
        count = 0
        while await jobs.run_one(maker, "test-worker", settings):
            count += 1
        return count

    return drain
