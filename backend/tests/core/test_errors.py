"""Every failure returns {"error": {"code", "message", "details"}}."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient

from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """Adds probe routes that exercise each error path (test-only, not in production)."""

    @app.get("/api/_probe/int")
    async def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    @app.get("/api/_probe/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/api/_probe/not-found")
    async def missing() -> None:
        raise NotFoundError("Project not found", details={"id": "x"})

    @app.get("/api/_probe/conflict")
    async def conflict() -> None:
        raise ConflictError("Stale row_version")

    @app.get("/api/_probe/forbidden")
    async def forbidden() -> None:
        raise PermissionDeniedError("Missing permission boq:import")

    @app.get("/api/_probe/custom")
    async def custom() -> None:
        raise AppError("Qty must be positive", code="invalid_qty", status_code=400)

    @app.get("/api/_probe/http-dict")
    async def http_dict() -> None:
        raise HTTPException(status_code=400, detail={"field": "qty"})

    return app


def _assert_error_shape(body: dict[str, object]) -> dict[str, object]:
    assert set(body) == {"error"}
    err = body["error"]
    assert isinstance(err, dict)
    assert set(err) == {"code", "message", "details"}
    return err


async def test_404_unknown_route(client: AsyncClient) -> None:
    resp = await client.get("/api/does-not-exist")
    assert resp.status_code == 404
    err = _assert_error_shape(resp.json())
    assert err["code"] == "not_found"
    assert err["message"] == "Not Found"


async def test_405_wrong_method(client: AsyncClient) -> None:
    resp = await client.post("/api/health")
    assert resp.status_code == 405
    assert _assert_error_shape(resp.json())["code"] == "method_not_allowed"


async def test_422_validation_error(client: AsyncClient) -> None:
    resp = await client.get("/api/_probe/int", params={"n": "abc"})
    assert resp.status_code == 422
    err = _assert_error_shape(resp.json())
    assert err["code"] == "validation_error"
    assert err["details"] == [
        {
            "loc": ["query", "n"],
            "msg": "Input should be a valid integer, unable to parse string as an integer",
            "type": "int_parsing",
        }
    ]


async def test_422_missing_param(client: AsyncClient) -> None:
    resp = await client.get("/api/_probe/int")
    assert resp.status_code == 422
    err = _assert_error_shape(resp.json())
    assert err["details"][0]["type"] == "missing"  # type: ignore[index]


async def test_500_unhandled_error_hides_internals(client: AsyncClient) -> None:
    resp = await client.get("/api/_probe/boom", headers={"X-Request-ID": "req-500"})
    assert resp.status_code == 500
    err = _assert_error_shape(resp.json())
    assert err == {
        "code": "internal_error",
        "message": "An unexpected error occurred",
        "details": None,
    }
    assert "secret" not in resp.text
    assert resp.headers["x-request-id"] == "req-500"


@pytest.mark.parametrize(
    ("path", "status", "code", "message"),
    [
        ("/api/_probe/not-found", 404, "not_found", "Project not found"),
        ("/api/_probe/conflict", 409, "conflict", "Stale row_version"),
        ("/api/_probe/forbidden", 403, "forbidden", "Missing permission boq:import"),
        ("/api/_probe/custom", 400, "invalid_qty", "Qty must be positive"),
    ],
)
async def test_app_errors(
    client: AsyncClient, path: str, status: int, code: str, message: str
) -> None:
    resp = await client.get(path)
    assert resp.status_code == status
    err = _assert_error_shape(resp.json())
    assert err["code"] == code
    assert err["message"] == message


async def test_app_error_details_are_returned(client: AsyncClient) -> None:
    resp = await client.get("/api/_probe/not-found")
    assert _assert_error_shape(resp.json())["details"] == {"id": "x"}


async def test_http_exception_with_structured_detail(client: AsyncClient) -> None:
    resp = await client.get("/api/_probe/http-dict")
    assert resp.status_code == 400
    err = _assert_error_shape(resp.json())
    assert err["code"] == "bad_request"
    assert err["message"] == "Bad Request"
    assert err["details"] == {"field": "qty"}
