"""Every endpoint declares its permission; the role matrix only uses known permissions."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS, Role, permissions_for
from app.main import create_app
from app.modules.auth.deps import AUTHENTICATED, PERMISSION_ATTR, PUBLIC, require

# Anonymous endpoints are a deliberate, short list.
EXPECTED_PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/setup/status"),
    ("POST", "/api/setup"),
    ("GET", "/api/settings/branding"),
    ("GET", "/api/settings/logo"),
}


def _api_routes(routes: list[Any], prefix: str = "") -> list[tuple[str, APIRoute]]:
    """Flatten FastAPI's lazily included routers into (full path, route)."""
    out: list[tuple[str, APIRoute]] = []
    for route in routes:
        if isinstance(route, APIRoute):
            out.append((prefix + route.path, route))
        elif hasattr(route, "original_router"):
            ctx_prefix = getattr(route.include_context, "prefix", "") or ""
            out.extend(_api_routes(route.original_router.routes, prefix + ctx_prefix))
    return out


def _declared(route: APIRoute) -> set[str]:
    found: set[str] = set()

    def walk(dependant: Any) -> None:
        for dep in dependant.dependencies:
            marker = getattr(dep.call, PERMISSION_ATTR, None)
            if marker:
                found.add(marker)
            walk(dep)

    walk(route.dependant)
    return found


@pytest.fixture(scope="module")
def application() -> FastAPI:
    return create_app()


def test_every_endpoint_declares_a_permission(application: FastAPI) -> None:
    routes = _api_routes(application.router.routes)
    assert len(routes) > 20
    missing = [f"{sorted(r.methods or set())} {path}" for path, r in routes if not _declared(r)]
    assert missing == [], f"Endpoints without require()/authenticated/public: {missing}"


def test_each_endpoint_declares_exactly_one_access_rule(application: FastAPI) -> None:
    multiple = {
        path: _declared(r)
        for path, r in _api_routes(application.router.routes)
        if len(_declared(r)) > 1
    }
    assert multiple == {}


def test_public_endpoints_are_exactly_the_expected_list(application: FastAPI) -> None:
    public = {
        (method, path)
        for path, r in _api_routes(application.router.routes)
        if _declared(r) == {PUBLIC}
        for method in (r.methods or set())
        if method != "HEAD"
    }
    assert public == EXPECTED_PUBLIC


def test_declared_permissions_are_known(application: FastAPI) -> None:
    for _, route in _api_routes(application.router.routes):
        for perm in _declared(route) - {PUBLIC, AUTHENTICATED}:
            assert perm in PERMISSIONS


def test_require_rejects_unknown_permission() -> None:
    with pytest.raises(ValueError, match="Unknown permission"):
        require("boq:delete_everything")


def test_role_matrix_shape() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(PERMISSIONS)
    # Viewer is client-safe: read-only, issued reports only.
    assert ROLE_PERMISSIONS[Role.VIEWER] == {"projects:read", "reports:read_issued"}
    for role, perms in ROLE_PERMISSIONS.items():
        if role != Role.ADMIN:
            assert "users:manage" not in perms
            assert "settings:manage" not in perms
    assert "reports:approve" in ROLE_PERMISSIONS[Role.QC_LEAD]
    assert "reports:approve" not in ROLE_PERMISSIONS[Role.QC_INSPECTOR]
    assert "ncr:close" in ROLE_PERMISSIONS[Role.QC_LEAD]
    assert "ncr:close" not in ROLE_PERMISSIONS[Role.QC_INSPECTOR]
    assert "design:signoff" in ROLE_PERMISSIONS[Role.ENGINEER]
    assert "pr:approve" in ROLE_PERMISSIONS[Role.PROJECT_MANAGER]
    assert "grn:create" in ROLE_PERMISSIONS[Role.STORES]


def test_multiple_roles_union() -> None:
    perms = permissions_for({Role.STORES, Role.QC_INSPECTOR})
    assert {"grn:create", "qc:inspect", "kitting:issue"} <= perms
    assert "reports:approve" not in perms
