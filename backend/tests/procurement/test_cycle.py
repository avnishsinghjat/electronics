"""Shortfall -> PR -> PO -> GRN -> issue, with the status service, ledger and
reservations checked at each step."""

from decimal import Decimal

from sqlalchemy import func, select

from app.modules.inventory import service as inventory
from app.modules.inventory.models import LedgerEntry, StockReservation
from tests.procurement.conftest import Ctx, po_line

D = Decimal


async def test_full_cycle_keeps_ledger_consistent(ctx: Ctx) -> None:
    res = await ctx.part(category="Passive")
    mcu = await ctx.part(category="IC", msl_level=3)
    lines = await ctx.boq([(res, "10", "Passive"), (mcu, "1", "IC")], build_qty=10)
    assert lines[res.mpn]["required_qty"] == "100"

    # 1. Requisition everything short; nothing is ordered yet.
    pr = await ctx.call("POST", f"/projects/{ctx.tree['project'].id}/requisitions", expect=201)
    assert pr["status"] == "draft" and pr["project_code"] == ctx.tree["project"].code
    assert {(ln["mpn"], ln["qty"]) for ln in pr["lines"]} == {
        (res.mpn, "100.0000"),
        (mcu.mpn, "10.0000"),
    }
    # Again: everything is on a requisition now.
    again = await ctx.client.post(
        f"/api/projects/{ctx.tree['project'].id}/requisitions", headers=ctx.pm, json={}
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "nothing_to_order"
    line = await ctx.line(res.mpn)
    assert (line["status"], line["being_ordered"], line["shortfall"]) == (
        "Not ordered",
        "100.0000",
        "100",
    )

    # 2. Vendor on each line, submit, approve (PM), convert (purchase).
    vendor_lines = [
        {
            "boq_line_id": ln["boq_line_id"],
            "part_id": ln["part_id"],
            "qty": ln["qty"],
            "suggested_vendor_id": str(ctx.vendor.id),
        }
        for ln in pr["lines"]
    ]
    pr = await ctx.call(
        "PUT", f"/requisitions/{pr['id']}", row_version=pr["row_version"], lines=vendor_lines
    )
    pr = await ctx.call("POST", f"/requisitions/{pr['id']}/submit", row_version=pr["row_version"])
    denied = await ctx.client.post(
        f"/api/requisitions/{pr['id']}/decision",
        headers=ctx.buyer,
        json={"row_version": pr["row_version"], "approve": True},
    )
    assert denied.status_code == 403  # purchase cannot approve its own requisitions
    pr = await ctx.call(
        "POST", f"/requisitions/{pr['id']}/decision", row_version=pr["row_version"], approve=True
    )
    assert pr["status"] == "approved" and pr["approved_by_name"]
    orders = await ctx.call(
        "POST", f"/requisitions/{pr['id']}/convert", h=ctx.buyer, row_version=pr["row_version"]
    )
    assert len(orders) == 1 and orders[0]["status"] == "draft"
    po = await ctx.get(f"/purchase-orders/{orders[0]['id']}", h=ctx.buyer)
    assert po["requisition_number"] == pr["number"] and po["project_codes"] == [
        ctx.tree["project"].code
    ]
    # A draft PO is not ordered yet, but is "being ordered".
    line = await ctx.line(res.mpn)
    assert (line["ordered_qty"], line["being_ordered"]) == ("0", "100.0000")

    # 3. Issue needs prices.
    r = await ctx.client.post(
        f"/api/purchase-orders/{po['id']}/issue",
        headers=ctx.buyer,
        json={"row_version": po["row_version"]},
    )
    assert r.json()["error"]["code"] == "price_missing"
    edited = [
        po_line(
            res if pl["part_id"] == str(res.id) else mcu,
            pl["qty_ordered"],
            "0.12" if pl["part_id"] == str(res.id) else "410.00",
            allocations=[(a["boq_line_id"], a["qty"]) for a in pl["allocations"]],
            expected_date="2026-11-20",
        )
        for pl in po["lines"]
    ]
    po = await ctx.call(
        "PUT",
        f"/purchase-orders/{po['id']}",
        h=ctx.buyer,
        row_version=po["row_version"],
        vendor_id=str(ctx.vendor.id),
        lines=edited,
    )
    po = await ctx.call(
        "POST", f"/purchase-orders/{po['id']}/issue", h=ctx.buyer, row_version=po["row_version"]
    )
    assert po["status"] == "issued" and D(po["total"]) == D("4112.00")
    line = await ctx.line(res.mpn)
    assert (line["status"], line["ordered_qty"], line["pending_receipt"]) == (
        "Ordered",
        "100.0000",
        "100.0000",
    )
    assert line["purchase_orders"][0]["po_number"] == po["number"]

    # 4. Partial receipt: 60 of 100 resistors, MCU into the MSL cabinet.
    res_pl = next(pl for pl in po["lines"] if pl["part_id"] == str(res.id))
    mcu_pl = next(pl for pl in po["lines"] if pl["part_id"] == str(mcu.id))
    grn = await ctx.receive(
        po,
        [
            ctx.grn_line(res_pl, "60", batch_lot="L2611", date_code="2644"),
            ctx.grn_line(mcu_pl, "10", location_id=ctx.msl_loc.id, batch_lot="M1"),
        ],
    )
    assert grn["lines"][1]["msl_level"] == 3  # defaulted from the part master
    assert grn["lines"][0]["allocated"][0]["qty"] == "60.0000"
    line = await ctx.line(res.mpn)
    assert (line["status"], line["received_qty"], line["pending_receipt"]) == (
        "Partially received",
        "60.0000",
        "40.0000",
    )
    assert (await ctx.line(mcu.mpn))["status"] == "Received"
    po = await ctx.get(f"/purchase-orders/{po['id']}")
    assert po["status"] == "partially_received"
    rows = (
        (
            await ctx.session.execute(
                select(LedgerEntry).where(LedgerEntry.part_id == res.id).order_by(LedgerEntry.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(r.reason, r.qty_delta, r.project_id, r.lot_code) for r in rows] == [
        ("GRN", D(60), ctx.tree["project"].id, "L2611")
    ]
    reserved = (
        await ctx.session.execute(
            select(func.sum(StockReservation.qty)).where(StockReservation.part_id == res.id)
        )
    ).scalar_one()
    assert reserved == D(60)

    # 5. Final receipt.
    await ctx.receive(po, [ctx.grn_line(res_pl, "40")])
    assert (await ctx.line(res.mpn))["status"] == "Received"
    po = await ctx.get(f"/purchase-orders/{po['id']}")
    assert po["status"] == "received" and po["next_expected"] is None

    # 6. Kitting issue (the Phase 7 entry point) -> Issued; ledger and balances agree.
    await inventory.issue_to_boq_line(
        ctx.session,
        part_id=res.id,
        location_id=ctx.stores_loc.id,
        qty=100,
        boq_line_id=lines[res.mpn]["id"],
        project_id=ctx.tree["project"].id,
    )
    await ctx.session.flush()
    line = await ctx.line(res.mpn)
    assert (line["status"], line["issued_qty"]) == ("Issued", "100.0000")
    assert await inventory.stock_on_hand(ctx.session, res.id) == 0
    assert await inventory.stock_on_hand(ctx.session, mcu.id, ctx.msl_loc.id) == 10
    assert await inventory.verify_balances(ctx.session) == []
    t = await ctx.tracker()
    assert t["kpis"]["pct_fully_received"] == 100.0 and t["kpis"]["value_pending"] == "0"
    module = next(m for m in t["modules"] if m["module_id"] == str(ctx.tree["module"].id))
    assert module["clear_to_build"] is True


async def test_rejection_at_grn_creates_a_return_and_stays_outstanding(ctx: Ctx) -> None:
    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    po = await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    pl = po["lines"][0]
    grn = await ctx.receive(po, [ctx.grn_line(pl, "6", rejected="4")])
    assert grn["lines"][0]["inspection_result"] == "partial"
    assert [(r["qty"], r["status"]) for r in grn["returns"]] == [("4.0000", "open")]
    line = await ctx.line(part.mpn)
    assert (line["status"], line["received_qty"], line["pending_receipt"]) == (
        "Partially received",
        "6.0000",
        "4.0000",
    )
    assert await inventory.stock_on_hand(ctx.session, part.id) == 6  # rejects never post
    po = await ctx.get(f"/purchase-orders/{po['id']}")
    assert po["lines"][0]["outstanding"] == "4.0000" and po["lines"][0]["qty_rejected"] == "4.0000"

    # The replacement arrives and clears it; the return is tracked to closure.
    await ctx.receive(po, [ctx.grn_line(pl, "4")])
    assert (await ctx.line(part.mpn))["status"] == "Received"
    ret = grn["returns"][0]
    ret = await ctx.call(
        "PATCH",
        f"/vendor-returns/{ret['id']}",
        h=ctx.stores,
        row_version=ret["row_version"],
        status="replaced",
        note="Replaced on DN-2",
    )
    assert ret["status"] == "replaced"


async def test_over_receipt_is_refused_and_extra_ordered_stock_is_free(ctx: Ctx) -> None:
    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    # Ordered 25 (reel MOQ) for a requirement of 10.
    po = await ctx.po([po_line(part, "25", allocations=[(lines[part.mpn]["id"], "10")])])
    pl = po["lines"][0]
    r = await ctx.receive(po, [ctx.grn_line(pl, "26")], expect=409)
    assert (
        r["error"]["code"] == "over_receipt" and r["error"]["details"]["outstanding"] == "25.0000"
    )
    await ctx.receive(po, [ctx.grn_line(pl, "25")])
    line = await ctx.line(part.mpn)
    assert (line["status"], line["received_qty"], line["ordered_qty"]) == (
        "Received",
        "10.0000",
        "10.0000",
    )
    rows = (
        await ctx.session.execute(
            select(LedgerEntry.project_id, LedgerEntry.qty_delta).where(
                LedgerEntry.part_id == part.id
            )
        )
    ).all()
    assert sorted(rows, key=lambda r: r[1]) == [(ctx.tree["project"].id, D(10)), (None, D(15))]
    stock = next(
        s for s in await ctx.get("/inventory/stock", q=part.mpn) if s["part_id"] == str(part.id)
    )
    assert (stock["on_hand"], stock["reserved"], stock["available"]) == (
        "25.0000",
        "10.0000",
        "15.0000",
    )
    # Over-receipt at BOQ level: more received than required still reads "Received".
    r = await ctx.receive(po, [ctx.grn_line(pl, "1")], expect=409)
    assert r["error"]["code"] == "order_not_receivable"


async def test_po_line_serving_two_projects(ctx: Ctx) -> None:
    from tests.factories import ModuleFactory, ProjectFactory, create

    part = await ctx.part()
    p2 = await create(
        ctx.session, ProjectFactory, division_id=ctx.tree["division"].id, code="PRJ-TWO-1"
    )
    m2 = await create(ctx.session, ModuleFactory, project_id=p2.id)
    a = await ctx.boq([(part, "10", "Passive")], build_qty=10)
    b = await ctx.boq([(part, "5", "Passive")], build_qty=10, project_id=p2.id, module_id=m2.id)
    po = await ctx.po(
        [
            po_line(
                part,
                "150",
                allocations=[(a[part.mpn]["id"], "100"), (b[part.mpn]["id"], "50")],
                expected_date="2026-01-15",
            )
        ]
    )
    assert po["project_codes"] == sorted([ctx.tree["project"].code, "PRJ-TWO-1"])
    assert [x["qty"] for x in po["lines"][0]["allocations"]] == ["100.0000", "50.0000"]
    await ctx.receive(po, [ctx.grn_line(po["lines"][0], "120")])
    one = await ctx.line(part.mpn)
    two = await ctx.line(part.mpn, p2.id)
    assert (one["status"], one["received_qty"]) == ("Received", "100.0000")
    assert (two["status"], two["received_qty"], two["pending_receipt"]) == (
        "Partially received",
        "20.0000",
        "30.0000",
    )
    assert two["days_overdue"] > 0 and two["expected_date"] == "2026-01-15"
    assert D(two["value_pending"]) == D("45.0")  # 30 x 1.50
    projects = dict(
        (
            await ctx.session.execute(
                select(LedgerEntry.project_id, LedgerEntry.qty_delta).where(
                    LedgerEntry.part_id == part.id
                )
            )
        ).all()
    )
    assert projects == {ctx.tree["project"].id: D(100), p2.id: D(20)}
    pending = [
        p for p in await ctx.get("/procurement/pending", h=ctx.buyer) if p["po_id"] == po["id"]
    ]
    assert [(p["outstanding"], p["project_codes"]) for p in pending] == [
        ("30.0000", sorted([ctx.tree["project"].code, "PRJ-TWO-1"]))
    ]


async def test_cancellation(ctx: Ctx) -> None:
    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    alloc = [(lines[part.mpn]["id"], "10")]

    # Whole order cancelled before any receipt: back to Not ordered.
    po = await ctx.po([po_line(part, "10", allocations=alloc)])
    assert (await ctx.line(part.mpn))["status"] == "Ordered"
    await ctx.call(
        "POST", f"/purchase-orders/{po['id']}/cancel", h=ctx.buyer, row_version=po["row_version"]
    )
    assert (await ctx.line(part.mpn))["status"] == "Not ordered"

    # Partial receipt, then the remainder cancelled: ordered drops to what arrived.
    po = await ctx.po([po_line(part, "10", allocations=alloc)])
    await ctx.receive(po, [ctx.grn_line(po["lines"][0], "4")])
    po = await ctx.get(f"/purchase-orders/{po['id']}")
    r = await ctx.client.post(
        f"/api/purchase-orders/{po['id']}/cancel",
        headers=ctx.buyer,
        json={"row_version": po["row_version"]},
    )
    assert r.json()["error"]["code"] == "order_has_receipts"
    po = await ctx.call(
        "POST",
        f"/po-lines/{po['lines'][0]['id']}/cancel",
        h=ctx.buyer,
        row_version=po["lines"][0]["row_version"],
    )
    assert po["status"] == "received" and po["lines"][0]["outstanding"] == "0"
    line = await ctx.line(part.mpn)
    assert (line["ordered_qty"], line["received_qty"], line["shortfall"], line["status"]) == (
        "4.0000",
        "4.0000",
        "6.0000",
        "Partially received",
    )
    r = await ctx.receive(po, [ctx.grn_line(po["lines"][0], "1")], expect=409)
    assert r["error"]["code"] == "order_not_receivable"


async def test_hold_then_resolve(ctx: Ctx) -> None:
    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    po = await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    grn = await ctx.receive(po, [ctx.grn_line(po["lines"][0], "0", hold="10")])
    gl = grn["lines"][0]
    assert gl["inspection_result"] == "hold"
    assert (await ctx.line(part.mpn))["received_qty"] == "0"  # hold is not received
    r = await ctx.receive(po, [ctx.grn_line(po["lines"][0], "1")], expect=409)  # hold counts
    assert r["error"]["code"] == "over_receipt"
    grn = await ctx.call(
        "POST",
        f"/grn-lines/{gl['id']}/resolve-hold",
        h=ctx.stores,
        row_version=gl["row_version"],
        accept_qty="7",
        reject_qty="3",
        reason="Bent leads",
    )
    gl = grn["lines"][0]
    assert (gl["qty_accepted"], gl["qty_rejected"], gl["qty_on_hold"], gl["inspection_result"]) == (
        "7.0000",
        "3.0000",
        "0.0000",
        "partial",
    )
    assert [r["qty"] for r in grn["returns"]] == ["3.0000"]
    line = await ctx.line(part.mpn)
    assert (line["received_qty"], line["pending_receipt"]) == ("7.0000", "3.0000")
    assert await inventory.stock_on_hand(ctx.session, part.id) == 7


async def test_orders_against_revision_a_count_on_revision_b(ctx: Ctx) -> None:
    part = await ctx.part()
    lines = await ctx.boq([(part, "1", "Passive")], build_qty=10)
    await ctx.po([po_line(part, "10", allocations=[(lines[part.mpn]["id"], "10")])])
    boq_id = (await ctx.tracker())["lines"][0]["boq_id"]
    rev_b = await ctx.call("POST", f"/boqs/{boq_id}/revisions", expect=201)
    await ctx.call(
        "POST", f"/boq-revisions/{rev_b['id']}/release", row_version=rev_b["row_version"]
    )
    line = await ctx.line(part.mpn)
    assert (line["revision"], line["status"], line["ordered_qty"]) == ("B", "Ordered", "10.0000")
