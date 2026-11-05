"""The tracker (per project, every BOQ line) and the cross-project pending view (every open
PO line). Quantities and status come from the status service through the BOQ module;
nothing here recomputes them."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import Principal
from app.modules.boq import service as boq
from app.modules.boq.status import LineStatus
from app.modules.org import service as org
from app.modules.parts import service as parts
from app.modules.procurement import quantities
from app.modules.procurement import service as procurement
from app.modules.procurement.models import PoLine, PoStatus, PurchaseOrder, Vendor

ZERO = Decimal(0)
_OPEN = (PoStatus.ISSUED.value, PoStatus.PARTIALLY_RECEIVED.value)


def _days_overdue(expected: date | None, today: date) -> int:
    return max((today - expected).days, 0) if expected else 0


@dataclass
class _Line:
    data: dict[str, Any]
    module_id: uuid.UUID | None
    status: str
    required: Decimal


async def project_tracker(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, *, today: date | None = None
) -> dict[str, Any]:
    user.require("procurement:read")
    today = today or date.today()
    project = await org.get_project(session, user, project_id)
    module_list = await org.list_modules(session, user, project_id)
    tracked = await boq.project_lines(session, user, project_id)

    all_ids = [i for tb in tracked for tl in tb.lines for i in tl.group]
    allocs = await quantities.allocations_for(session, all_ids)
    by_line: dict[uuid.UUID, list[quantities.AllocationInfo]] = defaultdict(list)
    for a in allocs:
        by_line[a.boq_line_id].append(a)
    in_purchasing = await procurement.being_ordered(session, all_ids)

    lines: list[_Line] = []
    unreleased: list[str] = []
    for tb in tracked:
        if tb.revision is None:
            continue
        if tb.revision.status != "released":
            unreleased.append(f"{tb.view.boq.name} (rev {tb.revision.revision})")
        for tl in tb.lines:
            ln, q = tl.line, tl.qty
            infos = [a for i in tl.group for a in by_line.get(i, [])]
            live = [a for a in infos if a.po_status != PoStatus.CANCELLED.value]
            pending = [a for a in live if a.po_status in _OPEN and a.outstanding > 0]
            expected = min((a.expected_date for a in pending if a.expected_date), default=None)
            pos: dict[uuid.UUID, dict[str, Any]] = {}
            for a in live:
                entry = pos.setdefault(
                    a.po_id,
                    {
                        "po_id": a.po_id,
                        "po_number": a.po_number,
                        "vendor_name": a.vendor_name,
                        "expected_date": a.expected_date,
                        "outstanding": ZERO,
                    },
                )
                entry["outstanding"] += a.outstanding if a.po_status in _OPEN else ZERO
            value = sum(
                (a.outstanding * a.unit_price for a in pending if a.unit_price is not None), ZERO
            )
            overdue = _days_overdue(expected, today) if q.pending_receipt > 0 else 0
            lines.append(
                _Line(
                    data={
                        "boq_line_id": ln.id,
                        "boq_id": tb.view.boq.id,
                        "boq_name": tb.view.boq.name,
                        "revision": tb.revision.revision,
                        "module_id": tb.view.boq.module_id,
                        "module_code": tb.view.module.code if tb.view.module else None,
                        "line_no": ln.line_no,
                        "ref_des": ln.ref_des,
                        "part_id": ln.part_id,
                        "mpn": ln.mpn,
                        "manufacturer": ln.manufacturer,
                        "description": ln.description,
                        "category": ln.category,
                        "unit": ln.unit,
                        "dnp": ln.dnp,
                        "required_qty": q.required,
                        "ordered_qty": q.ordered,
                        "received_qty": q.received,
                        "issued_qty": q.issued,
                        "shortfall": q.shortfall,
                        "pending_receipt": q.pending_receipt,
                        "being_ordered": sum((in_purchasing.get(i, ZERO) for i in tl.group), ZERO),
                        "status": q.status.value,
                        "vendors": sorted({a.vendor_name for a in live}),
                        "purchase_orders": sorted(pos.values(), key=lambda p: p["po_number"]),
                        "expected_date": expected,
                        "days_overdue": overdue,
                        "value_pending": value,
                    },
                    module_id=tb.view.boq.module_id,
                    status=q.status.value,
                    required=q.required,
                )
            )

    required = [ln for ln in lines if ln.required > 0]
    done = {LineStatus.RECEIVED.value, LineStatus.ISSUED.value}
    received_n = sum(1 for ln in required if ln.status in done)
    kpis = {
        "lines": len(lines),
        "lines_required": len(required),
        "pct_fully_received": round(100 * received_n / len(required), 1) if required else 0.0,
        "lines_to_order": sum(1 for ln in lines if ln.data["shortfall"] > 0),
        "lines_awaiting_delivery": sum(1 for ln in lines if ln.data["pending_receipt"] > 0),
        "overdue_lines": sum(1 for ln in lines if ln.data["days_overdue"] > 0),
        "value_pending": sum((ln.data["value_pending"] for ln in lines), ZERO),
    }

    modules = []
    boq_modules = {tb.view.boq.module_id for tb in tracked}
    targets: list[tuple[uuid.UUID | None, str | None, str]] = [
        (m.id, m.code, m.name) for m in module_list
    ]
    if None in boq_modules:
        targets.append((None, None, "Project-wide items"))
    for module_id, code, name in targets:
        own = [tb for tb in tracked if tb.view.boq.module_id == module_id]
        mine = [ln for ln in required if ln.module_id == module_id]
        got = sum(1 for ln in mine if ln.status in done)
        reason: str | None = None
        if not own or all(tb.revision is None for tb in own):
            reason = "No BOQ"
        elif any(tb.revision is not None and tb.revision.status != "released" for tb in own):
            reason = "BOQ revision not released"
        elif not mine:
            reason = "No lines to build from"
        elif got < len(mine):
            reason = f"{len(mine) - got} of {len(mine)} lines not fully received"
        modules.append(
            {
                "module_id": module_id,
                "module_code": code,
                "module_name": name,
                "lines": len(mine),
                "lines_received": got,
                "clear_to_build": reason is None,
                "reason": reason,
            }
        )

    return {
        "project_id": project.id,
        "project_code": project.code,
        "project_name": project.name,
        "kpis": kpis,
        "modules": modules,
        "lines": [ln.data for ln in lines],
        "unreleased_boqs": unreleased,
    }


async def pending_lines(
    session: AsyncSession, user: Principal, *, today: date | None = None
) -> list[dict[str, Any]]:
    """Every PO line still owed by a vendor, across projects, soonest expected first."""
    user.require("procurement:read")
    today = today or date.today()
    rows = (
        await session.execute(
            select(PoLine, PurchaseOrder, Vendor)
            .join(PurchaseOrder, PurchaseOrder.id == PoLine.purchase_order_id)
            .join(Vendor, Vendor.id == PurchaseOrder.vendor_id)
            .where(
                PurchaseOrder.status.in_(_OPEN),
                PurchaseOrder.is_deleted.is_(False),
                PoLine.is_deleted.is_(False),
                PoLine.is_cancelled.is_(False),
            )
        )
    ).all()
    line_ids = [pl.id for pl, _, _ in rows]
    rec = await procurement.receipts_by_po_line(session, line_ids)
    allocs = await procurement.line_allocations(session, line_ids)
    scope = await org.scoped_project_ids(session, user)
    labels = await org.project_labels(
        session, {a.project_id for lst in allocs.values() for a in lst}
    )
    part_map = await parts.get_many(session, [pl.part_id for pl, _, _ in rows])
    out = []
    for pl, po, vendor in rows:
        left = procurement.outstanding(pl, rec[pl.id])
        if left <= 0:
            continue
        projects = {a.project_id for a in allocs[pl.id]}
        if scope is not None and not projects & scope:
            continue
        part = part_map[pl.part_id]
        out.append(
            {
                "po_id": po.id,
                "po_number": po.number,
                "po_status": po.status,
                "po_line_id": pl.id,
                "line_no": pl.line_no,
                "vendor_id": vendor.id,
                "vendor_name": vendor.name,
                "part_id": part.id,
                "mpn": part.mpn,
                "description": part.description,
                "qty_ordered": pl.qty_ordered,
                "qty_received": rec[pl.id].good,
                "outstanding": left,
                "unit_price": pl.unit_price,
                "value_pending": left * pl.unit_price if pl.unit_price is not None else None,
                "expected_date": pl.expected_date,
                "days_overdue": _days_overdue(pl.expected_date, today),
                "project_codes": sorted(labels[p][0] for p in projects if p in labels),
                "row_version": pl.row_version,
            }
        )
    out.sort(
        key=lambda r: (r["expected_date"] is None, r["expected_date"] or today, r["po_number"])
    )
    return out
