"""Inventory service: the ONLY way stock changes.

Every movement is a ledger row; the materialised ``stock_balances`` row for the same
part and location is updated in the same transaction, after taking a row lock, so the
balance can never drift from SUM(ledger) and never goes negative.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_actor_id
from app.core.errors import AppError, ConflictError
from app.core.models import utcnow
from app.modules.inventory.models import LedgerEntry, LedgerReason, StockBalance

_POSITIVE = {LedgerReason.GRN, LedgerReason.RETURN}
_NEGATIVE = {LedgerReason.ISSUE, LedgerReason.SCRAP}


class InsufficientStockError(ConflictError):
    code = "insufficient_stock"


@dataclass(frozen=True)
class BalanceMismatch:
    part_id: uuid.UUID
    location_id: uuid.UUID
    ledger_sum: Decimal
    balance: Decimal


def _validate(reason: LedgerReason, qty_delta: Decimal) -> None:
    if qty_delta == 0:
        raise AppError("Quantity change cannot be zero", code="zero_quantity")
    if reason in _POSITIVE and qty_delta < 0:
        raise AppError(f"{reason} movements must add stock", code="invalid_movement_sign")
    if reason in _NEGATIVE and qty_delta > 0:
        raise AppError(f"{reason} movements must remove stock", code="invalid_movement_sign")


async def post_movement(
    session: AsyncSession,
    *,
    part_id: uuid.UUID,
    location_id: uuid.UUID,
    qty_delta: Decimal | int | str,
    reason: LedgerReason,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    lot_code: str | None = None,
    project_id: uuid.UUID | None = None,
    note: str | None = None,
) -> LedgerEntry:
    delta = Decimal(qty_delta)
    reason = LedgerReason(reason)
    _validate(reason, delta)

    locked = (
        await session.execute(
            select(StockBalance.qty_on_hand)
            .where(StockBalance.part_id == part_id, StockBalance.location_id == location_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    current = Decimal(locked) if locked is not None else Decimal(0)
    if current + delta < 0:
        raise InsufficientStockError(
            "Not enough stock at this location",
            details={"on_hand": str(current), "requested": str(-delta)},
        )

    entry = LedgerEntry(
        part_id=part_id,
        location_id=location_id,
        qty_delta=delta,
        reason=reason.value,
        ref_type=ref_type,
        ref_id=ref_id,
        lot_code=lot_code,
        project_id=project_id,
        note=note,
        user_id=current_actor_id.get(),
    )
    session.add(entry)
    now = utcnow()
    if locked is not None:
        await session.execute(
            update(StockBalance)
            .where(StockBalance.part_id == part_id, StockBalance.location_id == location_id)
            .values(qty_on_hand=StockBalance.qty_on_hand + delta, updated_at=now)
        )
    else:
        # First stock at this location (delta > 0 here). ON CONFLICT covers a concurrent
        # first receipt; CHECKs are evaluated on the proposed row, so it must be >= 0.
        stmt = pg_insert(StockBalance).values(
            part_id=part_id, location_id=location_id, qty_on_hand=delta, updated_at=now
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[StockBalance.part_id, StockBalance.location_id],
                set_={
                    "qty_on_hand": StockBalance.qty_on_hand + stmt.excluded.qty_on_hand,
                    "updated_at": now,
                },
            )
        )
    await session.flush()
    return entry


async def transfer(
    session: AsyncSession,
    *,
    part_id: uuid.UUID,
    from_location_id: uuid.UUID,
    to_location_id: uuid.UUID,
    qty: Decimal | int | str,
    lot_code: str | None = None,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    note: str | None = None,
) -> tuple[LedgerEntry, LedgerEntry]:
    amount = Decimal(qty)
    if amount <= 0:
        raise AppError("Transfer quantity must be positive", code="invalid_quantity")
    if from_location_id == to_location_id:
        raise AppError("Source and destination are the same", code="same_location")
    out = await post_movement(
        session,
        part_id=part_id,
        location_id=from_location_id,
        qty_delta=-amount,
        reason=LedgerReason.TRANSFER,
        lot_code=lot_code,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
    )
    into = await post_movement(
        session,
        part_id=part_id,
        location_id=to_location_id,
        qty_delta=amount,
        reason=LedgerReason.TRANSFER,
        lot_code=lot_code,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
    )
    return out, into


async def stock_on_hand(
    session: AsyncSession, part_id: uuid.UUID, location_id: uuid.UUID | None = None
) -> Decimal:
    """Stock on hand computed from the ledger (the source of truth)."""
    stmt = select(func.coalesce(func.sum(LedgerEntry.qty_delta), 0)).where(
        LedgerEntry.part_id == part_id
    )
    if location_id is not None:
        stmt = stmt.where(LedgerEntry.location_id == location_id)
    return Decimal((await session.execute(stmt)).scalar_one())


async def verify_balances(session: AsyncSession) -> list[BalanceMismatch]:
    """Compare the materialised balance table with SUM(ledger). Empty list = consistent."""
    ledger = (
        select(
            LedgerEntry.part_id,
            LedgerEntry.location_id,
            func.sum(LedgerEntry.qty_delta).label("total"),
        )
        .group_by(LedgerEntry.part_id, LedgerEntry.location_id)
        .subquery()
    )
    stmt = (
        select(
            func.coalesce(ledger.c.part_id, StockBalance.part_id),
            func.coalesce(ledger.c.location_id, StockBalance.location_id),
            func.coalesce(ledger.c.total, 0),
            func.coalesce(StockBalance.qty_on_hand, 0),
        )
        .select_from(
            ledger.join(
                StockBalance,
                (ledger.c.part_id == StockBalance.part_id)
                & (ledger.c.location_id == StockBalance.location_id),
                full=True,
            )
        )
        .where(func.coalesce(ledger.c.total, 0) != func.coalesce(StockBalance.qty_on_hand, 0))
    )
    return [
        BalanceMismatch(
            part_id=r[0], location_id=r[1], ledger_sum=Decimal(r[2]), balance=Decimal(r[3])
        )
        for r in (await session.execute(stmt)).all()
    ]
