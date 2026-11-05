import io
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.settings.models import CompanySettings
from tests.factories import login, make_user

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SETUP: dict[str, Any] = {
    "company_name": "Sahyadri Electronics",
    "admin": {"username": "admin", "full_name": "Plant Admin", "password": "Setup-pass-2026"},
    "prefixes": {"PO": "PUR", "PRJ": "JOB"},
}


async def test_first_run_setup_creates_admin_and_signs_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    status = (await client.get("/api/setup/status")).json()
    assert status["needs_setup"] is True
    assert status["data_dir"]["ok"] is True and status["data_dir"]["writable"] is True
    assert {n["doc_type"] for n in status["numbering"]} >= {
        "PRJ",
        "PO",
        "GRN",
        "WO",
        "QC",
        "NCR",
        "RPT",
    }
    resp = await client.post("/api/setup", json=SETUP)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["roles"] == ["admin"]
    assert body["user"]["must_change_password"] is False
    assert "fabtrack_refresh=" in resp.headers["set-cookie"]
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    numbering = {
        n["doc_type"]: n
        for n in (await client.get("/api/settings/numbering", headers=headers)).json()
    }
    assert numbering["PO"]["prefix"] == "PUR" and numbering["PO"]["example"].startswith("PUR-")
    assert numbering["PRJ"]["prefix"] == "JOB"
    branding = (await client.get("/api/settings/branding")).json()
    assert branding == {
        "company_name": "Sahyadri Electronics",
        "has_logo": False,
        "logo_url": None,
        "setup_complete": True,
    }
    after = (await client.get("/api/setup/status")).json()
    assert after["needs_setup"] is False and after["numbering"] == []


async def test_setup_only_once(client: AsyncClient, db_session: AsyncSession) -> None:
    await make_user(db_session, "existing")
    resp = await client.post("/api/setup", json=SETUP)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "setup_complete"


async def test_setup_validates_password_and_prefix(client: AsyncClient) -> None:
    weak = await client.post(
        "/api/setup", json={**SETUP, "admin": {**SETUP["admin"], "password": "admin123"}}
    )
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    bad_prefix = await client.post("/api/setup", json={**SETUP, "prefixes": {"PO": "P O!"}})
    assert bad_prefix.status_code == 400 and bad_prefix.json()["error"]["code"] == "invalid_prefix"
    assert (await client.get("/api/setup/status")).json()["needs_setup"] is True


async def test_setup_rejects_unwritable_data_dir(
    client: AsyncClient, settings, tmp_path: Path
) -> None:
    settings.data_dir = tmp_path / "does-not-exist"
    status = (await client.get("/api/setup/status")).json()
    assert (
        status["data_dir"]["ok"] is False
        and status["data_dir"]["detail"] == "Directory does not exist"
    )
    resp = await client.post("/api/setup", json=SETUP)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "data_dir_unavailable"


async def test_logo_upload_validation_and_serving(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(CompanySettings(company_name="Logo Co"))
    await make_user(db_session, "brand_admin")
    headers = await login(client, "brand_admin")
    svg = await client.post(
        "/api/settings/logo",
        headers=headers,
        files={"file": ("logo.svg", io.BytesIO(b"<svg onload=alert(1)>"), "image/svg+xml")},
    )
    assert svg.status_code == 415
    big = await client.post(
        "/api/settings/logo",
        headers=headers,
        files={"file": ("big.png", io.BytesIO(PNG + b"0" * (2 * 1024 * 1024)), "image/png")},
    )
    assert big.status_code == 413
    ok = await client.post(
        "/api/settings/logo",
        headers=headers,
        files={"file": ("logo.png", io.BytesIO(PNG), "image/jpeg")},
    )
    assert ok.status_code == 200, ok.text
    served = await client.get("/api/settings/logo")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"  # sniffed type wins over the declared one
    assert served.content == PNG
    assert (await client.get("/api/settings/branding")).json()["has_logo"] is True


async def test_company_update_and_numbering_update(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add(CompanySettings(company_name="Old Co"))
    await make_user(db_session, "co_admin")
    headers = await login(client, "co_admin")
    company = (await client.get("/api/settings/company", headers=headers)).json()
    resp = await client.put(
        "/api/settings/company",
        headers=headers,
        json={
            "row_version": company["row_version"],
            "company_name": "New Co",
            "gstin": "27AABCS1234F1Z5",
        },
    )
    assert resp.status_code == 200 and resp.json()["company_name"] == "New Co"
    stale = await client.put(
        "/api/settings/company",
        headers=headers,
        json={"row_version": company["row_version"], "company_name": "Stale"},
    )
    assert stale.status_code == 409
    bad_gstin = await client.put(
        "/api/settings/company",
        headers=headers,
        json={"row_version": resp.json()["row_version"], "company_name": "X", "gstin": "nope"},
    )
    assert bad_gstin.status_code == 422
    num = await client.put("/api/settings/numbering/GRN", headers=headers, json={"prefix": "gr"})
    assert num.status_code == 200 and num.json()["prefix"] == "GR"
    missing = await client.put(
        "/api/settings/numbering/NOPE", headers=headers, json={"prefix": "X"}
    )
    assert missing.status_code == 404
