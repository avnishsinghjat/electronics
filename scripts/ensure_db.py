"""Create a PostgreSQL database if it does not exist.

Usage: python scripts/ensure_db.py postgresql+asyncpg://user:pass@host:5432/dbname
Connects to the server's ``postgres`` maintenance database with the same credentials.
"""

import asyncio
import sys

import asyncpg
from sqlalchemy import make_url


async def ensure(url: str) -> None:
    target = make_url(url)
    name = target.database
    if not name:
        raise SystemExit("database name missing from URL")
    conn = await asyncpg.connect(
        user=target.username,
        password=target.password,
        host=target.host or "localhost",
        port=target.port or 5432,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists:
            print(f"database {name}: exists")
        else:
            await conn.execute(f'CREATE DATABASE "{name}"')
            print(f"database {name}: created")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    asyncio.run(ensure(sys.argv[1]))
