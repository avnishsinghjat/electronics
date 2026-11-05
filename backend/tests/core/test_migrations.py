"""Migrations upgrade and downgrade cleanly on an empty database, and the models
match the migrations exactly (no un-migrated model change can slip in)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND = Path(__file__).resolve().parents[2]


def _cfg(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
async def empty_db(admin_url: str) -> AsyncIterator[str]:
    name = f"fabtrack_mig_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


async def _tables(url: str) -> set[str]:
    eng = create_async_engine(url)
    try:
        async with eng.connect() as conn:
            return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
    finally:
        await eng.dispose()


async def test_upgrade_downgrade_upgrade(empty_db: str) -> None:
    cfg = _cfg(empty_db)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    assert {"projects", "inventory_ledger", "audit_log"} <= await _tables(empty_db)
    await asyncio.to_thread(command.downgrade, cfg, "base")
    assert await _tables(empty_db) == {"alembic_version"}
    await asyncio.to_thread(command.upgrade, cfg, "head")
    from app.models import Base

    assert await _tables(empty_db) == set(Base.metadata.tables) | {"alembic_version"}


async def test_models_match_migrations(empty_db: str) -> None:
    cfg = _cfg(empty_db)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    await asyncio.to_thread(command.check, cfg)  # raises if autogenerate finds a diff
