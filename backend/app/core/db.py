"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.models import Base

__all__ = ["Base", "dispose_engine", "get_engine", "get_session", "get_sessionmaker", "ping"]

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("postgresql+asyncpg"):
        connect_args["timeout"] = settings.db_connect_timeout_s
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = build_engine(get_settings())
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session; overridden in tests for rollback isolation."""
    async with get_sessionmaker()() as session:
        yield session


async def ping(session: AsyncSession) -> None:
    await session.execute(text("SELECT 1"))
