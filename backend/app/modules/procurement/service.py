"""Procurement service. Phase 5 provides the per-BOQ-line quantity aggregation used by the
status column; requisitions, purchase orders, goods receipts and the tracker arrive in
Phase 6 and extend these queries (received / issued)."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.procurement.models import PoLine, PoLineAllocation, PoStatus, PurchaseOrder

ZERO = Decimal(0)


async def line_quantities(
    session: AsyncSession, boq_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[Decimal, Decimal, Decimal]]:
    """BOQ line id -> (ordered, received, issued).

    ordered: quantities allocated to the line on purchase-order lines that are not
    cancelled, on orders that are not cancelled (open and closed orders both count).
    received / issued: accepted goods receipts and kitting issues post through the
    inventory ledger; neither can exist before Phase 6/7, so they are zero here.
    """
    if not boq_line_ids:
        return {}
    rows = (
        await session.execute(
            select(PoLineAllocation.boq_line_id, func.coalesce(func.sum(PoLineAllocation.qty), 0))
            .join(PoLine, PoLine.id == PoLineAllocation.po_line_id)
            .join(PurchaseOrder, PurchaseOrder.id == PoLine.purchase_order_id)
            .where(
                PoLineAllocation.boq_line_id.in_(boq_line_ids),
                PoLineAllocation.is_deleted.is_(False),
                PoLine.is_deleted.is_(False),
                PoLine.is_cancelled.is_(False),
                PurchaseOrder.is_deleted.is_(False),
                PurchaseOrder.status != PoStatus.CANCELLED.value,
            )
            .group_by(PoLineAllocation.boq_line_id)
        )
    ).all()
    ordered = {line_id: Decimal(total) for line_id, total in rows}
    return {lid: (ordered.get(lid, ZERO), ZERO, ZERO) for lid in boq_line_ids}
