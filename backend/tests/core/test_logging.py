import json
import logging

import pytest
from httpx import AsyncClient

from app.core.logging import JsonFormatter, configure_logging, request_id_var


def _record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("fabtrack.test", logging.INFO, __file__, 1, msg, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_core_fields_and_extras() -> None:
    token = request_id_var.set("rid-1")
    try:
        line = JsonFormatter().format(_record(part="GRM188R71H104KA93D", qty=3))
    finally:
        request_id_var.reset(token)
    data = json.loads(line)
    assert data["msg"] == "hello"
    assert data["level"] == "INFO"
    assert data["logger"] == "fabtrack.test"
    assert data["request_id"] == "rid-1"
    assert data["part"] == "GRM188R71H104KA93D"
    assert data["qty"] == 3
    assert "ts" in data


def test_json_formatter_omits_request_id_outside_requests() -> None:
    data = json.loads(JsonFormatter().format(_record()))
    assert "request_id" not in data


def test_json_formatter_serialises_exceptions() -> None:
    try:
        raise ValueError("bad qty")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "fabtrack.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
    data = json.loads(JsonFormatter().format(record))
    assert "ValueError: bad qty" in data["exc"]


def test_configure_logging_text_mode() -> None:
    configure_logging("DEBUG", json_output=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)
    configure_logging("INFO", json_output=True)
    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)


async def test_access_log_line_per_request(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="fabtrack.access")
    await client.get("/api/health", headers={"X-Request-ID": "log-me"})
    records = [r for r in caplog.records if r.name == "fabtrack.access"]
    assert len(records) == 1
    rec = records[0]
    assert rec.__dict__["path"] == "/api/health"
    assert rec.__dict__["status"] == 200
    assert rec.__dict__["method"] == "GET"
    assert rec.__dict__["duration_ms"] >= 0
