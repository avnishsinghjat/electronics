"""Per-BOQ-line procurement quantities: the inputs of the status service.

The BOQ module calls this; it does not import the BOQ module back (no cycle). BOQ lines are
identified by groups: a line of the current revision plus the lines of earlier revisions with
the same stable line key, so orders placed against revision A still count once revision B
is released.

    ordered   = allocations on PO lines of issued (or later, closed included) orders; for a
                cancelled PO line only what was received on it (cancelling cancels the
                undelivered rest). Draft orders are not ordered yet: see being_ordered.
    received  = accepted GRN quantity allocated to the line
    issued    = kitting issues to the line (ledger ISSUE minus RETURN, ref boq_line)
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory import service as inventory
from app.modules.procurement.models import (
    GoodsReceipt,
    GrnAllocation,
    GrnLine,
    GrnStatus,
    PoLine,
    PoLineAllocation,
    PoStatus,
    PurchaseOrder,
    Vendor,
)

ZERO = Decimal(0)


@dataclass(frozen=True)
class AllocationInfo:
    """One PO line's share for one BOQ line, as the tracker shows it."""

    allocation_id: uuid.UUID
    boq_line_id: uuid.UUID
    project_id: uuid.UUID
    po_id: uuid.UUID
    po_number: str
    po_status: str
    po_line_id: uuid.UUID
    po_line_no: int
    vendor_id: uuid.UUID
    vendor_name: str
    expected_date: date | None
    unit_price: Decimal | None
    allocated: Decimal
    received: Decimal
    line_cancelled: bool

    @property
    def ordered(self) -> Decimal:
        """What this allocation contributes to ordered_qty."""
        if self.po_status in (PoStatus.CANCELLED.value, PoStatus.DRAFT.value):
            return ZERO
        if self.line_cancelled:
            return min(self.allocated, self.received)
        return self.allocated

    @property
    def drafted(self) -> Decimal:
        """On a draft order: in purchasing, not yet ordered."""
        return self.allocated if self.po_status == PoStatus.DRAFT.value else ZERO

    @property
    def outstanding(self) -> Decimal:
        return max(self.ordered - self.received, ZERO)


async def received_by_allocation(
    session: AsyncSession, allocation_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    if not allocation_ids:
        return {}
    rows = (
        await session.execute(
            select(GrnAllocation.allocation_id, func.sum(GrnAllocation.qty))
            .join(GrnLine, GrnLine.id == GrnAllocation.grn_line_id)
            .join(GoodsReceipt, GoodsReceipt.id == GrnLine.goods_receipt_id)
            .where(
                GrnAllocation.allocation_id.in_(allocation_ids),
                GrnAllocation.is_deleted.is_(False),
                GoodsReceipt.status == GrnStatus.POSTED.value,
            )
            .group_by(GrnAllocation.allocation_id)
        )
    ).all()
    return {aid: Decimal(total) for aid, total in rows}


async def allocations_for(
    session: AsyncSession, boq_line_ids: list[uuid.UUID]
) -> list[AllocationInfo]:
    """Every live allocation to these BOQ lines (any PO status, cancelled included)."""
    if not boq_line_ids:
        return []
    rows = (
        await session.execute(
            select(PoLineAllocation, PoLine, PurchaseOrder, Vendor.name)
            .join(PoLine, PoLine.id == PoLineAllocation.po_line_id)
            .join(PurchaseOrder, PurchaseOrder.id == PoLine.purchase_order_id)
            .join(Vendor, Vendor.id == PurchaseOrder.vendor_id)
            .where(
                PoLineAllocation.boq_line_id.in_(boq_line_ids),
                PoLineAllocation.is_deleted.is_(False),
                PoLine.is_deleted.is_(False),
                PurchaseOrder.is_deleted.is_(False),
            )
            .order_by(PoLine.expected_date.asc().nulls_last(), PurchaseOrder.number)
        )
    ).all()
    received = await received_by_allocation(session, [a.id for a, *_ in rows])
    return [
        AllocationInfo(
            allocation_id=a.id,
            boq_line_id=a.boq_line_id,
            project_id=a.project_id,
            po_id=po.id,
            po_number=po.number,
            po_status=po.status,
            po_line_id=pl.id,
            po_line_no=pl.line_no,
            vendor_id=po.vendor_id,
            vendor_name=vendor_name,
            expected_date=pl.expected_date,
            unit_price=pl.unit_price,
            allocated=a.qty,
            received=received.get(a.id, ZERO),
            line_cancelled=pl.is_cancelled,
        )
        for a, pl, po, vendor_name in rows
    ]


async def line_quantities(
    session: AsyncSession, groups: dict[uuid.UUID, list[uuid.UUID]]
) -> dict[uuid.UUID, tuple[Decimal, Decimal, Decimal]]:
    """Group key (a BOQ line id) -> (ordered, received, issued) summed over the group's
    line ids (the same line key across revisions of one BOQ)."""
    if not groups:
        return {}
    member_of: dict[uuid.UUID, uuid.UUID] = {}
    for key, members in groups.items():
        for m in {key, *members}:
            member_of[m] = key
    ids = list(member_of)
    ordered: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    received: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for info in await allocations_for(session, ids):
        key = member_of[info.boq_line_id]
        ordered[key] += info.ordered
        received[key] += info.received
    issued_by_line = await inventory.issued_by_boq_line(session, ids)
    issued: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for line_id, qty in issued_by_line.items():
        issued[member_of[line_id]] += qty
    return {key: (ordered[key], received[key], issued[key]) for key in groups}
