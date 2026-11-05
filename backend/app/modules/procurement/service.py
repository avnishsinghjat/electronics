"""Procurement: vendors, purchase requisitions, purchase orders, goods receipts and vendor
returns.

Rules that matter (tested in tests/procurement):
- A PO line serves one or more BOQ lines through explicit allocations (each with its
  project); allocations never exceed the ordered quantity and must be for the same part.
- Receiving locks the purchase order row, so two people receiving the same PO line at once
  are serialised and cannot together receive more than is outstanding.
- Only ACCEPTED quantity posts to the inventory ledger. It is distributed over the PO
  line's allocations (oldest first), recorded per allocation, and reserved for that
  allocation's project; anything beyond the allocations is free stock.
- Rejected quantity creates a vendor return and stays outstanding on the PO line (the
  vendor owes a replacement). Quantity on hold counts against the PO line until it is
  resolved into accepted or rejected.
- PO status follows receipts: issued -> partially received -> received.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.models import utcnow
from app.core.numbering import next_number
from app.core.repository import check_version
from app.modules.attachments import service as attachments
from app.modules.auth.service import Principal
from app.modules.boq import service as boq
from app.modules.inventory import service as inventory
from app.modules.inventory.models import LedgerReason
from app.modules.org import service as org
from app.modules.parts import service as parts
from app.modules.parts.models import Part
from app.modules.procurement import quantities
from app.modules.procurement.models import (
    GoodsReceipt,
    GrnAllocation,
    GrnLine,
    GrnStatus,
    InspectionResult,
    PoLine,
    PoLineAllocation,
    PoStatus,
    PrLine,
    PrStatus,
    PurchaseOrder,
    PurchaseRequisition,
    ReturnStatus,
    Vendor,
    VendorReturn,
)
from app.modules.procurement.schemas import (
    GrnCreate,
    GrnPatch,
    HoldResolution,
    PoCreate,
    PoLineIn,
    PoLinePatch,
    PoUpdate,
    PrFromShortfall,
    PrUpdate,
    ReturnUpdate,
    VendorCreate,
    VendorUpdate,
)

ZERO = Decimal(0)
GRN_LINE_REF = "grn_line"
_OPEN_PR = (PrStatus.DRAFT.value, PrStatus.SUBMITTED.value, PrStatus.APPROVED.value)
_RECEIVABLE = (PoStatus.ISSUED.value, PoStatus.PARTIALLY_RECEIVED.value)


# ---------------------------------------------------------------- scoping helpers


async def _visible_projects(session: AsyncSession, user: Principal) -> set[uuid.UUID] | None:
    return await org.scoped_project_ids(session, user)


async def po_projects(
    session: AsyncSession, po_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Purchase order id -> projects its lines are allocated to."""
    wanted = set(po_ids)
    out: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if not wanted:
        return out
    rows = await session.execute(
        select(PoLine.purchase_order_id, PoLineAllocation.project_id)
        .join(PoLineAllocation, PoLineAllocation.po_line_id == PoLine.id)
        .where(
            PoLine.purchase_order_id.in_(wanted),
            PoLine.is_deleted.is_(False),
            PoLineAllocation.is_deleted.is_(False),
        )
        .distinct()
    )
    for po_id, project_id in rows.all():
        out[po_id].add(project_id)
    return out


def _po_in_scope(scope: set[uuid.UUID] | None, projects: set[uuid.UUID]) -> bool:
    """Unrestricted users see every order; scoped users see orders serving their projects."""
    return scope is None or bool(projects & scope)


# ---------------------------------------------------------------- vendors


async def _vendor(session: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    vendor = await session.get(Vendor, vendor_id)
    if vendor is None or vendor.is_deleted:
        raise NotFoundError("Vendor not found", details={"id": str(vendor_id)})
    return vendor


async def open_po_counts(session: AsyncSession) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(PurchaseOrder.vendor_id, func.count())
        .where(
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.status.in_(
                [PoStatus.DRAFT.value, PoStatus.ISSUED.value, PoStatus.PARTIALLY_RECEIVED.value]
            ),
        )
        .group_by(PurchaseOrder.vendor_id)
    )
    return {vid: int(n) for vid, n in rows.all()}


async def list_vendors(
    session: AsyncSession, user: Principal, q: str | None = None
) -> list[Vendor]:
    user.require("procurement:read")
    stmt = select(Vendor).where(Vendor.is_deleted.is_(False)).order_by(Vendor.name)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Vendor.name.ilike(like), Vendor.code.ilike(like), Vendor.gstin.ilike(like))
        )
    return list((await session.execute(stmt)).scalars().all())


async def get_vendor(session: AsyncSession, user: Principal, vendor_id: uuid.UUID) -> Vendor:
    user.require("procurement:read")
    return await _vendor(session, vendor_id)


async def _code_taken(session: AsyncSession, code: str, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(Vendor.id).where(Vendor.code == code, Vendor.is_deleted.is_(False))
    if exclude:
        stmt = stmt.where(Vendor.id != exclude)
    return (await session.execute(stmt)).first() is not None


async def create_vendor(session: AsyncSession, user: Principal, data: VendorCreate) -> Vendor:
    user.require("vendors:manage")
    if await _code_taken(session, data.code):
        raise ConflictError(f"Vendor code {data.code} is already used", code="duplicate_code")
    values = data.model_dump()
    values["contacts"] = [c.model_dump() for c in data.contacts]
    vendor = Vendor(**values)
    session.add(vendor)
    await session.flush()
    await session.commit()
    return vendor


async def update_vendor(
    session: AsyncSession, user: Principal, vendor_id: uuid.UUID, data: VendorUpdate
) -> Vendor:
    user.require("vendors:manage")
    vendor = await _vendor(session, vendor_id)
    check_version(vendor, data.row_version)
    if await _code_taken(session, data.code, exclude=vendor.id):
        raise ConflictError(f"Vendor code {data.code} is already used", code="duplicate_code")
    values = data.model_dump(exclude={"row_version"})
    values["contacts"] = [c.model_dump() for c in data.contacts]
    for key, value in values.items():
        setattr(vendor, key, value)
    await session.flush()
    await session.commit()
    return vendor


async def delete_vendor(
    session: AsyncSession, user: Principal, vendor_id: uuid.UUID, row_version: int
) -> None:
    user.require("vendors:manage")
    vendor = await _vendor(session, vendor_id)
    check_version(vendor, row_version)
    used = (
        await session.execute(
            select(PurchaseOrder.number).where(
                PurchaseOrder.vendor_id == vendor.id, PurchaseOrder.is_deleted.is_(False)
            )
        )
    ).first()
    if used:
        raise ConflictError(
            f"{vendor.name} has purchase orders (e.g. {used[0]}) and cannot be deleted",
            code="vendor_in_use",
        )
    vendor.is_deleted = True
    await session.flush()
    await session.commit()


# ---------------------------------------------------------------- requisitions


async def _pr(session: AsyncSession, user: Principal, pr_id: uuid.UUID) -> PurchaseRequisition:
    user.require("procurement:read")
    pr = await session.get(PurchaseRequisition, pr_id)
    if pr is None or pr.is_deleted:
        raise NotFoundError("Requisition not found", details={"id": str(pr_id)})
    try:
        await org.get_project(session, user, pr.project_id)
    except NotFoundError as exc:
        raise NotFoundError("Requisition not found", details={"id": str(pr_id)}) from exc
    return pr


async def pr_lines(session: AsyncSession, pr_id: uuid.UUID) -> list[PrLine]:
    rows = await session.execute(
        select(PrLine)
        .where(PrLine.requisition_id == pr_id, PrLine.is_deleted.is_(False))
        .order_by(PrLine.created_at, PrLine.id)
    )
    return list(rows.scalars().all())


async def on_requisition(
    session: AsyncSession, boq_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """BOQ line id -> quantity on open (not yet converted or rejected) requisitions."""
    if not boq_line_ids:
        return {}
    rows = await session.execute(
        select(PrLine.boq_line_id, func.sum(PrLine.qty))
        .join(PurchaseRequisition, PurchaseRequisition.id == PrLine.requisition_id)
        .where(
            PrLine.boq_line_id.in_(boq_line_ids),
            PrLine.is_deleted.is_(False),
            PurchaseRequisition.is_deleted.is_(False),
            PurchaseRequisition.status.in_(_OPEN_PR),
        )
        .group_by(PrLine.boq_line_id)
    )
    return {lid: Decimal(q) for lid, q in rows.all() if lid is not None}


async def being_ordered(
    session: AsyncSession, boq_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """BOQ line id -> quantity on open requisitions plus draft purchase orders: already in
    purchasing, so not requisitioned again."""
    out: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for line_id, qty in (await on_requisition(session, boq_line_ids)).items():
        out[line_id] += qty
    for info in await quantities.allocations_for(session, boq_line_ids):
        out[info.boq_line_id] += info.drafted
    return dict(out)


def _group_sum(values: dict[uuid.UUID, Decimal], group: list[uuid.UUID]) -> Decimal:
    return sum((values.get(i, ZERO) for i in group), ZERO)


async def create_pr_from_shortfall(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, data: PrFromShortfall
) -> PurchaseRequisition:
    """One requisition line per selected BOQ line (or every line short), for the shortfall
    not already on an open requisition. Only released revisions can be requisitioned."""
    user.require("pr:create")
    await org.get_project(session, user, project_id)
    wanted = set(data.boq_line_ids)
    tracked = await boq.project_lines(session, user, project_id)
    found: set[uuid.UUID] = set()
    candidates: list[tuple[boq.TrackedLine, str]] = []
    for tb in tracked:
        for tl in tb.lines:
            if wanted and tl.line.id not in wanted:
                continue
            found.add(tl.line.id)
            if tb.revision is None or tb.revision.status != "released":
                if wanted:
                    raise ConflictError(
                        f"{tb.view.boq.name} revision {tb.revision.revision if tb.revision else ''}"
                        " is not released; release it before requisitioning",
                        code="revision_not_released",
                    )
                continue
            candidates.append((tl, tb.view.boq.name))
    missing = wanted - found
    if missing:
        raise NotFoundError(
            "Some BOQ lines are not in this project's current BOQ revisions",
            details={"ids": sorted(str(m) for m in missing)},
        )
    open_qty = await being_ordered(session, [i for tl, _ in candidates for i in tl.group])
    specs: list[tuple[boq.TrackedLine, Decimal]] = []
    no_part: list[str] = []
    for tl, _name in candidates:
        need = tl.qty.shortfall - _group_sum(open_qty, tl.group)
        if need <= 0:
            continue
        if tl.line.part_id is None:
            no_part.append(tl.line.mpn or f"line {tl.line.line_no}")
            continue
        specs.append((tl, need))
    if no_part:
        raise ConflictError(
            "These lines are not linked to a part in the part master: " + ", ".join(no_part),
            code="line_without_part",
        )
    if not specs:
        raise ConflictError(
            "Nothing to requisition: every selected line is ordered or already on a requisition",
            code="nothing_to_order",
        )
    vendors = await parts.preferred_vendors(
        session, [tl.line.part_id for tl, _ in specs if tl.line.part_id]
    )
    pr = PurchaseRequisition(
        number=await next_number(session, "PR"), project_id=project_id, notes=data.notes
    )
    session.add(pr)
    await session.flush()
    for tl, need in specs:
        assert tl.line.part_id is not None
        session.add(
            PrLine(
                requisition_id=pr.id,
                boq_line_id=tl.line.id,
                part_id=tl.line.part_id,
                qty=need,
                suggested_vendor_id=vendors.get(tl.line.part_id),
            )
        )
    await session.flush()
    await session.commit()
    return pr


def _require_pr_status(pr: PurchaseRequisition, *allowed: PrStatus) -> None:
    if pr.status not in {s.value for s in allowed}:
        raise ConflictError(
            f"Requisition {pr.number} is {pr.status}", code="invalid_status_transition"
        )


async def update_pr(
    session: AsyncSession, user: Principal, pr_id: uuid.UUID, data: PrUpdate
) -> PurchaseRequisition:
    user.require("pr:create")
    pr = await _pr(session, user, pr_id)
    check_version(pr, data.row_version)
    _require_pr_status(pr, PrStatus.DRAFT, PrStatus.REJECTED)
    line_ids = [ln.boq_line_id for ln in data.lines if ln.boq_line_id]
    refs = await boq.line_refs(session, user, line_ids)
    for ref in refs.values():
        if ref.project_id != pr.project_id:
            raise AppError("A BOQ line belongs to another project", code="wrong_project")
    part_map = await parts.get_many(session, [ln.part_id for ln in data.lines])
    for ln in data.lines:
        if ln.part_id not in part_map:
            raise NotFoundError("Part not found", details={"id": str(ln.part_id)})
        if ln.suggested_vendor_id:
            await _vendor(session, ln.suggested_vendor_id)
    for old in await pr_lines(session, pr.id):
        await session.delete(old)
    await session.flush()
    for ln in data.lines:
        session.add(PrLine(requisition_id=pr.id, **ln.model_dump()))
    pr.notes = data.notes
    if pr.status == PrStatus.REJECTED.value:  # edited after rejection: back to draft
        pr.status = PrStatus.DRAFT.value
        pr.decision_note = None
    pr.updated_at = utcnow()  # bump row_version even if only lines changed
    await session.flush()
    await session.commit()
    return pr


async def submit_pr(
    session: AsyncSession, user: Principal, pr_id: uuid.UUID, row_version: int
) -> PurchaseRequisition:
    user.require("pr:create")
    pr = await _pr(session, user, pr_id)
    check_version(pr, row_version)
    _require_pr_status(pr, PrStatus.DRAFT)
    if not await pr_lines(session, pr.id):
        raise ConflictError("The requisition has no lines", code="empty_requisition")
    pr.status = PrStatus.SUBMITTED.value
    pr.submitted_at = utcnow()
    await session.flush()
    await session.commit()
    return pr


async def decide_pr(
    session: AsyncSession,
    user: Principal,
    pr_id: uuid.UUID,
    row_version: int,
    *,
    approve: bool,
    note: str | None,
) -> PurchaseRequisition:
    user.require("pr:approve")
    pr = await _pr(session, user, pr_id)
    check_version(pr, row_version)
    _require_pr_status(pr, PrStatus.SUBMITTED)
    pr.status = PrStatus.APPROVED.value if approve else PrStatus.REJECTED.value
    pr.approved_by = user.id if approve else None
    pr.approved_at = utcnow() if approve else None
    pr.decision_note = note
    await session.flush()
    await session.commit()
    return pr


async def delete_pr(
    session: AsyncSession, user: Principal, pr_id: uuid.UUID, row_version: int
) -> None:
    user.require("pr:create")
    pr = await _pr(session, user, pr_id)
    check_version(pr, row_version)
    _require_pr_status(pr, PrStatus.DRAFT, PrStatus.REJECTED)
    pr.is_deleted = True
    await session.flush()
    await session.commit()


async def convert_pr(
    session: AsyncSession, user: Principal, pr_id: uuid.UUID, row_version: int
) -> list[PurchaseOrder]:
    """Approved requisition -> one draft PO per suggested vendor, each line allocated to
    its BOQ line."""
    user.require("po:manage")
    pr = await _pr(session, user, pr_id)
    check_version(pr, row_version)
    _require_pr_status(pr, PrStatus.APPROVED)
    lines = await pr_lines(session, pr.id)
    without = [ln for ln in lines if ln.suggested_vendor_id is None]
    if without:
        names = await parts.get_many(session, [ln.part_id for ln in without])
        raise ConflictError(
            "Choose a vendor for: " + ", ".join(names[ln.part_id].mpn for ln in without),
            code="vendor_missing",
        )
    by_vendor: dict[uuid.UUID, list[PrLine]] = defaultdict(list)
    for ln in lines:
        assert ln.suggested_vendor_id is not None
        by_vendor[ln.suggested_vendor_id].append(ln)
    orders = []
    for vendor_id, vendor_lines in by_vendor.items():
        vendor = await _vendor(session, vendor_id)
        expected = (
            date.fromordinal(date.today().toordinal() + vendor.lead_time_days)
            if vendor.lead_time_days
            else None
        )
        po = PurchaseOrder(
            number=await next_number(session, "PO"),
            vendor_id=vendor_id,
            requisition_id=pr.id,
            notes=pr.notes,
        )
        session.add(po)
        await session.flush()
        for no, ln in enumerate(vendor_lines, start=1):
            pl = PoLine(
                purchase_order_id=po.id,
                line_no=no,
                part_id=ln.part_id,
                qty_ordered=ln.qty,
                expected_date=expected,
                notes=ln.notes,
            )
            session.add(pl)
            await session.flush()
            if ln.boq_line_id:
                session.add(
                    PoLineAllocation(
                        po_line_id=pl.id,
                        boq_line_id=ln.boq_line_id,
                        project_id=pr.project_id,
                        qty=ln.qty,
                    )
                )
        orders.append(po)
    pr.status = PrStatus.CONVERTED.value
    await session.flush()
    await session.commit()
    return orders


async def list_prs(
    session: AsyncSession,
    user: Principal,
    *,
    project_id: uuid.UUID | None = None,
    status: list[str] | None = None,
) -> list[PurchaseRequisition]:
    user.require("procurement:read")
    stmt = (
        select(PurchaseRequisition)
        .where(PurchaseRequisition.is_deleted.is_(False))
        .order_by(PurchaseRequisition.created_at.desc())
    )
    scope = await _visible_projects(session, user)
    if scope is not None:
        stmt = stmt.where(PurchaseRequisition.project_id.in_(scope))
    if project_id:
        stmt = stmt.where(PurchaseRequisition.project_id == project_id)
    if status:
        stmt = stmt.where(PurchaseRequisition.status.in_(status))
    return list((await session.execute(stmt)).scalars().all())


async def get_pr(session: AsyncSession, user: Principal, pr_id: uuid.UUID) -> PurchaseRequisition:
    return await _pr(session, user, pr_id)


async def pr_line_counts(session: AsyncSession, pr_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not pr_ids:
        return {}
    rows = await session.execute(
        select(PrLine.requisition_id, func.count())
        .where(PrLine.requisition_id.in_(pr_ids), PrLine.is_deleted.is_(False))
        .group_by(PrLine.requisition_id)
    )
    return {rid: int(n) for rid, n in rows.all()}


async def orders_for_requisitions(
    session: AsyncSession, pr_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PurchaseOrder]]:
    out: dict[uuid.UUID, list[PurchaseOrder]] = defaultdict(list)
    if not pr_ids:
        return out
    rows = await session.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.requisition_id.in_(pr_ids), PurchaseOrder.is_deleted.is_(False))
        .order_by(PurchaseOrder.number)
    )
    for po in rows.scalars():
        assert po.requisition_id is not None
        out[po.requisition_id].append(po)
    return out


# ---------------------------------------------------------------- purchase orders


async def _po(
    session: AsyncSession, user: Principal, po_id: uuid.UUID, *, lock: bool = False
) -> PurchaseOrder:
    user.require("procurement:read")
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.id == po_id, PurchaseOrder.is_deleted.is_(False)
    )
    if lock:
        stmt = stmt.with_for_update()
    po = (await session.execute(stmt)).scalar_one_or_none()
    if po is None:
        raise NotFoundError("Purchase order not found", details={"id": str(po_id)})
    scope = await _visible_projects(session, user)
    if not _po_in_scope(scope, (await po_projects(session, [po.id]))[po.id]):
        raise NotFoundError("Purchase order not found", details={"id": str(po_id)})
    if lock:
        await session.refresh(po)
    return po


async def po_lines(session: AsyncSession, po_id: uuid.UUID) -> list[PoLine]:
    rows = await session.execute(
        select(PoLine)
        .where(PoLine.purchase_order_id == po_id, PoLine.is_deleted.is_(False))
        .order_by(PoLine.line_no)
    )
    return list(rows.scalars().all())


async def line_allocations(
    session: AsyncSession, po_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PoLineAllocation]]:
    out: dict[uuid.UUID, list[PoLineAllocation]] = defaultdict(list)
    if not po_line_ids:
        return out
    rows = await session.execute(
        select(PoLineAllocation)
        .where(PoLineAllocation.po_line_id.in_(po_line_ids), PoLineAllocation.is_deleted.is_(False))
        .order_by(PoLineAllocation.created_at, PoLineAllocation.id)
    )
    for a in rows.scalars():
        out[a.po_line_id].append(a)
    return out


@dataclass
class LineReceipts:
    accepted: Decimal = ZERO
    rejected: Decimal = ZERO
    on_hold: Decimal = ZERO

    @property
    def good(self) -> Decimal:
        """Counts against the ordered quantity: accepted, plus on hold until resolved."""
        return self.accepted + self.on_hold


async def receipts_by_po_line(
    session: AsyncSession, po_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, LineReceipts]:
    out: dict[uuid.UUID, LineReceipts] = defaultdict(LineReceipts)
    if not po_line_ids:
        return out
    rows = await session.execute(
        select(
            GrnLine.po_line_id,
            func.sum(GrnLine.qty_accepted),
            func.sum(GrnLine.qty_rejected),
            func.sum(GrnLine.qty_on_hold),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GrnLine.goods_receipt_id)
        .where(
            GrnLine.po_line_id.in_(po_line_ids),
            GrnLine.is_deleted.is_(False),
            GoodsReceipt.status == GrnStatus.POSTED.value,
        )
        .group_by(GrnLine.po_line_id)
    )
    for line_id, acc, rej, hold in rows.all():
        out[line_id] = LineReceipts(Decimal(acc), Decimal(rej), Decimal(hold))
    return out


def outstanding(line: PoLine, rec: LineReceipts) -> Decimal:
    if line.is_cancelled:
        return ZERO
    return max(line.qty_ordered - rec.good, ZERO)


async def _validated_lines(
    session: AsyncSession, user: Principal, lines: list[PoLineIn]
) -> tuple[dict[uuid.UUID, Part], dict[uuid.UUID, boq.LineRef]]:
    part_map = await parts.get_many(session, [ln.part_id for ln in lines])
    for ln in lines:
        if ln.part_id not in part_map or part_map[ln.part_id].is_deleted:
            raise NotFoundError("Part not found", details={"id": str(ln.part_id)})
    refs = await boq.line_refs(
        session, user, [a.boq_line_id for ln in lines for a in ln.allocations]
    )
    for ln in lines:
        for a in ln.allocations:
            ref = refs[a.boq_line_id]
            if ref.part_id != ln.part_id:
                raise AppError(
                    f"BOQ line {ref.line_no} of {ref.boq_name} is for "
                    f"{ref.mpn or 'another part'}, not {part_map[ln.part_id].mpn}",
                    code="allocation_part_mismatch",
                    status_code=422,
                )
    return part_map, refs


async def _write_lines(
    session: AsyncSession, po: PurchaseOrder, lines: list[PoLineIn], refs: dict[uuid.UUID, Any]
) -> None:
    for no, ln in enumerate(lines, start=1):
        pl = PoLine(
            purchase_order_id=po.id,
            line_no=no,
            part_id=ln.part_id,
            qty_ordered=ln.qty_ordered,
            unit_price=ln.unit_price,
            expected_date=ln.expected_date,
            notes=ln.notes,
        )
        session.add(pl)
        await session.flush()
        for a in ln.allocations:
            session.add(
                PoLineAllocation(
                    po_line_id=pl.id,
                    boq_line_id=a.boq_line_id,
                    project_id=refs[a.boq_line_id].project_id,
                    qty=a.qty,
                )
            )
    await session.flush()


async def create_po(session: AsyncSession, user: Principal, data: PoCreate) -> PurchaseOrder:
    user.require("po:manage")
    await _vendor(session, data.vendor_id)
    _, refs = await _validated_lines(session, user, data.lines)
    po = PurchaseOrder(
        number=await next_number(session, "PO"),
        vendor_id=data.vendor_id,
        order_date=data.order_date,
        notes=data.notes,
    )
    session.add(po)
    await session.flush()
    await _write_lines(session, po, data.lines, refs)
    await session.commit()
    return po


def _require_po_status(po: PurchaseOrder, *allowed: PoStatus) -> None:
    if po.status not in {s.value for s in allowed}:
        raise ConflictError(
            f"{po.number} is {po.status.replace('_', ' ')}", code="invalid_status_transition"
        )


async def update_po(
    session: AsyncSession, user: Principal, po_id: uuid.UUID, data: PoUpdate
) -> PurchaseOrder:
    """Full replace of a DRAFT order's vendor, header and lines."""
    user.require("po:manage")
    po = await _po(session, user, po_id)
    check_version(po, data.row_version)
    _require_po_status(po, PoStatus.DRAFT)
    await _vendor(session, data.vendor_id)
    _, refs = await _validated_lines(session, user, data.lines)
    old = await po_lines(session, po.id)
    for pl in old:
        await session.delete(pl)  # allocations cascade
    await session.flush()
    po.vendor_id = data.vendor_id
    po.order_date = data.order_date
    po.notes = data.notes
    po.updated_at = utcnow()
    await _write_lines(session, po, data.lines, refs)
    await session.commit()
    return po


async def issue_po(
    session: AsyncSession, user: Principal, po_id: uuid.UUID, row_version: int
) -> PurchaseOrder:
    user.require("po:manage")
    po = await _po(session, user, po_id)
    check_version(po, row_version)
    _require_po_status(po, PoStatus.DRAFT)
    lines = await po_lines(session, po.id)
    if not lines:
        raise ConflictError("The order has no lines", code="empty_order")
    if any(pl.unit_price is None for pl in lines):
        raise ConflictError("Every line needs a unit price before issuing", code="price_missing")
    po.status = PoStatus.ISSUED.value
    po.issued_at = utcnow()
    po.order_date = po.order_date or date.today()
    await session.flush()
    await session.commit()
    return po


async def cancel_po(
    session: AsyncSession, user: Principal, po_id: uuid.UUID, row_version: int
) -> PurchaseOrder:
    user.require("po:manage")
    po = await _po(session, user, po_id, lock=True)
    check_version(po, row_version)
    lines = await po_lines(session, po.id)
    rec = await receipts_by_po_line(session, [pl.id for pl in lines])
    if po.status == PoStatus.PARTIALLY_RECEIVED.value or any(
        rec[pl.id].accepted + rec[pl.id].on_hold + rec[pl.id].rejected > 0 for pl in lines
    ):
        raise ConflictError(
            "Goods were received on this order; cancel the remaining lines instead",
            code="order_has_receipts",
        )
    _require_po_status(po, PoStatus.DRAFT, PoStatus.ISSUED)
    po.status = PoStatus.CANCELLED.value
    await session.flush()
    await session.commit()
    return po


async def close_po(
    session: AsyncSession, user: Principal, po_id: uuid.UUID, row_version: int, note: str | None
) -> PurchaseOrder:
    """Mark a received (or short-received, by agreement) order as finished. Quantities on
    a closed order still count as ordered (CLAUDE.md); to reorder an undelivered remainder,
    cancel those lines instead."""
    user.require("po:manage")
    po = await _po(session, user, po_id)
    check_version(po, row_version)
    _require_po_status(po, PoStatus.ISSUED, PoStatus.PARTIALLY_RECEIVED, PoStatus.RECEIVED)
    po.status = PoStatus.CLOSED.value
    if note:
        po.notes = f"{po.notes}\n{note}".strip() if po.notes else note
    await session.flush()
    await session.commit()
    return po


async def _po_line(
    session: AsyncSession, user: Principal, po_line_id: uuid.UUID
) -> tuple[PurchaseOrder, PoLine]:
    pl = await session.get(PoLine, po_line_id)
    if pl is None or pl.is_deleted:
        raise NotFoundError("PO line not found", details={"id": str(po_line_id)})
    po = await _po(session, user, pl.purchase_order_id)
    return po, pl


async def patch_po_line(
    session: AsyncSession, user: Principal, po_line_id: uuid.UUID, data: PoLinePatch
) -> PoLine:
    user.require("po:manage")
    po, pl = await _po_line(session, user, po_line_id)
    check_version(pl, data.row_version)
    _require_po_status(po, PoStatus.DRAFT, PoStatus.ISSUED, PoStatus.PARTIALLY_RECEIVED)
    pl.expected_date = data.expected_date
    pl.notes = data.notes
    await session.flush()
    await session.commit()
    return pl


async def cancel_po_line(
    session: AsyncSession, user: Principal, po_line_id: uuid.UUID, row_version: int
) -> PoLine:
    """Cancel what the vendor has not delivered on one line. What was received stays."""
    user.require("po:manage")
    po, pl = await _po_line(session, user, po_line_id)
    po = await _po(session, user, po.id, lock=True)
    check_version(pl, row_version)
    _require_po_status(po, PoStatus.ISSUED, PoStatus.PARTIALLY_RECEIVED)
    if pl.is_cancelled:
        raise ConflictError("The line is already cancelled", code="already_cancelled")
    rec = (await receipts_by_po_line(session, [pl.id]))[pl.id]
    if rec.on_hold > 0:
        raise ConflictError("Resolve the quantity on hold for this line first", code="hold_pending")
    pl.is_cancelled = True
    await session.flush()
    await _refresh_po_status(session, po)
    await session.commit()
    return pl


async def _refresh_po_status(session: AsyncSession, po: PurchaseOrder) -> None:
    if po.status not in _RECEIVABLE:
        return
    lines = await po_lines(session, po.id)
    rec = await receipts_by_po_line(session, [pl.id for pl in lines])
    live = [pl for pl in lines if not pl.is_cancelled]
    any_good = any(rec[pl.id].good > 0 for pl in lines)
    if live and all(rec[pl.id].accepted >= pl.qty_ordered for pl in live):
        status = PoStatus.RECEIVED
    elif not live:  # every line cancelled after partial receipts
        status = PoStatus.RECEIVED if any_good else PoStatus.ISSUED
    elif any_good:
        status = PoStatus.PARTIALLY_RECEIVED
    else:
        status = PoStatus.ISSUED
    if po.status != status.value:
        po.status = status.value
        await session.flush()


@dataclass
class PoFilter:
    status: list[str] = field(default_factory=list)
    vendor_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    q: str | None = None


async def list_pos(session: AsyncSession, user: Principal, f: PoFilter) -> list[PurchaseOrder]:
    user.require("procurement:read")
    stmt: Select[PurchaseOrder] = (
        select(PurchaseOrder)
        .where(PurchaseOrder.is_deleted.is_(False))
        .order_by(PurchaseOrder.created_at.desc())
    )
    if f.status:
        stmt = stmt.where(PurchaseOrder.status.in_(f.status))
    if f.vendor_id:
        stmt = stmt.where(PurchaseOrder.vendor_id == f.vendor_id)
    if f.q:
        stmt = stmt.where(PurchaseOrder.number.ilike(f"%{f.q.strip()}%"))
    orders = list((await session.execute(stmt)).scalars().all())
    projects = await po_projects(session, [po.id for po in orders])
    scope = await _visible_projects(session, user)
    return [
        po
        for po in orders
        if _po_in_scope(scope, projects[po.id])
        and (f.project_id is None or f.project_id in projects[po.id])
    ]


async def get_po(session: AsyncSession, user: Principal, po_id: uuid.UUID) -> PurchaseOrder:
    return await _po(session, user, po_id)


# ---------------------------------------------------------------- goods receipts


async def _distribute(
    session: AsyncSession,
    *,
    grn_line: GrnLine,
    po_line: PoLine,
    qty: Decimal,
    location_id: uuid.UUID,
    lot: str | None,
) -> None:
    """Post accepted quantity: allocations first (oldest first, each up to what it still
    lacks), reserved for their projects; the rest is free stock."""
    allocs = (await line_allocations(session, [po_line.id]))[po_line.id]
    got = await quantities.received_by_allocation(session, [a.id for a in allocs])
    remaining = qty
    for a in allocs:
        take = min(max(a.qty - got.get(a.id, ZERO), ZERO), remaining)
        if take <= 0:
            continue
        session.add(
            GrnAllocation(
                grn_line_id=grn_line.id,
                allocation_id=a.id,
                boq_line_id=a.boq_line_id,
                project_id=a.project_id,
                qty=take,
            )
        )
        await inventory.post_movement(
            session,
            part_id=po_line.part_id,
            location_id=location_id,
            qty_delta=take,
            reason=LedgerReason.GRN,
            ref_type=GRN_LINE_REF,
            ref_id=grn_line.id,
            lot_code=lot,
            project_id=a.project_id,
        )
        await inventory.reserve(
            session,
            part_id=po_line.part_id,
            project_id=a.project_id,
            qty=take,
            location_id=location_id,
            note=f"Received on {grn_line.id}",
        )
        remaining -= take
        if remaining <= 0:
            break
    if remaining > 0:
        await inventory.post_movement(
            session,
            part_id=po_line.part_id,
            location_id=location_id,
            qty_delta=remaining,
            reason=LedgerReason.GRN,
            ref_type=GRN_LINE_REF,
            ref_id=grn_line.id,
            lot_code=lot,
        )
    await session.flush()


def _inspection(acc: Decimal, rej: Decimal, hold: Decimal) -> InspectionResult:
    parts_ = [q > 0 for q in (acc, rej, hold)]
    if sum(parts_) > 1:
        return InspectionResult.PARTIAL
    if rej > 0:
        return InspectionResult.REJECT
    if hold > 0:
        return InspectionResult.HOLD
    return InspectionResult.ACCEPT


async def _vendor_return(
    session: AsyncSession, grn_line: GrnLine, vendor_id: uuid.UUID, qty: Decimal, reason: str
) -> VendorReturn:
    ret = VendorReturn(
        number=await next_number(session, "RTN"),
        grn_line_id=grn_line.id,
        vendor_id=vendor_id,
        qty=qty,
        reason=reason,
    )
    session.add(ret)
    await session.flush()
    return ret


async def receive(session: AsyncSession, user: Principal, data: GrnCreate) -> GoodsReceipt:
    """Post a goods receipt. The purchase order row is locked for the whole transaction, so
    concurrent receipts against the same order are applied one after the other and each
    one sees what the previous one received."""
    user.require("grn:create")
    po = await _po(session, user, data.purchase_order_id, lock=True)
    grn = await post_receipt(session, po, data, received_by=user.id)
    await session.commit()
    return grn


async def post_receipt(
    session: AsyncSession, po: PurchaseOrder, data: GrnCreate, *, received_by: uuid.UUID | None
) -> GoodsReceipt:
    """Validate and post a receipt against an order the caller has already locked
    (``receive`` does that after the permission and scope checks; the seed data uses it
    directly). Does not commit."""
    if po.status not in _RECEIVABLE:
        raise ConflictError(
            f"{po.number} is {po.status.replace('_', ' ')}; only issued orders can be received",
            code="order_not_receivable",
        )
    lines = {pl.id: pl for pl in await po_lines(session, po.id)}
    requested: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for ln in data.lines:
        pl = lines.get(ln.po_line_id)
        if pl is None:
            raise NotFoundError(
                "PO line not found on this order", details={"id": str(ln.po_line_id)}
            )
        if pl.is_cancelled:
            raise ConflictError(f"Line {pl.line_no} is cancelled", code="line_cancelled")
        await inventory.get_location(session, ln.location_id)
        requested[pl.id] += ln.qty_accepted + ln.qty_on_hold
    rec = await receipts_by_po_line(session, list(requested))
    for line_id, qty in requested.items():
        pl = lines[line_id]
        left = outstanding(pl, rec[line_id])
        if qty > left:
            raise ConflictError(
                f"Line {pl.line_no}: {qty.normalize():f} would exceed the outstanding "
                f"{left.normalize():f}",
                code="over_receipt",
                details={"line_no": pl.line_no, "outstanding": str(left), "requested": str(qty)},
            )

    grn = GoodsReceipt(
        number=await next_number(session, "GRN"),
        purchase_order_id=po.id,
        status=GrnStatus.POSTED.value,
        received_at=data.received_at or utcnow(),
        received_by=received_by,
        delivery_note_ref=data.delivery_note_ref,
        notes=data.notes,
    )
    session.add(grn)
    await session.flush()
    part_map = await parts.get_many(session, [pl.part_id for pl in lines.values()])
    for ln in data.lines:
        pl = lines[ln.po_line_id]
        gl = GrnLine(
            goods_receipt_id=grn.id,
            po_line_id=pl.id,
            location_id=ln.location_id,
            qty_received=ln.qty_received,
            qty_accepted=ln.qty_accepted,
            qty_rejected=ln.qty_rejected,
            qty_on_hold=ln.qty_on_hold,
            batch_lot=ln.batch_lot,
            date_code=ln.date_code,
            msl_level=ln.msl_level or part_map[pl.part_id].msl_level,
            inspection_result=_inspection(ln.qty_accepted, ln.qty_rejected, ln.qty_on_hold).value,
            notes=ln.notes,
        )
        session.add(gl)
        await session.flush()
        if ln.qty_accepted > 0:
            await _distribute(
                session,
                grn_line=gl,
                po_line=pl,
                qty=ln.qty_accepted,
                location_id=ln.location_id,
                lot=ln.batch_lot,
            )
        if ln.qty_rejected > 0:
            await _vendor_return(session, gl, po.vendor_id, ln.qty_rejected, ln.reject_reason or "")
    await _refresh_po_status(session, po)
    return grn


async def _grn(session: AsyncSession, user: Principal, grn_id: uuid.UUID) -> GoodsReceipt:
    user.require("procurement:read")
    grn = await session.get(GoodsReceipt, grn_id)
    if grn is None or grn.is_deleted:
        raise NotFoundError("Goods receipt not found", details={"id": str(grn_id)})
    try:
        await _po(session, user, grn.purchase_order_id)
    except NotFoundError as exc:
        raise NotFoundError("Goods receipt not found", details={"id": str(grn_id)}) from exc
    return grn


async def get_grn(session: AsyncSession, user: Principal, grn_id: uuid.UUID) -> GoodsReceipt:
    return await _grn(session, user, grn_id)


async def grn_lines(session: AsyncSession, grn_ids: list[uuid.UUID]) -> list[GrnLine]:
    if not grn_ids:
        return []
    rows = await session.execute(
        select(GrnLine)
        .where(GrnLine.goods_receipt_id.in_(grn_ids), GrnLine.is_deleted.is_(False))
        .order_by(GrnLine.created_at, GrnLine.id)
    )
    return list(rows.scalars().all())


async def grn_allocations(
    session: AsyncSession, grn_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[GrnAllocation]]:
    out: dict[uuid.UUID, list[GrnAllocation]] = defaultdict(list)
    if not grn_line_ids:
        return out
    rows = await session.execute(
        select(GrnAllocation).where(
            GrnAllocation.grn_line_id.in_(grn_line_ids), GrnAllocation.is_deleted.is_(False)
        )
    )
    for a in rows.scalars():
        out[a.grn_line_id].append(a)
    return out


async def list_grns(
    session: AsyncSession, user: Principal, *, po_id: uuid.UUID | None = None
) -> list[GoodsReceipt]:
    user.require("procurement:read")
    stmt = (
        select(GoodsReceipt)
        .where(GoodsReceipt.is_deleted.is_(False))
        .order_by(GoodsReceipt.created_at.desc())
    )
    if po_id:
        stmt = stmt.where(GoodsReceipt.purchase_order_id == po_id)
    grns = list((await session.execute(stmt)).scalars().all())
    scope = await _visible_projects(session, user)
    if scope is None:
        return grns
    projects = await po_projects(session, [g.purchase_order_id for g in grns])
    return [g for g in grns if _po_in_scope(scope, projects[g.purchase_order_id])]


async def patch_grn(
    session: AsyncSession, user: Principal, grn_id: uuid.UUID, data: GrnPatch
) -> GoodsReceipt:
    user.require("grn:create")
    grn = await _grn(session, user, grn_id)
    check_version(grn, data.row_version)
    if data.coc_file_id is not None:
        files = await attachments.list_for(session, user, "grn", grn.id)
        if data.coc_file_id not in {f.id for f, _ in files}:
            raise AppError(
                "The certificate of conformance must be a file attached to this GRN",
                code="file_not_attached",
                status_code=422,
            )
    grn.coc_file_id = data.coc_file_id
    grn.delivery_note_ref = data.delivery_note_ref
    grn.notes = data.notes
    await session.flush()
    await session.commit()
    return grn


async def resolve_hold(
    session: AsyncSession, user: Principal, grn_line_id: uuid.UUID, data: HoldResolution
) -> GrnLine:
    """Move quantity on hold to accepted (posts stock) and/or rejected (vendor return)."""
    user.require("grn:create")
    gl = await session.get(GrnLine, grn_line_id)
    if gl is None or gl.is_deleted:
        raise NotFoundError("GRN line not found", details={"id": str(grn_line_id)})
    grn = await _grn(session, user, gl.goods_receipt_id)
    po = await _po(session, user, grn.purchase_order_id, lock=True)
    await session.refresh(gl)
    check_version(gl, data.row_version)
    if data.accept_qty + data.reject_qty > gl.qty_on_hold:
        raise ConflictError(f"Only {gl.qty_on_hold.normalize():f} is on hold", code="exceeds_hold")
    pl = await session.get(PoLine, gl.po_line_id)
    assert pl is not None
    gl.qty_on_hold -= data.accept_qty + data.reject_qty
    gl.qty_accepted += data.accept_qty
    gl.qty_rejected += data.reject_qty
    gl.inspection_result = _inspection(gl.qty_accepted, gl.qty_rejected, gl.qty_on_hold).value
    await session.flush()
    if data.accept_qty > 0:
        assert gl.location_id is not None
        await _distribute(
            session,
            grn_line=gl,
            po_line=pl,
            qty=data.accept_qty,
            location_id=gl.location_id,
            lot=gl.batch_lot,
        )
    if data.reject_qty > 0:
        await _vendor_return(session, gl, po.vendor_id, data.reject_qty, data.reason or "")
    await _refresh_po_status(session, po)
    await session.commit()
    return gl


# ---------------------------------------------------------------- vendor returns


async def list_returns(
    session: AsyncSession,
    user: Principal,
    *,
    status: list[str] | None = None,
    grn_ids: list[uuid.UUID] | None = None,
) -> list[tuple[VendorReturn, GrnLine, GoodsReceipt]]:
    user.require("procurement:read")
    stmt = (
        select(VendorReturn, GrnLine, GoodsReceipt)
        .join(GrnLine, GrnLine.id == VendorReturn.grn_line_id)
        .join(GoodsReceipt, GoodsReceipt.id == GrnLine.goods_receipt_id)
        .where(VendorReturn.is_deleted.is_(False))
        .order_by(VendorReturn.created_at.desc())
    )
    if status:
        stmt = stmt.where(VendorReturn.status.in_(status))
    if grn_ids is not None:
        stmt = stmt.where(GoodsReceipt.id.in_(grn_ids))
    rows = [(r, gl, g) for r, gl, g in (await session.execute(stmt)).all()]
    scope = await _visible_projects(session, user)
    if scope is None:
        return rows
    projects = await po_projects(session, [g.purchase_order_id for _, _, g in rows])
    return [row for row in rows if _po_in_scope(scope, projects[row[2].purchase_order_id])]


async def update_return(
    session: AsyncSession, user: Principal, return_id: uuid.UUID, data: ReturnUpdate
) -> VendorReturn:
    user.require("grn:create")
    ret = await session.get(VendorReturn, return_id)
    if ret is None or ret.is_deleted:
        raise NotFoundError("Vendor return not found", details={"id": str(return_id)})
    gl = await session.get(GrnLine, ret.grn_line_id)
    assert gl is not None
    await _grn(session, user, gl.goods_receipt_id)
    check_version(ret, data.row_version)
    if ret.status == ReturnStatus.CLOSED.value:
        raise ConflictError("The return is closed", code="invalid_status_transition")
    ret.status = data.status
    if data.note:
        ret.reason = f"{ret.reason}\n{data.note}"
    await session.flush()
    await session.commit()
    return ret


# ---------------------------------------------------------------- attachments


async def _vendor_files(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    user.require("procurement:read")
    await _vendor(session, ref_id)


async def _grn_files(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    await _grn(session, user, ref_id)


attachments.register_ref_type("vendor", _vendor_files)
attachments.register_ref_type("grn", _grn_files)
