"""Inventory API: stock views, transfers, adjustments needing approval, reservations,
low-stock alerts and the ledger listing."""

from decimal import Decimal
from typing import Any

from app.modules.inventory import service as inventory
from app.modules.inventory.models import LedgerReason
from tests.factories import login, make_user, uniq
from tests.procurement.conftest import Ctx

D = Decimal


async def _stock(ctx: Ctx, part: Any, qty: int, loc: Any = None) -> None:
    await inventory.post_movement(
        ctx.session,
        part_id=part.id,
        location_id=(loc or ctx.stores_loc).id,
        qty_delta=qty,
        reason=LedgerReason.GRN,
        lot_code="LOT-A",
    )
    await ctx.session.flush()


async def test_transfer_and_ledger(ctx: Ctx) -> None:
    part = await ctx.part()
    await _stock(ctx, part, 50)
    rows = await ctx.call(
        "POST",
        "/inventory/transfers",
        h=ctx.stores,
        expect=201,
        part_id=str(part.id),
        from_location_id=str(ctx.stores_loc.id),
        to_location_id=str(ctx.msl_loc.id),
        qty="20",
        lot_code="LOT-A",
        note="Bake out",
    )
    assert [(r["location_code"], D(r["qty_delta"])) for r in rows] == [
        ("STORES", -20),
        ("MSL-DRY-1", 20),
    ]
    balances = {
        b["location_code"]: b["qty_on_hand"]
        for b in await ctx.get("/inventory/balances", q=part.mpn)
    }
    assert balances == {"STORES": "30.0000", "MSL-DRY-1": "20.0000"}
    r = await ctx.client.post(
        "/api/inventory/transfers",
        headers=ctx.stores,
        json={
            "part_id": str(part.id),
            "from_location_id": str(ctx.stores_loc.id),
            "to_location_id": str(ctx.msl_loc.id),
            "qty": "31",
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    r = await ctx.client.post(
        "/api/inventory/transfers",
        headers=ctx.pm,
        json={
            "part_id": str(part.id),
            "from_location_id": str(ctx.stores_loc.id),
            "to_location_id": str(ctx.msl_loc.id),
            "qty": "1",
        },
    )
    assert r.status_code == 403
    page = await ctx.get("/inventory/ledger", part_id=str(part.id))
    assert page["total"] == 3 and [i["reason"] for i in page["items"]] == [
        "TRANSFER",
        "TRANSFER",
        "GRN",
    ]
    assert page["items"][0]["user_name"] == "Test User"
    assert await inventory.verify_balances(ctx.session) == []


async def test_adjustment_needs_someone_elses_approval(ctx: Ctx) -> None:
    part = await ctx.part()
    await _stock(ctx, part, 10)
    adj = await ctx.call(
        "POST",
        "/inventory/adjustments",
        h=ctx.stores,
        expect=201,
        part_id=str(part.id),
        location_id=str(ctx.stores_loc.id),
        qty_delta="-3",
        reason="Cycle count: 7 found",
    )
    assert adj["status"] == "pending"
    assert await inventory.stock_on_hand(ctx.session, part.id) == 10  # a request moves nothing
    r = await ctx.client.post(
        f"/api/inventory/adjustments/{adj['id']}/decision",
        headers=ctx.stores,
        json={"row_version": adj["row_version"], "approve": True},
    )
    assert r.status_code == 403  # stores cannot approve at all
    # An approver who is also the requester (admin) is refused.
    admin = uniq("adm").replace("-", "_")
    await make_user(ctx.session, admin, roles=("admin",))
    admin_h = await login(ctx.client, admin)
    own = await ctx.call(
        "POST",
        "/inventory/adjustments",
        h=admin_h,
        expect=201,
        part_id=str(part.id),
        location_id=str(ctx.stores_loc.id),
        qty_delta="1",
        reason="Found one",
    )
    r = await ctx.client.post(
        f"/api/inventory/adjustments/{own['id']}/decision",
        headers=admin_h,
        json={"row_version": own["row_version"], "approve": True},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    done = await ctx.call(
        "POST",
        f"/inventory/adjustments/{adj['id']}/decision",
        h=ctx.qc_lead,
        row_version=adj["row_version"],
        approve=True,
        note="Checked",
    )
    assert (done["status"], done["decided_by_name"]) == ("approved", "Test User")
    assert await inventory.stock_on_hand(ctx.session, part.id) == 7
    r = await ctx.client.post(
        f"/api/inventory/adjustments/{adj['id']}/decision",
        headers=ctx.qc_lead,
        json={"row_version": done["row_version"], "approve": False},
    )
    assert r.json()["error"]["code"] == "already_decided"
    rej = await ctx.call(
        "POST",
        f"/inventory/adjustments/{own['id']}/decision",
        h=ctx.qc_lead,
        row_version=own["row_version"],
        approve=False,
        note="Recount first",
    )
    assert rej["status"] == "rejected" and await inventory.stock_on_hand(ctx.session, part.id) == 7
    pending = await ctx.get("/inventory/adjustments", status="pending")
    assert adj["id"] not in {a["id"] for a in pending}


async def test_reservations_and_low_stock(ctx: Ctx) -> None:
    part = await ctx.part()
    await _stock(ctx, part, 30)
    quarantine = next(loc for loc in await ctx.get("/inventory/locations") if loc["code"] == "QUAR")
    from app.modules.inventory.models import InventoryLocation

    quar = await ctx.session.get(InventoryLocation, __import__("uuid").UUID(quarantine["id"]))
    await _stock(ctx, part, 100, quar)  # quarantined stock is never available
    project = str(ctx.tree["project"].id)
    r = await ctx.client.post(
        "/api/inventory/reservations",
        headers=ctx.stores,
        json={"part_id": str(part.id), "project_id": project, "qty": "31"},
    )
    assert r.status_code == 409 and r.json()["error"]["details"]["available"] == "30.0000"
    res = await ctx.call(
        "POST",
        "/inventory/reservations",
        h=ctx.stores,
        expect=201,
        part_id=str(part.id),
        project_id=project,
        qty="25",
        note="For lot 1",
    )
    assert res["project_code"] == ctx.tree["project"].code
    row = next(
        s for s in await ctx.get("/inventory/stock", q=part.mpn) if s["part_id"] == str(part.id)
    )
    assert (row["on_hand"], row["usable"], row["reserved"], row["available"], row["low"]) == (
        "130.0000",
        "30.0000",
        "25.0000",
        "5.0000",
        False,
    )
    # Minimum stock 10: available 5 is low.
    from app.modules.parts.models import Part

    p = await ctx.session.get(Part, part.id)
    assert p is not None
    patched = await ctx.call(
        "PATCH", f"/parts/{part.id}", h=ctx.buyer, row_version=p.row_version, min_stock=10
    )
    assert patched["min_stock"] == 10
    low = await ctx.get("/inventory/stock", low_only="true")
    assert str(part.id) in {s["part_id"] for s in low}
    released = await ctx.call(
        "POST",
        f"/inventory/reservations/{res['id']}/release",
        h=ctx.stores,
        row_version=res["row_version"],
    )
    assert released["status"] == "released"
    assert str(part.id) not in {
        s["part_id"] for s in await ctx.get("/inventory/stock", low_only="true")
    }
    assert res["id"] not in {
        r["id"] for r in await ctx.get("/inventory/reservations", project_id=project)
    }
