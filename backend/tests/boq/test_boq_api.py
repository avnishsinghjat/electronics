import io
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boq.models import BoqLine
from app.modules.parts.models import Part
from app.modules.settings.models import CompanySettings
from app.seed import seed_reference_data, seed_sample_data
from tests.factories import (
    DivisionFactory,
    PartFactory,
    PoLineFactory,
    ProjectFactory,
    PurchaseOrderFactory,
    VendorFactory,
    create,
    login,
    make_user,
    project_tree,
)

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


@pytest.fixture
async def ctx(client: AsyncClient, db_session: AsyncSession) -> dict[str, Any]:
    await seed_reference_data(db_session)
    await seed_sample_data(db_session)
    db_session.add(CompanySettings(company_name="Test Co"))
    tree = await project_tree(db_session)
    await make_user(db_session, "boq_pm", roles=("project_manager",))
    h = await login(client, "boq_pm")
    return {"h": h, **tree}


async def _new_boq(client: AsyncClient, ctx: dict[str, Any], **body: Any) -> dict[str, Any]:
    r = await client.post(
        f"/api/projects/{ctx['project'].id}/boqs",
        headers=ctx["h"],
        json={"name": "Main BOM", **body},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _rev(client: AsyncClient, ctx: dict[str, Any], rev_id: str) -> dict[str, Any]:
    r = await client.get(f"/api/boq-revisions/{rev_id}", headers=ctx["h"])
    assert r.status_code == 200, r.text
    return r.json()


async def _import(
    client: AsyncClient,
    ctx: dict[str, Any],
    run_jobs: Any,
    boq_id: str,
    name: str,
    mapping: dict[str, int] | None = None,
    **mapping_extra: Any,
) -> dict[str, Any]:
    content = (SAMPLES / name).read_bytes()
    up = await client.post(
        f"/api/boqs/{boq_id}/imports",
        headers=ctx["h"],
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )
    assert up.status_code == 202, up.text
    assert up.json()["status"] == "parsing"
    await run_jobs()
    parsed = (await client.get(f"/api/boq-imports/{up.json()['id']}", headers=ctx["h"])).json()
    assert parsed["status"] == "parsed", parsed
    body = {
        "row_version": parsed["row_version"],
        "header_row": parsed["header_row"],
        "mapping": mapping or parsed["mapping"],
        **mapping_extra,
    }
    r = await client.put(f"/api/boq-imports/{parsed['id']}/mapping", headers=ctx["h"], json=body)
    assert r.status_code == 202, r.text
    await run_jobs()
    validated = (await client.get(f"/api/boq-imports/{parsed['id']}", headers=ctx["h"])).json()
    assert validated["status"] == "validated", validated
    return validated


def line(mpn: str | None, qty: str, ref: str = "", **kw: Any) -> dict[str, Any]:
    return {"mpn": mpn, "qty_per_unit": qty, "ref_des": ref, **kw}


async def test_boq_revision_lifecycle_and_lines(client: AsyncClient, ctx: dict[str, Any]) -> None:
    boq = await _new_boq(client, ctx, module_id=str(ctx["module"].id))
    assert [r["revision"] for r in boq["revisions"]] == ["A"]
    assert boq["revisions"][0]["build_qty"] == 10  # module qty_to_deliver
    rev_a = boq["revisions"][0]
    h = ctx["h"]

    lines = [
        line("GRM188R71H104KA93D", "3", "C1-C3", category="Passive"),
        line("stm32f407vgt6", "1", "U1", category="IC"),
        line(None, "1", "J1", dnp=True, description="Header", category="Connector"),
        line("RC0603FR-0710KL", "2", "R1,R2", category="Passive", attrition_pct="10"),
    ]
    saved = await client.put(
        f"/api/boq-revisions/{rev_a['id']}/lines",
        headers=h,
        json={"row_version": 1, "lines": lines},
    )
    assert saved.status_code == 200, saved.text
    detail = await _rev(client, ctx, rev_a["id"])
    caps, mcu, header, res = detail["lines"]
    assert caps["ref_des"] == "C1,C2,C3" and caps["part_id"] is not None
    assert mcu["part_id"] is not None  # matched despite lower case
    assert (
        Decimal(caps["attrition_pct"]) == 2 and caps["attrition_override"] is False
    )  # category rate
    assert Decimal(caps["required_qty"]) == 31  # 3 x 10 x 1.02 = 30.6 -> 31
    assert Decimal(res["attrition_pct"]) == 10 and res["attrition_override"] is True
    assert Decimal(res["required_qty"]) == 22
    assert (header["status"], Decimal(header["required_qty"])) == ("Not required", 0)
    assert caps["status"] == "Not ordered" and Decimal(caps["shortfall"]) == 31

    stale = await client.put(
        f"/api/boq-revisions/{rev_a['id']}/lines",
        headers=h,
        json={"row_version": 1, "lines": lines},
    )
    assert stale.status_code == 409

    upd = await client.patch(
        f"/api/boq-revisions/{rev_a['id']}",
        headers=h,
        json={
            "row_version": detail["row_version"],
            "build_qty": 100,
            "attrition_by_category": {"Passive": 5, "IC": 1},
        },
    )
    assert upd.status_code == 200
    detail = await _rev(client, ctx, rev_a["id"])
    assert Decimal(detail["lines"][0]["attrition_pct"]) == 5
    assert Decimal(detail["lines"][0]["required_qty"]) == 315
    assert Decimal(detail["lines"][3]["attrition_pct"]) == 10  # override kept

    rel = await client.post(
        f"/api/boq-revisions/{rev_a['id']}/release",
        headers=h,
        json={"row_version": detail["row_version"]},
    )
    assert rel.status_code == 200 and rel.json()["status"] == "released"
    locked = await client.put(
        f"/api/boq-revisions/{rev_a['id']}/lines",
        headers=h,
        json={"row_version": rel.json()["row_version"], "lines": lines},
    )
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "revision_locked"

    rev_b = (await client.post(f"/api/boqs/{boq['id']}/revisions", headers=h)).json()
    assert (rev_b["revision"], rev_b["status"], rev_b["line_count"]) == ("B", "draft", 4)
    dup = await client.post(f"/api/boqs/{boq['id']}/revisions", headers=h)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "draft_exists"
    b_lines = (await _rev(client, ctx, rev_b["id"]))["lines"]
    edited = [
        {
            **{k: b_lines[0][k] for k in ("line_key", "mpn", "ref_des", "category")},
            "qty_per_unit": "4",
            "ref_des": "C1-C4",
        },
        {
            **{k: b_lines[1][k] for k in ("line_key", "ref_des", "category")},
            "mpn": "STM32G431CBT6",
            "qty_per_unit": "1",
        },
        {
            **{k: b_lines[3][k] for k in ("line_key", "mpn", "ref_des", "category")},
            "qty_per_unit": "2",
            "description": "Res 10k (note)",
        },
        line("W25Q64JVSSIQ", "1", "U4", category="IC"),
    ]
    saved_b = await client.put(
        f"/api/boq-revisions/{rev_b['id']}/lines",
        headers=h,
        json={"row_version": rev_b["row_version"], "lines": edited},
    )
    assert saved_b.status_code == 200, saved_b.text
    b_detail = await _rev(client, ctx, rev_b["id"])
    rel_b = await client.post(
        f"/api/boq-revisions/{rev_b['id']}/release",
        headers=h,
        json={"row_version": b_detail["row_version"]},
    )
    assert rel_b.status_code == 200
    revisions = {
        r["revision"]: r["status"]
        for r in (await client.get(f"/api/boqs/{boq['id']}", headers=h)).json()["revisions"]
    }
    assert revisions == {"A": "superseded", "B": "released"}

    diff = (await client.get(f"/api/boqs/{boq['id']}/compare?from=A&to=B", headers=h)).json()
    assert diff["summary"] == {
        "added": 1,
        "removed": 1,
        "qty_changed": 1,
        "substituted": 1,
        "changed": 1,
        "unchanged": 0,
    }
    by_change = {d["change"]: d for d in diff["lines"]}
    assert (
        by_change["qty_changed"]["from_line"]["qty_per_unit"] == "3.0000"
        and by_change["qty_changed"]["to_line"]["qty_per_unit"] == "4.0000"
    )
    assert by_change["substituted"]["to_line"]["mpn"] == "STM32G431CBT6"
    assert by_change["removed"]["from_line"]["ref_des"] == "J1"
    assert by_change["added"]["to_line"]["mpn"] == "W25Q64JVSSIQ"
    assert by_change["changed"]["changed_fields"] == ["description"]


async def test_line_validation(client: AsyncClient, ctx: dict[str, Any]) -> None:
    boq = await _new_boq(client, ctx)
    rev = boq["revisions"][0]
    bad = await client.put(
        f"/api/boq-revisions/{rev['id']}/lines",
        headers=ctx["h"],
        json={"row_version": 1, "lines": [line(None, "1", "R1"), line("X1", "1", "R1")]},
    )
    assert bad.status_code == 422
    assert [p["field"] for p in bad.json()["error"]["details"]] == ["mpn", "ref_des"]
    neg = await client.put(
        f"/api/boq-revisions/{rev['id']}/lines",
        headers=ctx["h"],
        json={"row_version": 1, "lines": [line("X", "-1")]},
    )
    assert neg.status_code == 422
    empty = await client.post(
        f"/api/boq-revisions/{rev['id']}/release", headers=ctx["h"], json={"row_version": 1}
    )
    assert empty.status_code == 409 and empty.json()["error"]["code"] == "empty_revision"


async def test_ordered_quantity_flows_into_status(
    client: AsyncClient, ctx: dict[str, Any], db_session: AsyncSession
) -> None:
    from app.modules.procurement.models import PoLineAllocation

    boq = await _new_boq(client, ctx, build_qty=10)
    rev = boq["revisions"][0]
    await client.put(
        f"/api/boq-revisions/{rev['id']}/lines",
        headers=ctx["h"],
        json={"row_version": 1, "lines": [line("RC0603FR-0710KL", "1", "R1", category="IC")]},
    )
    detail = await _rev(client, ctx, rev["id"])
    bl = detail["lines"][0]
    vendor = await create(db_session, VendorFactory)
    po = await create(db_session, PurchaseOrderFactory, vendor_id=vendor.id, status="issued")
    pol = await create(
        db_session,
        PoLineFactory,
        purchase_order_id=po.id,
        part_id=bl["part_id"],
        qty_ordered=Decimal(10),
    )
    db_session.add(
        PoLineAllocation(
            po_line_id=pol.id, boq_line_id=bl["id"], project_id=ctx["project"].id, qty=Decimal(4)
        )
    )
    await db_session.flush()
    bl = (await _rev(client, ctx, rev["id"]))["lines"][0]
    assert (
        bl["status"],
        Decimal(bl["ordered_qty"]),
        Decimal(bl["shortfall"]),
        Decimal(bl["pending_receipt"]),
    ) == ("Partially ordered", 4, 6, 4)
    pol.is_cancelled = True
    await db_session.flush()
    bl = (await _rev(client, ctx, rev["id"]))["lines"][0]
    assert bl["status"] == "Not ordered"


async def test_import_clean_then_rev_b_and_compare(
    client: AsyncClient, ctx: dict[str, Any], run_jobs: Any, db_session: AsyncSession
) -> None:
    boq = await _new_boq(client, ctx, create_revision=False)
    assert boq["revisions"] == []
    v = await _import(client, ctx, run_jobs, boq["id"], "boq-clean.csv")
    assert v["result"]["stats"]["errors"] == 0
    assert v["encoding"] == "utf-8" and v["delimiter"] == ","
    committed = await client.post(
        f"/api/boq-imports/{v['id']}/commit",
        headers=ctx["h"],
        json={"row_version": v["row_version"], "release": True, "build_qty": 25},
    )
    assert committed.status_code == 200, committed.text
    rev_a = committed.json()
    assert (rev_a["revision"], rev_a["status"], rev_a["line_count"], rev_a["build_qty"]) == (
        "A",
        "released",
        15,
        25,
    )

    v2 = await _import(client, ctx, run_jobs, boq["id"], "boq-clean-rev-b.csv")
    rev_b = (
        await client.post(
            f"/api/boq-imports/{v2['id']}/commit",
            headers=ctx["h"],
            json={"row_version": v2["row_version"]},
        )
    ).json()
    assert (rev_b["revision"], rev_b["status"]) == ("B", "draft")
    diff = (await client.get(f"/api/boqs/{boq['id']}/compare?from=A&to=B", headers=ctx["h"])).json()
    assert diff["summary"]["added"] == 1  # U4 flash
    assert diff["summary"]["removed"] == 1  # FB1
    assert diff["summary"]["qty_changed"] == 1  # 100nF 3 -> 4
    assert diff["summary"]["substituted"] == 1  # R3 1k -> 100k part
    assert diff["summary"]["unchanged"] == 12
    # Unknown MPN (the new flash) was created in the part master on commit.
    assert (
        await db_session.execute(select(func.count()).where(Part.mpn == "W25Q64JVSSIQ"))
    ).scalar_one() == 1


async def test_import_messy_reports_errors_and_blocks_commit(
    client: AsyncClient, ctx: dict[str, Any], run_jobs: Any
) -> None:
    boq = await _new_boq(client, ctx)
    v = await _import(client, ctx, run_jobs, boq["id"], "boq-messy.csv")
    assert v["encoding"] == "windows-1252" and v["header_row"] == 3
    codes = {i["code"] for i in v["result"]["issues"]}
    assert {
        "missing_mpn",
        "invalid_qty",
        "duplicate_ref_des",
        "qty_ref_des_mismatch",
        "unknown_part",
        "mpn_variant_master",
        "invalid_price",
        "merged",
    } <= codes
    blocked = await client.post(
        f"/api/boq-imports/{v['id']}/commit",
        headers=ctx["h"],
        json={"row_version": v["row_version"]},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "import_has_errors"
    report = await client.get(f"/api/boq-imports/{v['id']}/errors.csv", headers=ctx["h"])
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/csv")
    assert "missing_mpn" in report.text and report.text.startswith("﻿Row,Severity")
    # Nothing was written: revision A is still empty.
    assert (await _rev(client, ctx, boq["revisions"][0]["id"]))["lines"] == []


async def test_mapping_templates_save_and_auto_apply(
    client: AsyncClient, ctx: dict[str, Any], run_jobs: Any
) -> None:
    boq = await _new_boq(client, ctx, create_revision=False)
    # Map the semicolon file by hand (its quantity header "Menge" is unknown) and save it.
    content = (SAMPLES / "boq-semicolon-utf8bom.csv").read_bytes()
    up = (
        await client.post(
            f"/api/boqs/{boq['id']}/imports",
            headers=ctx["h"],
            files={"file": ("eu.csv", io.BytesIO(content), "text/csv")},
        )
    ).json()
    await run_jobs()
    parsed = (await client.get(f"/api/boq-imports/{up['id']}", headers=ctx["h"])).json()
    assert "qty" not in parsed["mapping"]
    mapping = {**parsed["mapping"], "qty": 2}
    r = await client.put(
        f"/api/boq-imports/{up['id']}/mapping",
        headers=ctx["h"],
        json={
            "row_version": parsed["row_version"],
            "header_row": 0,
            "mapping": mapping,
            "decimal_comma": True,
            "save_template_name": "Euro supplier",
            "template_client": ctx["project"].client_name,
        },
    )
    assert r.status_code == 202
    await run_jobs()
    validated = (await client.get(f"/api/boq-imports/{up['id']}", headers=ctx["h"])).json()
    assert validated["result"]["stats"]["errors"] == 0
    assert validated["result"]["lines"][0]["qty_per_unit"] == "1.5"
    templates = (await client.get("/api/boq-mapping-templates", headers=ctx["h"])).json()
    assert [t["name"] for t in templates] == ["Euro supplier"]
    assert templates[0]["mapping"]["qty"] == "menge"
    # A second upload of the same layout picks the template automatically.
    up2 = (
        await client.post(
            f"/api/boqs/{boq['id']}/imports",
            headers=ctx["h"],
            files={"file": ("eu2.csv", io.BytesIO(content), "text/csv")},
        )
    ).json()
    await run_jobs()
    parsed2 = (await client.get(f"/api/boq-imports/{up2['id']}", headers=ctx["h"])).json()
    assert parsed2["mapping"]["qty"] == 2
    assert parsed2["suggested_template_id"] == templates[0]["id"]
    applied = (
        await client.get(
            f"/api/boq-imports/{up2['id']}/template/{templates[0]['id']}", headers=ctx["h"]
        )
    ).json()
    assert applied == mapping


async def test_kicad_and_xlsx_imports(
    client: AsyncClient, ctx: dict[str, Any], run_jobs: Any
) -> None:
    boq = await _new_boq(client, ctx, create_revision=False)
    v = await _import(client, ctx, run_jobs, boq["id"], "kicad-bom.csv")
    assert v["result"]["stats"]["errors"] == 0 and v["result"]["stats"]["dnp_lines"] == 1
    xboq = await _new_boq(client, ctx, name="From Excel", create_revision=False)
    content = (SAMPLES / "boq-clean.xlsx").read_bytes()
    up = (
        await client.post(
            f"/api/boqs/{xboq['id']}/imports",
            headers=ctx["h"],
            files={
                "file": (
                    "boq.xlsx",
                    io.BytesIO(content),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    ).json()
    await run_jobs()
    parsed = (await client.get(f"/api/boq-imports/{up['id']}", headers=ctx["h"])).json()
    assert (parsed["sheet"], parsed["header_row"]) == ("BOQ", 1)


async def test_import_rejects_wrong_types_and_bad_mapping(
    client: AsyncClient, ctx: dict[str, Any], run_jobs: Any
) -> None:
    boq = await _new_boq(client, ctx)
    pdf = await client.post(
        f"/api/boqs/{boq['id']}/imports",
        headers=ctx["h"],
        files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert pdf.status_code == 415
    broken = (
        await client.post(
            f"/api/boqs/{boq['id']}/imports",
            headers=ctx["h"],
            files={"file": ("x.xlsx", io.BytesIO(b"PK\x03\x04junk"), "application/octet-stream")},
        )
    ).json()
    await run_jobs()
    failed = (await client.get(f"/api/boq-imports/{broken['id']}", headers=ctx["h"])).json()
    assert failed["status"] == "failed" and "could not be opened" in failed["error"]
    up = (
        await client.post(
            f"/api/boqs/{boq['id']}/imports",
            headers=ctx["h"],
            files={"file": ("a.csv", io.BytesIO(b"ref,mpn,qty\nR1,X,1\n"), "text/csv")},
        )
    ).json()
    await run_jobs()
    parsed = (await client.get(f"/api/boq-imports/{up['id']}", headers=ctx["h"])).json()
    bad = await client.put(
        f"/api/boq-imports/{up['id']}/mapping",
        headers=ctx["h"],
        json={
            "row_version": parsed["row_version"],
            "header_row": 0,
            "mapping": {"spaceship": 0, "qty": 9},
        },
    )
    assert bad.status_code == 422 and bad.json()["error"]["details"] == {
        "unknown_fields": ["spaceship"],
        "bad_columns": [9],
    }


async def test_two_thousand_line_import_under_ten_seconds(
    client: AsyncClient, ctx: dict[str, Any], run_jobs: Any, db_session: AsyncSession
) -> None:
    boq = await _new_boq(client, ctx, create_revision=False)
    start = time.perf_counter()
    v = await _import(client, ctx, run_jobs, boq["id"], "boq-2000.csv")
    r = await client.post(
        f"/api/boq-imports/{v['id']}/commit",
        headers=ctx["h"],
        json={"row_version": v["row_version"], "release": True},
    )
    elapsed = time.perf_counter() - start
    assert r.status_code == 200 and r.json()["line_count"] == 2000
    assert elapsed < 10, f"2,000-line import took {elapsed:.1f}s"
    detail = await _rev(client, ctx, r.json()["id"])
    assert len(detail["lines"]) == 2000
    assert (
        await db_session.execute(
            select(func.count()).select_from(BoqLine).where(BoqLine.revision_id == r.json()["id"])
        )
    ).scalar_one() == 2000


async def test_boq_permissions_and_scope(
    client: AsyncClient, ctx: dict[str, Any], db_session: AsyncSession
) -> None:
    boq = await _new_boq(client, ctx)
    other_div = await create(db_session, DivisionFactory)
    other = await create(db_session, ProjectFactory, division_id=other_div.id)
    await make_user(
        db_session, "boq_scoped", roles=("project_manager",), scopes=(("project", other.id),)
    )
    scoped = await login(client, "boq_scoped")
    assert (await client.get(f"/api/boqs/{boq['id']}", headers=scoped)).status_code == 404
    assert (
        await client.get(f"/api/boq-revisions/{boq['revisions'][0]['id']}", headers=scoped)
    ).status_code == 404
    assert [b["id"] for b in (await client.get("/api/boqs", headers=scoped)).json()] == []
    await make_user(db_session, "boq_viewer", roles=("viewer",))
    viewer = await login(client, "boq_viewer")
    assert (await client.get(f"/api/boqs/{boq['id']}", headers=viewer)).status_code == 403
    await make_user(db_session, "boq_stores", roles=("stores",))
    stores = await login(client, "boq_stores")
    assert (await client.get(f"/api/boqs/{boq['id']}", headers=stores)).status_code == 200
    r = await client.put(
        f"/api/boq-revisions/{boq['revisions'][0]['id']}/lines",
        headers=stores,
        json={"row_version": 1, "lines": []},
    )
    assert r.status_code == 403
    parts_search = await client.get("/api/parts?q=grm188", headers=stores)
    assert parts_search.status_code == 200
    assert "GRM188R71H104KA93D" in [p["mpn"] for p in parts_search.json()]
    exact = (await client.get("/api/parts?q=grm188r71h104ka93d", headers=stores)).json()
    assert exact[0]["mpn"] == "GRM188R71H104KA93D"


async def test_parts_create_inline_and_duplicates(
    client: AsyncClient, ctx: dict[str, Any], db_session: AsyncSession
) -> None:
    await create(db_session, PartFactory, mpn="NEW-1", manufacturer="Acme")
    dup = await client.post(
        "/api/parts",
        headers=ctx["h"],
        json={"mpn": "new 1", "manufacturer": "ACME", "description": "x"},
    )
    assert dup.status_code == 409
    ok = await client.post(
        "/api/parts",
        headers=ctx["h"],
        json={
            "mpn": "NEW-2",
            "manufacturer": "Acme",
            "description": "Fresh part",
            "category": "IC",
        },
    )
    assert ok.status_code == 201 and ok.json()["category"] == "IC"


async def test_sample_boq_seed_is_visible_and_compares(
    client: AsyncClient, ctx: dict[str, Any], db_session: AsyncSession
) -> None:
    from app.seed import SAMPLE_BOQ_NAME, seed_sample_boqs

    assert await seed_sample_boqs(db_session) == 3 + 11 + 11
    assert await seed_sample_boqs(db_session) == 0
    boqs = (await client.get("/api/boqs", headers=ctx["h"])).json()
    sample = next(b for b in boqs if b["name"] == SAMPLE_BOQ_NAME)
    assert [(r["revision"], r["status"], r["line_count"]) for r in sample["revisions"]] == [
        ("A", "released", 11),
        ("B", "draft", 11),
    ]
    a = await _rev(client, ctx, sample["revisions"][0]["id"])
    caps = next(ln for ln in a["lines"] if ln["mpn"] == "GRM188R71H104KA93D")
    # 8 per unit x 25 units x 1.02 (passive attrition) = 204
    assert (caps["ref_des"], caps["required_qty"], caps["status"]) == (
        "C1,C2,C3,C4,C5,C6,C7,C8",
        "204",
        "Not ordered",
    )
    dnp = next(ln for ln in a["lines"] if ln["dnp"])
    assert (dnp["required_qty"], dnp["status"]) == ("0", "Not required")
    cmp = (
        await client.get(f"/api/boqs/{sample['id']}/compare?from=A&to=B", headers=ctx["h"])
    ).json()
    assert {k: v for k, v in cmp["summary"].items() if v} == {
        "added": 1,
        "removed": 1,
        "qty_changed": 1,
        "substituted": 1,
        "unchanged": 8,
    }
