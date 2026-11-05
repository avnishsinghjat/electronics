"""Clear to build, requisition rules, vendors, permissions and scoping, the PO PDF."""

from decimal import Decimal

from app.modules.boq.status import LineStatus, quantities
from tests.factories import ModuleFactory, ProjectFactory, create, login, make_user, uniq
from tests.procurement.conftest import Ctx, po_line

D = Decimal


def test_status_over_receipt_and_rejection_branches() -> None:
    # More received than required (reel MOQ) is still Received; pending can't go negative.
    q = quantities(D(10), ordered=D(25), received=D(25))
    assert (q.status, q.shortfall, q.pending_receipt) == (LineStatus.RECEIVED, 0, 0)
    # Rejected quantity is not received: ordered 10, accepted 6.
    q = quantities(D(10), ordered=D(10), received=D(6))
    assert (q.status, q.pending_receipt) == (LineStatus.PARTIALLY_RECEIVED, 4)
    # Cancelled remainder: ordered falls back to what was received.
    q = quantities(D(10), ordered=D(4), received=D(4))
    assert (q.status, q.shortfall) == (LineStatus.PARTIALLY_RECEIVED, 6)


async def test_clear_to_build_edge_cases(ctx: Ctx) -> None:
    part, dnp_part, zero_part = await ctx.part(), await ctx.part(), await ctx.part()
    lines = await ctx.boq(
        [
            (part, "2", "Passive"),
            (dnp_part, "1", "Passive", {"dnp": True}),
            (zero_part, "0", "Passive"),
        ],
        build_qty=5,
    )
    assert lines[dnp_part.mpn]["status"] == "Not required"
    assert lines[zero_part.mpn]["status"] == "Not required"
    empty = await create(
        ctx.session, ModuleFactory, project_id=ctx.tree["project"].id, code="MOD-EMPTY"
    )
    drafty = await create(
        ctx.session, ModuleFactory, project_id=ctx.tree["project"].id, code="MOD-DRAFT"
    )
    await ctx.boq([(await ctx.part(), "1", "IC")], module_id=drafty.id, release=False)

    def readiness(t: dict, module_id: object) -> dict:
        return next(m for m in t["modules"] if m["module_id"] == str(module_id))

    t = await ctx.tracker()
    main = readiness(t, ctx.tree["module"].id)
    assert (main["clear_to_build"], main["lines"], main["reason"]) == (
        False,
        1,
        "1 of 1 lines not fully received",
    )
    assert readiness(t, empty.id)["reason"] == "No BOQ"
    assert readiness(t, drafty.id)["reason"] == "BOQ revision not released"
    assert t["unreleased_boqs"] and t["kpis"]["lines"] == 4 and t["kpis"]["lines_required"] == 2

    po = await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    await ctx.receive(po, [ctx.grn_line(po["lines"][0], "9")])
    assert readiness(await ctx.tracker(), ctx.tree["module"].id)["clear_to_build"] is False
    await ctx.receive(po, [ctx.grn_line(po["lines"][0], "1")])
    # DNP and zero-quantity lines never block: green once the one real line is in.
    main = readiness(await ctx.tracker(), ctx.tree["module"].id)
    assert (main["clear_to_build"], main["reason"], main["lines_received"]) == (True, None, 1)


async def test_requisition_rules(ctx: Ctx) -> None:
    part = await ctx.part()
    project = ctx.tree["project"].id
    draft_lines = await ctx.boq([(part, "1", "Passive")], release=False)
    r = await ctx.client.post(
        f"/api/projects/{project}/requisitions",
        headers=ctx.pm,
        json={"boq_line_ids": [draft_lines[part.mpn]["id"]]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "revision_not_released"
    r = await ctx.client.post(f"/api/projects/{project}/requisitions", headers=ctx.pm, json={})
    assert r.json()["error"]["code"] == "nothing_to_order"  # unreleased lines are skipped

    other = await ctx.part()
    released = await ctx.boq([(other, "3", "Passive")], build_qty=2)
    pr = await ctx.call(
        "POST",
        f"/projects/{project}/requisitions",
        expect=201,
        boq_line_ids=[released[other.mpn]["id"]],
    )
    assert [ln["qty"] for ln in pr["lines"]] == ["6.0000"]
    assert pr["lines"][0]["boq_ref"].endswith("line 1")
    r = await ctx.client.post(
        f"/api/requisitions/{pr['id']}/convert",
        headers=ctx.buyer,
        json={"row_version": pr["row_version"]},
    )
    assert r.json()["error"]["code"] == "invalid_status_transition"  # not approved yet
    pr = await ctx.call("POST", f"/requisitions/{pr['id']}/submit", row_version=pr["row_version"])
    r = await ctx.client.post(
        f"/api/requisitions/{pr['id']}/decision",
        headers=ctx.pm,
        json={"row_version": pr["row_version"], "approve": False},
    )
    assert r.status_code == 422  # a rejection needs a reason
    pr = await ctx.call(
        "POST",
        f"/requisitions/{pr['id']}/decision",
        row_version=pr["row_version"],
        approve=False,
        note="Wait for client ECO",
    )
    assert (pr["status"], pr["decision_note"]) == ("rejected", "Wait for client ECO")
    # A rejected requisition no longer holds the quantity, and editing it reopens it.
    assert (await ctx.line(other.mpn))["being_ordered"] == "0"
    lines = [
        {"boq_line_id": ln["boq_line_id"], "part_id": ln["part_id"], "qty": "5"}
        for ln in pr["lines"]
    ]
    pr = await ctx.call(
        "PUT", f"/requisitions/{pr['id']}", row_version=pr["row_version"], lines=lines
    )
    assert (pr["status"], pr["decision_note"], pr["lines"][0]["qty"]) == ("draft", None, "5.0000")
    # Approved without a vendor cannot convert.
    pr = await ctx.call("POST", f"/requisitions/{pr['id']}/submit", row_version=pr["row_version"])
    pr = await ctx.call(
        "POST", f"/requisitions/{pr['id']}/decision", row_version=pr["row_version"], approve=True
    )
    r = await ctx.client.post(
        f"/api/requisitions/{pr['id']}/convert",
        headers=ctx.buyer,
        json={"row_version": pr["row_version"]},
    )
    assert (
        r.json()["error"]["code"] == "vendor_missing" and other.mpn in r.json()["error"]["message"]
    )


async def test_po_validation(ctx: Ctx) -> None:
    part, wrong = await ctx.part(), await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    r = await ctx.client.post(
        "/api/purchase-orders",
        headers=ctx.buyer,
        json={
            "vendor_id": str(ctx.vendor.id),
            "lines": [po_line(wrong, "10", allocations=[(lines[part.mpn]["id"], "10")])],
        },
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "allocation_part_mismatch"
    r = await ctx.client.post(
        "/api/purchase-orders",
        headers=ctx.buyer,
        json={
            "vendor_id": str(ctx.vendor.id),
            "lines": [po_line(part, "5", allocations=[(lines[part.mpn]["id"], "10")])],
        },
    )
    assert r.status_code == 422  # allocations exceed the ordered quantity
    po = await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    r = await ctx.client.put(
        f"/api/purchase-orders/{po['id']}",
        headers=ctx.buyer,
        json={
            "row_version": po["row_version"],
            "vendor_id": str(ctx.vendor.id),
            "lines": [po_line(part, "1")],
        },
    )
    assert r.json()["error"]["code"] == "invalid_status_transition"  # issued orders are not edited
    # ...but the promised date is.
    pl = po["lines"][0]
    po = await ctx.call(
        "PATCH",
        f"/po-lines/{pl['id']}",
        h=ctx.buyer,
        row_version=pl["row_version"],
        expected_date="2026-12-01",
        notes="Vendor confirmed by phone",
    )
    assert po["lines"][0]["expected_date"] == "2026-12-01"
    po = await ctx.call(
        "POST",
        f"/purchase-orders/{po['id']}/close",
        h=ctx.buyer,
        row_version=po["row_version"],
        note="Short-closed by agreement",
    )
    assert po["status"] == "closed"
    # Closed orders still count as ordered (CLAUDE.md).
    assert (await ctx.line(part.mpn))["ordered_qty"] == "10.0000"


async def test_vendors(ctx: Ctx) -> None:
    body = {
        "code": "V-NEW-1",
        "name": "New Components",
        "gstin": "27aabcs1234f1z5",
        "contacts": [{"name": "Ravi", "phone": "+91 98", "email": "ravi@example.invalid"}],
        "payment_terms": "30 days",
        "lead_time_days": 21,
        "rating": "4.5",
    }
    v = await ctx.call("POST", "/vendors", h=ctx.buyer, expect=201, **body)
    assert (v["gstin"], v["contacts"][0]["name"]) == ("27AABCS1234F1Z5", "Ravi")
    r = await ctx.client.post("/api/vendors", headers=ctx.buyer, json={**body, "name": "Dup"})
    assert r.status_code == 409
    r = await ctx.client.post(
        "/api/vendors", headers=ctx.buyer, json={**body, "code": "V-X", "gstin": "BAD"}
    )
    assert r.status_code == 422
    r = await ctx.client.post("/api/vendors", headers=ctx.stores, json={**body, "code": "V-Y"})
    assert r.status_code == 403
    v = await ctx.call(
        "PUT",
        f"/vendors/{v['id']}",
        h=ctx.buyer,
        **{**body, "row_version": v["row_version"], "rating": "3.0"},
    )
    assert v["rating"] == "3.0"
    part = await ctx.part()
    po = await ctx.po([po_line(part, "1")], vendor_id=v["id"], issue=False)
    assert (await ctx.get(f"/vendors/{v['id']}"))["open_po_count"] == 1
    r = await ctx.client.delete(
        f"/api/vendors/{v['id']}", headers=ctx.buyer, params={"row_version": v["row_version"]}
    )
    assert (
        r.json()["error"]["code"] == "vendor_in_use"
        and po["number"] in r.json()["error"]["message"]
    )


async def test_permissions_and_scope(ctx: Ctx) -> None:
    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    po = await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    # Role checks in the service layer, reached through the API.
    r = await ctx.client.post(
        "/api/purchase-orders",
        headers=ctx.stores,
        json={"vendor_id": str(ctx.vendor.id), "lines": [po_line(part, "1")]},
    )
    assert r.status_code == 403
    r = await ctx.client.post(
        "/api/goods-receipts",
        headers=ctx.pm,
        json={"purchase_order_id": po["id"], "lines": [ctx.grn_line(po["lines"][0], "1")]},
    )
    assert r.status_code == 403
    assert (
        await ctx.client.get(f"/api/projects/{ctx.tree['project'].id}/tracker", headers=ctx.viewer)
    ).status_code == 403
    # A project manager scoped to another project sees none of it.
    other = await create(ctx.session, ProjectFactory, division_id=ctx.tree["division"].id)
    name = uniq("scoped").replace("-", "_")
    await make_user(ctx.session, name, roles=("project_manager",), scopes=(("project", other.id),))
    scoped = await login(ctx.client, name)
    assert (
        await ctx.client.get(f"/api/purchase-orders/{po['id']}", headers=scoped)
    ).status_code == 404
    assert po["id"] not in {
        p["id"] for p in (await ctx.client.get("/api/purchase-orders", headers=scoped)).json()
    }
    assert (
        await ctx.client.get(f"/api/projects/{ctx.tree['project'].id}/tracker", headers=scoped)
    ).status_code == 404
    assert po["id"] not in {
        p["po_id"]
        for p in (await ctx.client.get("/api/procurement/pending", headers=scoped)).json()
    }


async def test_po_pdf(ctx: Ctx) -> None:
    part = await ctx.part(mpn="GRM188R71H104KA93D")
    po = await ctx.po([po_line(part, "4000", "0.85", expected_date="2026-12-01")], issue=False)
    r = await ctx.client.get(f"/api/purchase-orders/{po['id']}/pdf", headers=ctx.buyer)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and po["number"] in r.headers["content-disposition"]
    import uuid

    from app.core.config import get_settings
    from app.modules.auth.models import User
    from app.modules.auth.service import load_principal
    from app.modules.procurement import pdf

    me = await ctx.client.get("/api/auth/me", headers=ctx.buyer)
    user = await ctx.session.get(User, uuid.UUID(me.json()["id"]))
    assert user is not None
    principal = await load_principal(ctx.session, user)
    context = await pdf.po_context(ctx.session, get_settings(), principal, uuid.UUID(po["id"]))
    assert context["draft"] is True and context["total"] == "3,400.00"
    assert context["lines"][0]["mpn"] == "GRM188R71H104KA93D"
    assert context["company"]["name"] == "Test Electronics"


async def test_sample_purchasing_seed(ctx: Ctx) -> None:
    from app.seed import (
        SAMPLE_BOQ_NAME,
        seed_sample_boqs,
        seed_sample_data,
        seed_sample_procurement,
    )

    await seed_sample_data(ctx.session)
    await seed_sample_boqs(ctx.session)
    assert await seed_sample_procurement(ctx.session) > 0
    assert await seed_sample_procurement(ctx.session) == 0
    boqs = await ctx.get("/boqs")
    project = next(b for b in boqs if b["name"] == SAMPLE_BOQ_NAME)["project_id"]
    t = await ctx.tracker(project)
    status = {ln["mpn"]: ln["status"] for ln in t["lines"]}
    assert status["GRM188R71H104KA93D"] == "Received"
    assert status["RC0603FR-0710KL"] == "Partially received"
    assert status["STM32F407VGT6"] == "Ordered"
    assert status["MCP2551-I/SN"] == "Not ordered"
    assert status["RC0603JR-070RL"] == "Not required"  # DNP
    overdue = {ln["mpn"] for ln in t["lines"] if ln["days_overdue"] > 0}
    assert overdue == {"GRM1885C1H220JA01D", "RC0603FR-0710KL"}
    assert t["kpis"]["lines_to_order"] == 4 and Decimal(t["kpis"]["value_pending"]) > 0


async def test_grn_coc_listings_and_returns(ctx: Ctx) -> None:
    import io

    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    po = await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    grn = await ctx.receive(po, [ctx.grn_line(po["lines"][0], "8", rejected="2")])

    up = await ctx.client.post(
        "/api/files",
        headers=ctx.stores,
        data={"ref_type": "grn", "ref_id": grn["id"]},
        files={"file": ("coc.pdf", io.BytesIO(b"%PDF-1.4 certificate"), "application/pdf")},
    )
    assert up.status_code == 201, up.text
    stranger = await ctx.client.post(
        "/api/files",
        headers=ctx.stores,
        data={"ref_type": "vendor", "ref_id": str(ctx.vendor.id)},
        files={"file": ("terms.pdf", io.BytesIO(b"%PDF-1.4 terms"), "application/pdf")},
    )
    assert stranger.status_code == 201
    r = await ctx.client.patch(
        f"/api/goods-receipts/{grn['id']}",
        headers=ctx.stores,
        json={"row_version": grn["row_version"], "coc_file_id": stranger.json()["id"]},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "file_not_attached"
    grn = await ctx.call(
        "PATCH",
        f"/goods-receipts/{grn['id']}",
        h=ctx.stores,
        row_version=grn["row_version"],
        coc_file_id=up.json()["id"],
        delivery_note_ref="DN-77",
        notes="CoC received",
    )
    assert (grn["coc_file_id"], grn["delivery_note_ref"]) == (up.json()["id"], "DN-77")

    listed = {g["id"]: g for g in await ctx.get("/goods-receipts", po_id=po["id"])}
    assert (
        listed[grn["id"]]["qty_accepted"] == "8.0000"
        and listed[grn["id"]]["po_number"] == po["number"]
    )
    returns = [
        r for r in await ctx.get("/vendor-returns", status="open") if r["grn_id"] == grn["id"]
    ]
    assert [(r["qty"], r["mpn"], r["po_number"]) for r in returns] == [
        ("2.0000", part.mpn, po["number"])
    ]
    closed = await ctx.call(
        "PATCH",
        f"/vendor-returns/{returns[0]['id']}",
        h=ctx.stores,
        row_version=returns[0]["row_version"],
        status="closed",
    )
    r = await ctx.client.patch(
        f"/api/vendor-returns/{closed['id']}",
        headers=ctx.stores,
        json={"row_version": closed["row_version"], "status": "open"},
    )
    assert r.json()["error"]["code"] == "invalid_status_transition"

    orders = await ctx.get(
        "/purchase-orders", status="partially_received", project_id=str(ctx.tree["project"].id)
    )
    assert po["id"] in {o["id"] for o in orders}
    prs = await ctx.get("/requisitions", project_id=str(ctx.tree["project"].id), status="draft")
    assert prs == []
    await ctx.boq([(await ctx.part(), "1", "Passive")], build_qty=3)
    pr = await ctx.call("POST", f"/projects/{ctx.tree['project'].id}/requisitions", expect=201)
    assert [p["number"] for p in await ctx.get("/requisitions", status="draft")].count(
        pr["number"]
    ) == 1
    await ctx.call(
        "DELETE", f"/requisitions/{pr['id']}?row_version={pr['row_version']}", expect=204
    )
    vendors = await ctx.get("/vendors", q=ctx.vendor.code)
    assert [v["id"] for v in vendors] == [str(ctx.vendor.id)]
