"""Operator command line: ``python -m app.cli <command>``.

Commands:
  check          verify database connectivity and DATA_DIR (exit 1 on failure)
  worker-health  exit 0 if the worker heartbeat is fresh (used by Docker)
  seed           run all registered seeders (module seeders register from Phase 1)
  openapi        print the OpenAPI schema as JSON (committed to docs/api/openapi.json)
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.modules.health.service import check_database, check_disk
from app.worker import heartbeat_is_fresh

Seeder = Callable[[AsyncSession], Awaitable[int]]
SEEDERS: list[tuple[str, Seeder]] = []


async def _check() -> int:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    async with get_sessionmaker()() as session:
        db = await check_database(session)
    await dispose_engine()
    disk = check_disk(settings.data_dir)
    print(f"database: {db.status} ({db.latency_ms} ms) {db.detail or ''}".rstrip())
    print(f"data_dir: {disk.status} {disk.path} free={disk.free_bytes}")
    return 0 if db.status == "ok" and disk.status != "error" else 1


async def _seed() -> int:
    total = 0
    async with get_sessionmaker()() as session:
        for name, seeder in SEEDERS:
            count = await seeder(session)
            print(f"seeded {name}: {count} rows")
            total += count
        await session.commit()
    await dispose_engine()
    print(f"{len(SEEDERS)} seeders registered, {total} rows written")
    return 0


def openapi_json() -> str:
    from app.main import create_app

    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("seed")
    sub.add_parser("openapi")
    hb = sub.add_parser("worker-health")
    hb.add_argument("--max-age", type=float, default=30.0)
    args = parser.parse_args(argv)

    if args.command == "check":
        return asyncio.run(_check())
    if args.command == "seed":
        return asyncio.run(_seed())
    if args.command == "openapi":
        sys.stdout.write(openapi_json())
        return 0
    settings = get_settings()
    return 0 if heartbeat_is_fresh(settings.worker_heartbeat_file, args.max_age) else 1


if __name__ == "__main__":
    sys.exit(main())
