"""QC service. Phase 7 needs one question answered for stage gating; Phase 8 adds
templates, inspections, photo evidence and NCRs here."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.qc.models import InspectionStatus, QcInspection


async def passed_inspection_exists(
    session: AsyncSession,
    *,
    work_order_stage_id: uuid.UUID,
    lot_id: uuid.UUID,
    serial_unit_id: uuid.UUID | None = None,
) -> bool:
    """True when a passed inspection covers this stage for the unit (an inspection of the
    unit itself, or of its whole lot) or, without a unit, for the lot."""
    subject = (
        or_(
            QcInspection.serial_unit_id == serial_unit_id,
            (QcInspection.serial_unit_id.is_(None)) & (QcInspection.lot_id == lot_id),
        )
        if serial_unit_id is not None
        else (QcInspection.serial_unit_id.is_(None)) & (QcInspection.lot_id == lot_id)
    )
    row = await session.execute(
        select(QcInspection.id)
        .where(
            QcInspection.work_order_stage_id == work_order_stage_id,
            QcInspection.status == InspectionStatus.PASSED.value,
            QcInspection.is_deleted.is_(False),
            subject,
        )
        .limit(1)
    )
    return row.first() is not None
