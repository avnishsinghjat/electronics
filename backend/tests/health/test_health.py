from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app import __version__
from app.core.config import Settings
from app.modules.health import service


async def test_health_returns_200_and_correct_shape(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "status",
        "version",
        "environment",
        "air_gapped",
        "database",
        "disk",
        "llm",
    }
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["environment"] == "test"
    assert body["air_gapped"] is True
    assert body["database"]["status"] == "ok"
    assert body["database"]["latency_ms"] >= 0
    assert body["disk"]["status"] in {"ok", "degraded"}
    assert body["disk"]["free_bytes"] > 0
    assert body["disk"]["total_bytes"] >= body["disk"]["free_bytes"]
    assert body["llm"] == {
        "status": "not_configured",
        "provider": None,
        "detail": "LLM gateway not configured (delivered in Phase 9)",
    }


async def test_health_sets_request_id_header(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert len(resp.headers["x-request-id"]) == 32


async def test_health_echoes_valid_incoming_request_id(client: AsyncClient) -> None:
    resp = await client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["x-request-id"] == "abc-123"


async def test_invalid_incoming_request_id_is_replaced(client: AsyncClient) -> None:
    resp = await client.get("/api/health", headers={"X-Request-ID": "bad id\twith spaces"})
    assert resp.headers["x-request-id"] != "bad id\twith spaces"
    assert len(resp.headers["x-request-id"]) == 32


async def test_openapi_schema_is_served_and_lists_health(client: AsyncClient) -> None:
    resp = await client.get("/api/openapi.json")
    assert resp.status_code == 200
    assert "/api/health" in resp.json()["paths"]


async def test_cdn_backed_docs_are_disabled(client: AsyncClient) -> None:
    assert (await client.get("/api/docs")).status_code == 404
    assert (await client.get("/redoc")).status_code == 404


class _BrokenSession:
    async def execute(self, *_: object, **__: object) -> None:
        raise ConnectionRefusedError("db down")


async def test_check_database_reports_error_without_raising() -> None:
    result = await service.check_database(_BrokenSession())  # type: ignore[arg-type]
    assert result.status == "error"
    assert result.latency_ms is None
    assert result.detail == "ConnectionRefusedError"


def test_check_disk_missing_directory(tmp_path: Path) -> None:
    result = service.check_disk(tmp_path / "missing")
    assert result.status == "error"
    assert result.free_bytes is None
    assert result.detail == "DATA_DIR does not exist"


def test_check_disk_low_space_is_degraded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "shutil.disk_usage",
        lambda _: SimpleNamespace(total=10 * 1024**3, used=0, free=100 * 1024**2),
    )
    result = service.check_disk(tmp_path)
    assert result.status == "degraded"
    assert result.free_bytes == 100 * 1024**2


async def test_overall_status_degraded_when_database_down(settings: Settings) -> None:
    result = await service.get_health(_BrokenSession(), settings)  # type: ignore[arg-type]
    assert result.status == "degraded"
    assert result.database.status == "error"
