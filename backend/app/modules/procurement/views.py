"""Response builders: turn service records into API schemas with the names, codes and
derived quantities the screens need. Read-only; no business rules here."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import Principal
from app.modules.boq import service as boq
from app.modules.inventory import service as inventory
from app.modules.org import service as org
from app.modules.parts import service as parts
from app.modules.procurement import quantities
from app.modules.procurement import service as procurement
from app.modules.procurement.models import (
    GoodsReceipt,
    GrnLine,
    PoStatus,
    PurchaseOrder,
    PurchaseRequisition,
    Vendor,
    VendorReturn,
)
from app.modules.procurement.schemas import (
    AllocationOut,
    Contact,
    GrnDetail,
    GrnLineOut,
    GrnOut,
    GrnRef,
    PoDetail,
    PoLineOut,
    PoOut,
    PoRef,
    PrDetail,
    PrLineOut,
    PrOut,
    ReturnOut,
    VendorOut,
)
from app.modules.users import service as users

ZERO = Decimal(0)


def vendor_out(v: Vendor, open_pos: int = 0) -> VendorOut:
    return VendorOut(
        id=v.id,
        code=v.code,
        name=v.name,
        gstin=v.gstin,
        address=v.address,
        city=v.city,
        state=v.state,
        contacts=[Contact(**c) for c in (v.contacts or [])],
        payment_terms=v.payment_terms,
        lead_time_days=v.lead_time_days,
        rating=v.rating,
        notes=v.notes,
        is_sample=v.is_sample,
        open_po_count=open_pos,
        row_version=v.row_version,
    )


# ---------------------------------------------------------------- requisitions


async def pr_outs(session: AsyncSession, prs: list[PurchaseRequisition]) -> list[PrOut]:
    ids = [p.id for p in prs]
    counts = await procurement.pr_line_counts(session, ids)
    orders = await procurement.orders_for_requisitions(session, ids)
    labels = await org.project_labels(session, {p.project_id for p in prs})
    names = await users.display_names(
        session, [p.created_by for p in prs] + [p.approved_by for p in prs]
    )
    return [
        PrOut(
            id=p.id,
            number=p.number,
            project_id=p.project_id,
            project_code=labels.get(p.project_id, ("", ""))[0],
            project_name=labels.get(p.project_id, ("", ""))[1],
            status=p.status,
            submitted_at=p.submitted_at,
            approved_by_name=names.get(p.approved_by) if p.approved_by else None,
            approved_at=p.approved_at,
            decision_note=p.decision_note,
            notes=p.notes,
            created_at=p.created_at,
            created_by_name=names.get(p.created_by) if p.created_by else None,
            line_count=counts.get(p.id, 0),
            purchase_orders=[
                PoRef(id=o.id, number=o.number, status=o.status) for o in orders.get(p.id, [])
            ],
            row_version=p.row_version,
        )
        for p in prs
    ]


async def pr_detail(session: AsyncSession, user: Principal, pr: PurchaseRequisition) -> PrDetail:
    (base,) = await pr_outs(session, [pr])
    lines = await procurement.pr_lines(session, pr.id)
    part_map = await parts.get_many(session, [ln.part_id for ln in lines])
    refs = await boq.line_refs(session, user, [ln.boq_line_id for ln in lines if ln.boq_line_id])
    vendor_ids = {ln.suggested_vendor_id for ln in lines if ln.suggested_vendor_id}
    vendors = {
        v.id: v.name for v in await procurement.list_vendors(session, user) if v.id in vendor_ids
    }
    return PrDetail(
        **base.model_dump(),
        lines=[
            PrLineOut(
                id=ln.id,
                boq_line_id=ln.boq_line_id,
                boq_ref=_boq_ref(refs[ln.boq_line_id]) if ln.boq_line_id in refs else None,
                part_id=ln.part_id,
                mpn=part_map[ln.part_id].mpn,
                manufacturer=part_map[ln.part_id].manufacturer,
                description=part_map[ln.part_id].description,
                unit=part_map[ln.part_id].unit,
                qty=ln.qty,
                suggested_vendor_id=ln.suggested_vendor_id,
                suggested_vendor_name=vendors.get(ln.suggested_vendor_id)
                if ln.suggested_vendor_id
                else None,
                notes=ln.notes,
            )
            for ln in lines
        ],
    )


def _boq_ref(ref: boq.LineRef) -> str:
    return f"{ref.boq_name} rev {ref.revision} line {ref.line_no}" + (
        f" ({ref.ref_des})" if ref.ref_des else ""
    )


# ---------------------------------------------------------------- purchase orders


async def po_outs(session: AsyncSession, orders: list[PurchaseOrder]) -> list[PoOut]:
    if not orders:
        return []
    vendors = {
        v.id: v
        for v in [await session.get(Vendor, vid) for vid in {o.vendor_id for o in orders}]
        if v is not None
    }
    reqs = {
        r.id: r.number
        for r in [
            await session.get(PurchaseRequisition, rid)
            for rid in {o.requisition_id for o in orders if o.requisition_id}
        ]
        if r is not None
    }
    projects = await procurement.po_projects(session, [o.id for o in orders])
    labels = await org.project_labels(session, {p for s in projects.values() for p in s})
    out = []
    for o in orders:
        lines = await procurement.po_lines(session, o.id)
        rec = await procurement.receipts_by_po_line(session, [pl.id for pl in lines])
        total = sum(
            (
                pl.qty_ordered * pl.unit_price
                for pl in lines
                if pl.unit_price is not None and not pl.is_cancelled
            ),
            ZERO,
        )
        pending_dates = [
            pl.expected_date
            for pl in lines
            if pl.expected_date and procurement.outstanding(pl, rec[pl.id]) > 0
        ]
        next_expected: date | None = (
            min(pending_dates)
            if pending_dates
            and o.status in (PoStatus.ISSUED.value, PoStatus.PARTIALLY_RECEIVED.value)
            else None
        )
        vendor = vendors[o.vendor_id]
        out.append(
            PoOut(
                id=o.id,
                number=o.number,
                vendor_id=o.vendor_id,
                vendor_code=vendor.code,
                vendor_name=vendor.name,
                requisition_id=o.requisition_id,
                requisition_number=reqs.get(o.requisition_id) if o.requisition_id else None,
                status=o.status,
                order_date=o.order_date,
                issued_at=o.issued_at,
                currency=o.currency,
                notes=o.notes,
                total=total,
                line_count=len(lines),
                next_expected=next_expected,
                project_codes=sorted(labels[p][0] for p in projects[o.id] if p in labels),
                created_at=o.created_at,
                row_version=o.row_version,
            )
        )
    return out


async def po_detail(session: AsyncSession, user: Principal, po: PurchaseOrder) -> PoDetail:
    (base,) = await po_outs(session, [po])
    lines = await procurement.po_lines(session, po.id)
    rec = await procurement.receipts_by_po_line(session, [pl.id for pl in lines])
    allocs = await procurement.line_allocations(session, [pl.id for pl in lines])
    all_allocs = [a for lst in allocs.values() for a in lst]
    got = await quantities.received_by_allocation(session, [a.id for a in all_allocs])
    refs = await boq.line_refs(session, user, [a.boq_line_id for a in all_allocs])
    labels = await org.project_labels(session, {a.project_id for a in all_allocs})
    part_map = await parts.get_many(session, [pl.part_id for pl in lines])
    receipts = await procurement.list_grns(session, user, po_id=po.id)
    return PoDetail(
        **base.model_dump(),
        lines=[
            PoLineOut(
                id=pl.id,
                line_no=pl.line_no,
                part_id=pl.part_id,
                mpn=part_map[pl.part_id].mpn,
                manufacturer=part_map[pl.part_id].manufacturer,
                description=part_map[pl.part_id].description,
                unit=part_map[pl.part_id].unit,
                msl_level=part_map[pl.part_id].msl_level,
                qty_ordered=pl.qty_ordered,
                unit_price=pl.unit_price,
                amount=pl.qty_ordered * pl.unit_price if pl.unit_price is not None else None,
                expected_date=pl.expected_date,
                is_cancelled=pl.is_cancelled,
                notes=pl.notes,
                qty_accepted=rec[pl.id].accepted,
                qty_rejected=rec[pl.id].rejected,
                qty_on_hold=rec[pl.id].on_hold,
                outstanding=procurement.outstanding(pl, rec[pl.id]),
                allocations=[
                    AllocationOut(
                        id=a.id,
                        boq_line_id=a.boq_line_id,
                        boq_ref=_boq_ref(refs[a.boq_line_id]),
                        project_id=a.project_id,
                        project_code=labels.get(a.project_id, ("", ""))[0],
                        qty=a.qty,
                        received=got.get(a.id, ZERO),
                    )
                    for a in allocs[pl.id]
                ],
                row_version=pl.row_version,
            )
            for pl in lines
        ],
        receipts=[GrnRef(id=g.id, number=g.number, received_at=g.received_at) for g in receipts],
    )


# ---------------------------------------------------------------- goods receipts


async def grn_outs(session: AsyncSession, grns: list[GoodsReceipt]) -> list[GrnOut]:
    if not grns:
        return []
    orders = {
        g.purchase_order_id: await session.get(PurchaseOrder, g.purchase_order_id) for g in grns
    }
    vendors = {
        o.vendor_id: await session.get(Vendor, o.vendor_id)
        for o in orders.values()
        if o is not None
    }
    lines = await procurement.grn_lines(session, [g.id for g in grns])
    names = await users.display_names(session, [g.received_by for g in grns])
    out = []
    for g in grns:
        mine = [ln for ln in lines if ln.goods_receipt_id == g.id]
        po = orders[g.purchase_order_id]
        assert po is not None
        vendor = vendors[po.vendor_id]
        out.append(
            GrnOut(
                id=g.id,
                number=g.number,
                purchase_order_id=g.purchase_order_id,
                po_number=po.number,
                vendor_name=vendor.name if vendor else "",
                status=g.status,
                received_at=g.received_at,
                received_by_name=names.get(g.received_by) if g.received_by else None,
                delivery_note_ref=g.delivery_note_ref,
                coc_file_id=g.coc_file_id,
                notes=g.notes,
                qty_accepted=sum((ln.qty_accepted for ln in mine), ZERO),
                qty_rejected=sum((ln.qty_rejected for ln in mine), ZERO),
                qty_on_hold=sum((ln.qty_on_hold for ln in mine), ZERO),
                row_version=g.row_version,
            )
        )
    return out


async def grn_detail(session: AsyncSession, user: Principal, grn: GoodsReceipt) -> GrnDetail:
    (base,) = await grn_outs(session, [grn])
    lines = await procurement.grn_lines(session, [grn.id])
    po_lines = {pl.id: pl for pl in await procurement.po_lines(session, grn.purchase_order_id)}
    part_map = await parts.get_many(session, [pl.part_id for pl in po_lines.values()])
    locations = (
        {loc.id: loc.code for loc in await inventory.list_locations(session, user)}
        if user.can("inventory:read")
        else {}
    )
    allocs = await procurement.grn_allocations(session, [ln.id for ln in lines])
    flat = [a for lst in allocs.values() for a in lst]
    refs = await boq.line_refs(session, user, [a.boq_line_id for a in flat])
    labels = await org.project_labels(session, {a.project_id for a in flat})
    returns = await procurement.list_returns(session, user, grn_ids=[grn.id])
    return GrnDetail(
        **base.model_dump(),
        lines=[
            GrnLineOut(
                id=ln.id,
                po_line_id=ln.po_line_id,
                po_line_no=po_lines[ln.po_line_id].line_no,
                part_id=po_lines[ln.po_line_id].part_id,
                mpn=part_map[po_lines[ln.po_line_id].part_id].mpn,
                description=part_map[po_lines[ln.po_line_id].part_id].description,
                location_id=ln.location_id,
                location_code=locations.get(ln.location_id) if ln.location_id else None,
                qty_received=ln.qty_received,
                qty_accepted=ln.qty_accepted,
                qty_rejected=ln.qty_rejected,
                qty_on_hold=ln.qty_on_hold,
                batch_lot=ln.batch_lot,
                date_code=ln.date_code,
                msl_level=ln.msl_level,
                inspection_result=ln.inspection_result,
                notes=ln.notes,
                allocated=[
                    AllocationOut(
                        id=a.allocation_id,
                        boq_line_id=a.boq_line_id,
                        boq_ref=_boq_ref(refs[a.boq_line_id]),
                        project_id=a.project_id,
                        project_code=labels.get(a.project_id, ("", ""))[0],
                        qty=a.qty,
                        received=a.qty,
                    )
                    for a in allocs[ln.id]
                ],
                row_version=ln.row_version,
            )
            for ln in lines
        ],
        returns=await return_outs(session, returns),
    )


async def return_outs(
    session: AsyncSession, rows: list[tuple[VendorReturn, GrnLine, GoodsReceipt]]
) -> list[ReturnOut]:
    out = []
    cache: dict[uuid.UUID, tuple[str, str, str]] = {}
    for ret, gl, grn in rows:
        if gl.po_line_id not in cache:
            po = await session.get(PurchaseOrder, grn.purchase_order_id)
            vendor = await session.get(Vendor, ret.vendor_id)
            pl = next(
                p
                for p in await procurement.po_lines(session, grn.purchase_order_id)
                if p.id == gl.po_line_id
            )
            part = (await parts.get_many(session, [pl.part_id]))[pl.part_id]
            cache[gl.po_line_id] = (
                po.number if po else "",
                vendor.name if vendor else "",
                part.mpn,
            )
        po_number, vendor_name, mpn = cache[gl.po_line_id]
        out.append(
            ReturnOut(
                id=ret.id,
                number=ret.number,
                grn_id=grn.id,
                grn_number=grn.number,
                po_number=po_number,
                vendor_id=ret.vendor_id,
                vendor_name=vendor_name,
                mpn=mpn,
                qty=ret.qty,
                reason=ret.reason,
                status=ret.status,
                created_at=ret.created_at,
                row_version=ret.row_version,
            )
        )
    return out
