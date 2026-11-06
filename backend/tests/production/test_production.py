"""Phase 7: release gate and override audit, kitting ledger and returns, serials, stage
gating by QC, lot-tracked progress, genealogy, scan, board, templates and labels."""

import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.audit import AuditLog
from app.modules.inventory import service as inventory
from app.modules.inventory.models import LedgerEntry, ReservationStatus, StockReservation
from app.modules.qc.models import QcInspection, QcTemplate
from tests.procurement.conftest import Ctx
from tests.production.conftest import Plant, make_plant

D = Decimal


async def _template(c: Ctx, steps: list[tuple[str, str, bool]]) -> dict[str, Any]:
    t = await c.call("POST", "/stage-templates", expect=201, name=f"T-{uuid.uuid4().hex[:6]}")
    return await c.call(
        "PUT",
        f"/stage-templates/{t['id']}",
        row_version=t["row_version"],
        name=t["name"],
        steps=[{"stage_code": code, "name": name, "requires_qc": qc} for code, name, qc in steps],
    )


async def _use_template(c: Ctx, template_id: str) -> None:
    a = c.tree["assembly"]
    a.stage_template_id = uuid.UUID(template_id)
    await c.session.flush()


# ---------------------------------------------------------------- release gate


async def test_release_gate_and_override_audit(ctx: Ctx) -> None:
    p = await make_plant(ctx, receive=False)
    wo = await p.wo(release=False)
    assert wo["readiness"] == {
        "clear_to_build": False,
        "reason": "2 of 2 lines not fully received",
        "lines": 2,
        "lines_received": 0,
    }
    r = await ctx.client.post(
        f"/api/work-orders/{wo['id']}/release",
        headers=p.production,
        json={"row_version": wo["row_version"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_clear_to_build"
    r = await ctx.client.post(
        f"/api/work-orders/{wo['id']}/release",
        headers=p.production,
        json={"row_version": wo["row_version"], "override_reason": "Client wants a pilot run"},
    )
    assert r.status_code == 403  # production may release, but not override
    wo = await ctx.call(
        "POST",
        f"/work-orders/{wo['id']}/release",
        row_version=wo["row_version"],
        override_reason="Pilot run of 5 approved by client; MCUs borrowed from stock",
    )
    assert (wo["status"], wo["release_override_reason"]) == (
        "released",
        "Pilot run of 5 approved by client; MCUs borrowed from stock",
    )
    event = (
        await ctx.session.execute(
            select(AuditLog).where(
                AuditLog.entity_id == wo["id"], AuditLog.action == "release_override"
            )
        )
    ).scalar_one()
    assert (
        event.after is not None
        and event.after["reason"].startswith("Pilot run")
        and event.actor_id is not None
    )
    assert event.after["readiness"] == "2 of 2 lines not fully received"


async def test_release_when_clear_needs_no_reason(plant: Plant) -> None:
    c = plant.ctx
    wo = await plant.wo(release=False)
    assert wo["readiness"]["clear_to_build"] is True
    wo = await c.call(
        "POST",
        f"/work-orders/{wo['id']}/release",
        h=plant.production,
        row_version=wo["row_version"],
    )
    assert wo["status"] == "released" and wo["release_override_reason"] is None
    r = await c.client.post(
        f"/api/work-orders/{wo['id']}/release",
        headers=c.pm,
        json={"row_version": wo["row_version"]},
    )
    assert r.json()["error"]["code"] == "invalid_status_transition"
    r = await c.client.put(
        f"/api/work-orders/{wo['id']}",
        headers=c.pm,
        json={"row_version": wo["row_version"], "build_qty": 3},
    )
    assert r.json()["error"]["code"] == "invalid_status_transition"


# ---------------------------------------------------------------- kitting


async def test_kitting_ledger_entries_and_returns(plant: Plant) -> None:
    c = plant.ctx
    res, mcu = plant.parts
    draft = await plant.wo(build_qty=4, release=False)
    r = await c.client.post(
        f"/api/work-orders/{draft['id']}/kit/issue",
        headers=c.stores,
        json={
            "issues": [
                {
                    "boq_line_id": plant.lines[res.mpn]["id"],
                    "location_id": str(c.stores_loc.id),
                    "qty": "1",
                }
            ]
        },
    )
    assert r.json()["error"]["code"] == "wo_not_released"
    wo = await c.call(
        "POST", f"/work-orders/{draft['id']}/release", row_version=draft["row_version"]
    )
    kit = await c.get(f"/work-orders/{wo['id']}/kit")
    lines = {ln["mpn"]: ln for ln in kit["lines"]}
    assert (lines[res.mpn]["required"], lines[mcu.mpn]["required"]) == ("8", "4")  # 2 x 4, 1 x 4
    assert kit["complete"] is False and lines[res.mpn]["reserved_for_project"] == "20.0000"

    lots = {
        (x["location_code"], x["lot_code"]): x["qty"]
        for x in await c.get("/inventory/lots", part_id=str(res.id))
    }
    assert lots == {("STORES", "RES-L1"): "10.0000", ("STORES", "RES-L2"): "10.0000"}
    r = await c.client.post(
        f"/api/work-orders/{wo['id']}/kit/issue",
        headers=c.stores,
        json={
            "issues": [
                {
                    "boq_line_id": plant.lines[res.mpn]["id"],
                    "location_id": str(c.stores_loc.id),
                    "qty": "11",
                    "lot_code": "RES-L1",
                }
            ]
        },
    )
    assert r.status_code == 409  # only 10 in that lot (and only 8 needed)
    r = await c.client.post(
        f"/api/work-orders/{wo['id']}/kit/issue",
        headers=c.stores,
        json={
            "issues": [
                {
                    "boq_line_id": plant.lines[res.mpn]["id"],
                    "location_id": str(c.stores_loc.id),
                    "qty": "9",
                    "lot_code": "RES-L1",
                }
            ]
        },
    )
    assert r.json()["error"]["code"] == "over_issue"

    recs = await c.call(
        "POST",
        f"/work-orders/{wo['id']}/kit/issue",
        h=c.stores,
        expect=201,
        issues=[
            {
                "boq_line_id": plant.lines[res.mpn]["id"],
                "location_id": str(c.stores_loc.id),
                "qty": "5",
                "lot_code": "RES-L1",
            },
            {
                "boq_line_id": plant.lines[res.mpn]["id"],
                "location_id": str(c.stores_loc.id),
                "qty": "3",
                "lot_code": "RES-L2",
            },
            {
                "boq_line_id": plant.lines[mcu.mpn]["id"],
                "location_id": str(c.msl_loc.id),
                "qty": "4",
                "lot_code": "MCU-L1",
            },
        ],
    )
    assert [(x["mpn"], x["lot_code"], x["qty"]) for x in recs] == [
        (res.mpn, "RES-L1", "5"),
        (res.mpn, "RES-L2", "3"),
        (mcu.mpn, "MCU-L1", "4"),
    ]
    issues = (
        (
            await c.session.execute(
                select(LedgerEntry)
                .where(LedgerEntry.part_id == res.id, LedgerEntry.reason == "ISSUE")
                .order_by(LedgerEntry.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(e.qty_delta, e.lot_code, e.ref_type, str(e.ref_id), e.project_id) for e in issues] == [
        (D(-5), "RES-L1", "boq_line", plant.lines[res.mpn]["id"], c.tree["project"].id),
        (D(-3), "RES-L2", "boq_line", plant.lines[res.mpn]["id"], c.tree["project"].id),
    ]
    kit = await c.get(f"/work-orders/{wo['id']}/kit")
    assert kit["complete"] is True
    reserved = (
        (
            await c.session.execute(
                select(StockReservation).where(
                    StockReservation.part_id == res.id,
                    StockReservation.status == ReservationStatus.ACTIVE.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert sum((r_.qty for r_ in reserved), D(0)) == 12  # 20 reserved at receipt - 8 issued
    line = await c.line(res.mpn)
    assert (line["issued_qty"], line["status"]) == ("8.0000", "Received")

    # Return 2 of lot RES-L2: ledger RETURN, reserved again, net issued 6.
    r = await c.client.post(
        f"/api/work-orders/{wo['id']}/kit/return",
        headers=c.stores,
        json={
            "boq_line_id": plant.lines[res.mpn]["id"],
            "location_id": str(c.stores_loc.id),
            "qty": "4",
            "lot_code": "RES-L2",
        },
    )
    assert r.json()["error"]["code"] == "return_exceeds_issue"
    ret = await c.call(
        "POST",
        f"/work-orders/{wo['id']}/kit/return",
        h=c.stores,
        expect=201,
        boq_line_id=plant.lines[res.mpn]["id"],
        location_id=str(c.stores_loc.id),
        qty="2",
        lot_code="RES-L2",
        note="Spare after SMT",
    )
    assert ret["kind"] == "return"
    assert (await c.line(res.mpn))["issued_qty"] == "6.0000"
    assert await inventory.stock_on_hand(c.session, res.id) == 14  # 20 received - 8 + 2
    assert await inventory.verify_balances(c.session) == []
    r = await c.client.post(
        f"/api/work-orders/{wo['id']}/cancel", headers=c.pm, json={"row_version": wo["row_version"]}
    )
    assert r.json()["error"]["code"] == "kit_not_returned"
    records = await c.get(f"/work-orders/{wo['id']}/kit/records")
    assert [x["kind"] for x in records] == ["return", "issue", "issue", "issue"]
    assert (
        await c.client.post(
            f"/api/work-orders/{wo['id']}/kit/issue",
            headers=c.qc_lead,
            json={
                "issues": [
                    {
                        "boq_line_id": plant.lines[res.mpn]["id"],
                        "location_id": str(c.stores_loc.id),
                        "qty": "1",
                    }
                ]
            },
        )
    ).status_code == 403


# ---------------------------------------------------------------- serials


async def test_serial_generation_format_and_limits(plant: Plant) -> None:
    c = plant.ctx
    await c.call("PUT", "/settings/company", h=await _admin(c), **await _company_body(c, "FT"))
    wo = await plant.wo(build_qty=3)
    units = await c.call("POST", f"/work-orders/{wo['id']}/serials", expect=201, count=2)
    code = re.sub(r"[^A-Z0-9]", "", c.tree["assembly"].code.upper())
    assert all(re.fullmatch(rf"FT-{code}-\d{{4}}-\d{{5}}", u["serial_number"]) for u in units)
    numbers = [int(u["serial_number"][-5:]) for u in units]
    more = await c.call("POST", f"/work-orders/{wo['id']}/serials", expect=201)
    assert len(more) == 3 and int(more[-1]["serial_number"][-5:]) == numbers[-1] + 1
    r = await c.client.post(f"/api/work-orders/{wo['id']}/serials", headers=c.pm, json={"count": 1})
    assert r.json()["error"]["code"] == "serials_exceed_lot"
    lot_only = await plant.wo(build_qty=2, track_serials=False)
    r = await c.client.post(f"/api/work-orders/{lot_only['id']}/serials", headers=c.pm, json={})
    assert r.json()["error"]["code"] == "lot_tracked"
    pdf = await c.client.get(f"/api/work-orders/{wo['id']}/labels.pdf", headers=plant.production)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def _admin(c: Ctx) -> dict[str, str]:
    from tests.factories import login, make_user, uniq

    name = uniq("adm").replace("-", "_")
    await make_user(c.session, name, roles=("admin",))
    return await login(c.client, name)


async def _company_body(c: Ctx, prefix: str) -> dict[str, Any]:
    from app.modules.settings.models import CompanySettings

    company = (await c.session.execute(select(CompanySettings))).scalar_one()
    return {
        "row_version": company.row_version,
        "company_name": company.company_name,
        "address": company.address,
        "serial_prefix": prefix,
    }


# ---------------------------------------------------------------- stage progress and QC gating


async def test_stage_gating_by_qc_cannot_be_bypassed(plant: Plant) -> None:
    c = plant.ctx
    t = await _template(
        c, [("kitting", "Kitting", False), ("aoi", "AOI", True), ("packing", "Packing", False)]
    )
    await _use_template(c, t["id"])
    wo = await plant.wo(build_qty=2)
    kit_stage, aoi, packing = wo["stages"]
    units = await c.call("POST", f"/work-orders/{wo['id']}/serials", expect=201)
    u1, u2 = units[0]["id"], units[1]["id"]
    op = plant.production

    async def act(
        stage: dict[str, Any], unit: str, action: str, expect: int = 200, **kw: Any
    ) -> Any:
        return await c.call(
            "POST",
            f"/work-order-stages/{stage['id']}/progress",
            h=op,
            expect=expect,
            action=action,
            serial_unit_id=unit,
            **kw,
        )

    r = await act(aoi, u1, "start", expect=409)
    assert r["error"]["code"] == "previous_stage_open"
    await act(kit_stage, u1, "start")
    await act(kit_stage, u1, "complete", passed=True)
    await act(aoi, u1, "start")
    r = await act(aoi, u1, "complete", expect=409, passed=True)  # straight to complete: refused
    assert r["error"]["code"] == "qc_required"
    p = await act(aoi, u1, "finish", passed=True)
    assert p["status"] == "awaiting_qc"
    r = await act(aoi, u1, "complete", expect=409)
    assert r["error"]["code"] == "qc_required"
    r = await act(packing, u1, "start", expect=409)
    assert r["error"]["code"] == "previous_stage_open"
    detail = await c.get(f"/work-orders/{wo['id']}")
    assert [s["status"] for s in detail["stages"]] == ["in_progress", "awaiting_qc", "not_started"]
    assert detail["status"] == "in_progress"

    # A failed inspection does not open the gate; a passed one does.
    tpl = QcTemplate(
        code=f"AOI-{uuid.uuid4().hex[:6]}", name="AOI check", stage_code="aoi", status="active"
    )
    c.session.add(tpl)
    await c.session.flush()
    lot_id = uuid.UUID(detail["lot_id"])
    c.session.add(
        QcInspection(
            number=f"QC-T-{uuid.uuid4().hex[:6]}",
            template_id=tpl.id,
            work_order_stage_id=uuid.UUID(aoi["id"]),
            serial_unit_id=uuid.UUID(u1),
            lot_id=lot_id,
            stage_code="aoi",
            status="failed",
        )
    )
    await c.session.flush()
    assert (await act(aoi, u1, "complete", expect=409))["error"]["code"] == "qc_required"
    c.session.add(
        QcInspection(
            number=f"QC-T-{uuid.uuid4().hex[:6]}",
            template_id=tpl.id,
            work_order_stage_id=uuid.UUID(aoi["id"]),
            serial_unit_id=uuid.UUID(u1),
            lot_id=lot_id,
            stage_code="aoi",
            status="passed",
        )
    )
    await c.session.flush()
    assert (await act(aoi, u1, "complete"))["status"] == "completed"
    # The passed inspection was for unit 1 only.
    await act(kit_stage, u2, "start")
    await act(kit_stage, u2, "complete", passed=True)
    await act(aoi, u2, "start")
    await act(aoi, u2, "finish", passed=False)
    assert (await act(aoi, u2, "complete", expect=409))["error"]["code"] == "qc_required"
    # A lot-level inspection covers every unit of the lot.
    c.session.add(
        QcInspection(
            number=f"QC-T-{uuid.uuid4().hex[:6]}",
            template_id=tpl.id,
            work_order_stage_id=uuid.UUID(aoi["id"]),
            lot_id=lot_id,
            stage_code="aoi",
            status="passed",
        )
    )
    await c.session.flush()
    assert (await act(aoi, u2, "complete"))["qty_failed"] == 1
    r = await act(packing, u2, "start", expect=409)  # unit 2 failed AOI
    assert r["error"]["code"] == "previous_stage_open"
    await act(packing, u1, "start")
    await act(packing, u1, "complete", passed=True)
    units = {u["serial_number"]: u for u in await c.get(f"/work-orders/{wo['id']}/units")}
    assert sorted(u["status"] for u in units.values()) == ["failed", "passed"]
    detail = await c.get(f"/work-orders/{wo['id']}")
    assert (detail["status"], detail["units_completed"], detail["units_failed"]) == (
        "completed",
        1,
        1,
    )
    r = await c.client.post(
        f"/api/work-order-stages/{packing['id']}/progress",
        headers=c.viewer,
        json={"action": "start", "serial_unit_id": u1},
    )
    assert r.status_code == 403


async def test_lot_tracked_progress(plant: Plant) -> None:
    c = plant.ctx
    t = await _template(c, [("smt", "SMT", False), ("functional_test", "Test", False)])
    await _use_template(c, t["id"])
    wo = await plant.wo(build_qty=10, track_serials=False)
    smt, test = wo["stages"]
    op = plant.production
    r = await c.client.post(
        f"/api/work-order-stages/{smt['id']}/progress",
        headers=op,
        json={"action": "start", "serial_unit_id": str(uuid.uuid4())},
    )
    assert r.json()["error"]["code"] == "lot_tracked"
    await c.call("POST", f"/work-order-stages/{smt['id']}/progress", h=op, action="start")
    r = await c.client.post(
        f"/api/work-order-stages/{smt['id']}/progress",
        headers=op,
        json={"action": "complete", "qty_passed": 9},
    )
    assert r.json()["error"]["code"] == "qty_mismatch"
    r = await c.client.post(
        f"/api/work-order-stages/{smt['id']}/progress",
        headers=op,
        json={"action": "finish", "qty_passed": 10, "qty_failed": 0},
    )
    assert r.json()["error"]["code"] == "no_qc_needed"
    await c.call(
        "POST",
        f"/work-order-stages/{smt['id']}/progress",
        h=op,
        action="complete",
        qty_passed=9,
        qty_failed=1,
    )
    await c.call("POST", f"/work-order-stages/{test['id']}/progress", h=op, action="start")
    r = await c.client.post(
        f"/api/work-order-stages/{test['id']}/progress",
        headers=op,
        json={"action": "complete", "qty_passed": 10, "qty_failed": 0},
    )
    assert "9 units" in r.json()["error"]["message"]  # only 9 reached the test stage
    await c.call(
        "POST",
        f"/work-order-stages/{test['id']}/progress",
        h=op,
        action="complete",
        qty_passed=9,
        qty_failed=0,
    )
    detail = await c.get(f"/work-orders/{wo['id']}")
    assert (detail["status"], detail["units_completed"], detail["units_failed"]) == (
        "completed",
        9,
        1,
    )
    assert [(s["units_in"], s["units_done"]) for s in detail["stages"]] == [(10, 9), (9, 9)]
    wo2 = await c.call("POST", f"/work-orders/{wo['id']}/close", row_version=detail["row_version"])
    assert wo2["status"] == "closed"


# ---------------------------------------------------------------- genealogy, scan, board


async def test_genealogy_returns_the_part_lots_of_a_serial(plant: Plant) -> None:
    c = plant.ctx
    res, mcu = plant.parts
    wo = await plant.wo(build_qty=5)
    await c.call(
        "POST",
        f"/work-orders/{wo['id']}/kit/issue",
        h=c.stores,
        expect=201,
        issues=[
            {
                "boq_line_id": plant.lines[res.mpn]["id"],
                "location_id": str(c.stores_loc.id),
                "qty": "6",
                "lot_code": "RES-L1",
            },
            {
                "boq_line_id": plant.lines[res.mpn]["id"],
                "location_id": str(c.stores_loc.id),
                "qty": "4",
                "lot_code": "RES-L2",
            },
            {
                "boq_line_id": plant.lines[mcu.mpn]["id"],
                "location_id": str(c.msl_loc.id),
                "qty": "5",
                "lot_code": "MCU-L1",
            },
        ],
    )
    # Returning all of a lot removes it from the genealogy.
    await c.call(
        "POST",
        f"/work-orders/{wo['id']}/kit/return",
        h=c.stores,
        expect=201,
        boq_line_id=plant.lines[res.mpn]["id"],
        location_id=str(c.stores_loc.id),
        qty="4",
        lot_code="RES-L2",
    )
    other = await plant.wo(build_qty=1)
    await c.call(
        "POST",
        f"/work-orders/{other['id']}/kit/issue",
        h=c.stores,
        expect=201,
        issues=[
            {
                "boq_line_id": plant.lines[res.mpn]["id"],
                "location_id": str(c.stores_loc.id),
                "qty": "2",
                "lot_code": "RES-L2",
            }
        ],
    )
    units = await c.call("POST", f"/work-orders/{wo['id']}/serials", expect=201)
    g = await c.get(f"/serial-units/{units[2]['id']}/genealogy")
    assert (g["work_order_number"], g["serial_number"]) == (wo["number"], units[2]["serial_number"])
    assert [(p["mpn"], p["lot_code"], p["qty"]) for p in g["parts"]] == [
        (res.mpn, "RES-L1", "6.0000"),
        (mcu.mpn, "MCU-L1", "5.0000"),
    ]


async def test_scan_and_board(plant: Plant) -> None:
    c = plant.ctx
    t = await _template(c, [("smt", "SMT", False), ("reflow", "Reflow", True)])
    await _use_template(c, t["id"])
    draft = await plant.wo(build_qty=1, release=False)
    wo = await plant.wo(build_qty=1)
    unit = (await c.call("POST", f"/work-orders/{wo['id']}/serials", expect=201))[0]
    scan = await c.get("/production/scan", h=plant.production, code=unit["serial_number"].lower())
    assert (scan["work_order_number"], scan["stage_name"], scan["next_action"]) == (
        wo["number"],
        "SMT",
        "start",
    )
    smt, reflow = wo["stages"]
    await c.call(
        "POST",
        f"/work-order-stages/{smt['id']}/progress",
        h=plant.production,
        action="start",
        serial_unit_id=unit["id"],
    )
    assert (await c.get("/production/scan", code=unit["serial_number"]))[
        "next_action"
    ] == "complete"
    await c.call(
        "POST",
        f"/work-order-stages/{smt['id']}/progress",
        h=plant.production,
        action="complete",
        serial_unit_id=unit["id"],
        passed=True,
    )
    await c.call(
        "POST",
        f"/work-order-stages/{reflow['id']}/progress",
        h=plant.production,
        action="start",
        serial_unit_id=unit["id"],
    )
    scan = await c.get("/production/scan", code=unit["serial_number"])
    assert (scan["stage_name"], scan["next_action"], scan["stage_requires_qc"]) == (
        "Reflow",
        "finish",
        True,
    )
    r = await c.client.get("/api/production/scan", headers=c.pm, params={"code": "NOPE-1"})
    assert r.status_code == 404
    board = {
        col["key"]: [card["number"] for card in col["cards"]]
        for col in await c.get("/production/board")
    }
    assert draft["number"] in board["draft"] and wo["number"] in board["reflow"]


async def test_stage_templates(plant: Plant) -> None:
    c = plant.ctx
    templates = await c.get("/production/stage-templates")
    default = next(t for t in templates if t["is_default"])
    assert len(default["steps"]) == 12 and default["assembly_count"] >= 0
    t = await c.call(
        "POST", "/stage-templates", expect=201, name="Through-hole only", copy_from_id=default["id"]
    )
    assert len(t["steps"]) == 12
    t = await c.call(
        "PUT",
        f"/stage-templates/{t['id']}",
        row_version=t["row_version"],
        name="Through-hole only",
        steps=[
            {"stage_code": "tht", "name": "THT insertion", "requires_qc": False},
            {"stage_code": "custom", "name": "Potting", "requires_qc": True},
            {"stage_code": "packing", "name": "Packing", "requires_qc": False},
        ],
    )
    assert [(s["seq"], s["name"], s["requires_qc"]) for s in t["steps"]] == [
        (1, "THT insertion", False),
        (2, "Potting", True),
        (3, "Packing", False),
    ]
    r = await c.client.post(
        "/api/stage-templates", headers=c.pm, json={"name": "through-hole ONLY"}
    )
    assert r.status_code == 409
    await _use_template(c, t["id"])
    r = await c.client.delete(
        f"/api/stage-templates/{t['id']}", headers=c.pm, params={"row_version": t["row_version"]}
    )
    assert r.json()["error"]["code"] == "template_in_use"
    r = await c.client.delete(
        f"/api/stage-templates/{default['id']}",
        headers=c.pm,
        params={"row_version": default["row_version"]},
    )
    assert r.json()["error"]["code"] == "template_is_default"
    # A new work order copies the template's stages; later template edits don't touch it.
    wo = await plant.wo(build_qty=1, release=False)
    assert [s["name"] for s in wo["stages"]] == ["THT insertion", "Potting", "Packing"]
    assert (
        await c.client.post("/api/stage-templates", headers=c.stores, json={"name": "x"})
    ).status_code == 403


async def test_sample_production_seed(ctx: Ctx) -> None:
    from app.seed import (
        seed_sample_boqs,
        seed_sample_data,
        seed_sample_procurement,
        seed_sample_production,
    )

    await seed_sample_data(ctx.session)
    await seed_sample_boqs(ctx.session)
    await seed_sample_procurement(ctx.session)
    assert await seed_sample_production(ctx.session) > 0
    assert await seed_sample_production(ctx.session) == 0
    orders = [
        wo
        for wo in await ctx.get("/work-orders")
        if wo["notes"] and wo["notes"].startswith("SAMPLE DATA")
    ]
    by_status = {wo["status"]: wo for wo in orders}
    assert set(by_status) == {"draft", "in_progress"}
    pilot = await ctx.get(f"/work-orders/{by_status['in_progress']['id']}")
    assert pilot["serial_count"] == 5 and pilot["current_stage"] == "SMT placement"
    assert [s["status"] for s in pilot["stages"][:3]] == ["completed", "in_progress", "not_started"]
    assert pilot["release_override_reason"].startswith("Sample:")
    draft = await ctx.get(f"/work-orders/{by_status['draft']['id']}")
    assert draft["readiness"]["clear_to_build"] is False
