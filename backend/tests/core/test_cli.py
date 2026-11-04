import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import cli
from app.core import db
from app.core.config import get_settings


@pytest.fixture
def cli_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_database_url: str, engine: object
) -> Iterator[Path]:
    """Points the process-wide settings at the test database (engine fixture created it)."""
    monkeypatch.setenv("FABTRACK_DATABASE_URL", test_database_url)
    monkeypatch.setenv("FABTRACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FABTRACK_WORKER_HEARTBEAT_FILE", str(tmp_path / "hb"))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


async def test_check_command_succeeds(cli_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert await cli._check() == 0
    out = capsys.readouterr().out
    assert "database: ok" in out
    assert (cli_env / "data").is_dir()


async def test_check_command_fails_when_database_unreachable(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FABTRACK_DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/none")
    monkeypatch.setenv("FABTRACK_DB_CONNECT_TIMEOUT_S", "1")
    get_settings.cache_clear()
    await db.dispose_engine()
    assert await cli._check() == 1


async def test_seed_runs_registered_seeders(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    async def fake_seeder(_session: object) -> int:
        calls.append("ran")
        return 7

    monkeypatch.setattr(cli, "SEEDERS", [("probe", fake_seeder)])
    assert await cli._seed() == 0
    out = capsys.readouterr().out
    assert calls == ["ran"]
    assert "seeded probe: 7 rows" in out
    assert "1 seeders registered, 7 rows written" in out


def test_worker_health_command(cli_env: Path) -> None:
    assert cli.main(["worker-health"]) == 1
    (cli_env / "hb").write_text(f"{time.time():.3f} db_ok\n")
    assert cli.main(["worker-health", "--max-age", "10"]) == 0
