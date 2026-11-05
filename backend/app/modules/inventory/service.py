"""Inventory service: the ONLY way stock changes.

Every movement is a ledger row; the materialised ``stock_balances`` row for the same
part and location is updated in the same transaction, after taking a row lock, so the
balance can never drift from SUM(ledger) and never goes negative.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import current_actor_id
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.models import utcnow
from app.core.repository import check_version
from app.modules.auth.service import Principal
from app.modules.inventory.models import (
    AdjustmentStatus,
    InventoryLocation,
    LedgerEntry,
    LedgerReason,
    LocationKind,
    ReservationStatus,
    StockAdjustment,
    StockBalance,
    StockReservation,
)
from app.modules.org import service as org
from app.modules.parts.models import Part

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


# ---------------------------------------------------------------- issues to BOQ lines
# Kitting (Phase 7) issues stock against a BOQ line: ledger ISSUE rows with
# ref_type="boq_line". Returns of unused parts are RETURN rows with the same reference.

BOQ_LINE_REF = "boq_line"


async def issue_to_boq_line(
    session: AsyncSession,
    *,
    part_id: uuid.UUID,
    location_id: uuid.UUID,
    qty: Decimal | int | str,
    boq_line_id: uuid.UUID,
    project_id: uuid.UUID,
    lot_code: str | None = None,
    note: str | None = None,
) -> LedgerEntry:
    amount = Decimal(qty)
    if amount <= 0:
        raise AppError("Issue quantity must be positive", code="invalid_quantity")
    return await post_movement(
        session,
        part_id=part_id,
        location_id=location_id,
        qty_delta=-amount,
        reason=LedgerReason.ISSUE,
        ref_type=BOQ_LINE_REF,
        ref_id=boq_line_id,
        lot_code=lot_code,
        project_id=project_id,
        note=note,
    )


async def return_from_boq_line(
    session: AsyncSession,
    *,
    part_id: uuid.UUID,
    location_id: uuid.UUID,
    qty: Decimal | int | str,
    boq_line_id: uuid.UUID,
    project_id: uuid.UUID,
    lot_code: str | None = None,
    note: str | None = None,
) -> LedgerEntry:
    amount = Decimal(qty)
    if amount <= 0:
        raise AppError("Return quantity must be positive", code="invalid_quantity")
    issued = (await issued_by_boq_line(session, [boq_line_id])).get(boq_line_id, Decimal(0))
    if amount > issued:
        raise ConflictError(
            "Cannot return more than was issued to this line",
            code="return_exceeds_issue",
            details={"issued": str(issued)},
        )
    return await post_movement(
        session,
        part_id=part_id,
        location_id=location_id,
        qty_delta=amount,
        reason=LedgerReason.RETURN,
        ref_type=BOQ_LINE_REF,
        ref_id=boq_line_id,
        lot_code=lot_code,
        project_id=project_id,
        note=note,
    )


async def issued_by_boq_line(
    session: AsyncSession, boq_line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """Net issued quantity per BOQ line: ISSUE rows (negative) minus RETURN rows."""
    if not boq_line_ids:
        return {}
    rows = (
        await session.execute(
            select(LedgerEntry.ref_id, func.sum(-LedgerEntry.qty_delta))
            .where(
                LedgerEntry.ref_type == BOQ_LINE_REF,
                LedgerEntry.ref_id.in_(boq_line_ids),
                LedgerEntry.reason.in_([LedgerReason.ISSUE.value, LedgerReason.RETURN.value]),
            )
            .group_by(LedgerEntry.ref_id)
        )
    ).all()
    return {ref_id: Decimal(total) for ref_id, total in rows if ref_id is not None}


# ---------------------------------------------------------------- reservations


async def get_location(session: AsyncSession, location_id: uuid.UUID) -> InventoryLocation:
    loc = await session.get(InventoryLocation, location_id)
    if loc is None or loc.is_deleted:
        raise NotFoundError("Location not found", details={"id": str(location_id)})
    return loc


async def reserve(
    session: AsyncSession,
    *,
    part_id: uuid.UUID,
    project_id: uuid.UUID,
    qty: Decimal,
    location_id: uuid.UUID | None = None,
    note: str | None = None,
) -> StockReservation:
    """Earmark stock for a project (received against its PO allocation, or set aside by
    stores). Does not move stock; available = on hand - active reservations."""
    reservation = StockReservation(
        part_id=part_id, project_id=project_id, location_id=location_id, qty=qty, note=note
    )
    session.add(reservation)
    await session.flush()
    return reservation


# ---------------------------------------------------------------- user-facing operations
# Permission checks live here (service layer), not only in the router.

# Stock in these locations can be used for production; quarantine, scrap and WIP cannot.
USABLE_KINDS = (LocationKind.STORES.value, LocationKind.BIN.value, LocationKind.MSL_CABINET.value)


async def list_locations(session: AsyncSession, user: Principal) -> list[InventoryLocation]:
    user.require("inventory:read")
    rows = await session.execute(
        select(InventoryLocation)
        .where(InventoryLocation.is_deleted.is_(False))
        .order_by(InventoryLocation.code)
    )
    return list(rows.scalars().all())


async def stock_rows(
    session: AsyncSession,
    user: Principal,
    *,
    q: str | None = None,
    location_id: uuid.UUID | None = None,
) -> list[tuple[Part, InventoryLocation, Decimal]]:
    """Non-zero balances by part and location."""
    user.require("inventory:read")
    stmt = (
        select(Part, InventoryLocation, StockBalance.qty_on_hand)
        .join(Part, Part.id == StockBalance.part_id)
        .join(InventoryLocation, InventoryLocation.id == StockBalance.location_id)
        .where(StockBalance.qty_on_hand != 0)
        .order_by(Part.mpn, InventoryLocation.code)
    )
    if location_id:
        stmt = stmt.where(StockBalance.location_id == location_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Part.mpn.ilike(like), Part.description.ilike(like)))
    return [(p, loc, Decimal(qty)) for p, loc, qty in (await session.execute(stmt)).all()]


async def active_reserved(
    session: AsyncSession, part_ids: list[uuid.UUID] | None = None
) -> dict[uuid.UUID, Decimal]:
    stmt = (
        select(StockReservation.part_id, func.sum(StockReservation.qty))
        .where(
            StockReservation.status == ReservationStatus.ACTIVE.value,
            StockReservation.is_deleted.is_(False),
        )
        .group_by(StockReservation.part_id)
    )
    if part_ids is not None:
        stmt = stmt.where(StockReservation.part_id.in_(part_ids))
    return {pid: Decimal(q) for pid, q in (await session.execute(stmt)).all()}


async def part_stock(
    session: AsyncSession, user: Principal, *, q: str | None = None, low_only: bool = False
) -> list[dict[str, Any]]:
    """One row per part that has stock or a minimum level: on hand, usable (excludes
    quarantine, scrap and WIP), reserved for projects, available = usable - reserved, and
    the low-stock flag (available below the part's minimum)."""
    user.require("inventory:read")
    rows = await session.execute(
        select(
            StockBalance.part_id,
            InventoryLocation.kind,
            InventoryLocation.code,
            StockBalance.qty_on_hand,
        )
        .join(InventoryLocation, InventoryLocation.id == StockBalance.location_id)
        .where(StockBalance.qty_on_hand != 0)
    )
    on_hand: dict[uuid.UUID, Decimal] = {}
    usable: dict[uuid.UUID, Decimal] = {}
    where: dict[uuid.UUID, list[str]] = {}
    for part_id, kind, code, qty in rows.all():
        on_hand[part_id] = on_hand.get(part_id, Decimal(0)) + qty
        if kind in USABLE_KINDS:
            usable[part_id] = usable.get(part_id, Decimal(0)) + qty
        where.setdefault(part_id, []).append(code)
    stmt = select(Part).where(
        Part.is_deleted.is_(False),
        or_(Part.id.in_(list(on_hand) or [uuid.UUID(int=0)]), Part.min_stock.is_not(None)),
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Part.mpn.ilike(like), Part.description.ilike(like)))
    found = list((await session.execute(stmt.order_by(Part.mpn))).scalars().all())
    reserved = await active_reserved(session, [p.id for p in found])
    out = []
    for p in found:
        use = usable.get(p.id, Decimal(0))
        res = reserved.get(p.id, Decimal(0))
        available = use - res
        low = p.min_stock is not None and available < p.min_stock
        if low_only and not low:
            continue
        out.append(
            {
                "part_id": p.id,
                "mpn": p.mpn,
                "manufacturer": p.manufacturer,
                "description": p.description,
                "category": p.category,
                "unit": p.unit,
                "min_stock": p.min_stock,
                "on_hand": on_hand.get(p.id, Decimal(0)),
                "usable": use,
                "reserved": res,
                "available": available,
                "low": low,
                "locations": sorted(where.get(p.id, [])),
            }
        )
    return out


async def ledger_page(
    session: AsyncSession,
    user: Principal,
    *,
    part_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    reason: str | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[LedgerEntry], int]:
    user.require("inventory:read")
    stmt = select(LedgerEntry)
    if part_id:
        stmt = stmt.where(LedgerEntry.part_id == part_id)
    if location_id:
        stmt = stmt.where(LedgerEntry.location_id == location_id)
    if reason:
        stmt = stmt.where(LedgerEntry.reason == reason)
    if project_id:
        stmt = stmt.where(LedgerEntry.project_id == project_id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = await session.execute(
        stmt.order_by(LedgerEntry.id.desc()).limit(min(limit, 1000)).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def user_transfer(
    session: AsyncSession,
    user: Principal,
    *,
    part_id: uuid.UUID,
    from_location_id: uuid.UUID,
    to_location_id: uuid.UUID,
    qty: Decimal,
    lot_code: str | None,
    note: str | None,
) -> tuple[LedgerEntry, LedgerEntry]:
    user.require("inventory:transfer")
    await get_location(session, from_location_id)
    await get_location(session, to_location_id)
    pair = await transfer(
        session,
        part_id=part_id,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        qty=qty,
        lot_code=lot_code,
        note=note,
    )
    # Reservations at the source follow the stock to its new location.
    reservations = (
        (
            await session.execute(
                select(StockReservation).where(
                    StockReservation.part_id == part_id,
                    StockReservation.location_id == from_location_id,
                    StockReservation.status == ReservationStatus.ACTIVE.value,
                    StockReservation.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    left = (
        await session.execute(
            select(StockBalance.qty_on_hand).where(
                StockBalance.part_id == part_id, StockBalance.location_id == from_location_id
            )
        )
    ).scalar_one_or_none() or Decimal(0)
    reserved_here = sum((r.qty for r in reservations), Decimal(0))
    if reserved_here > left:
        for r in reservations:
            r.location_id = to_location_id
    await session.flush()
    await session.commit()
    return pair


async def request_adjustment(
    session: AsyncSession,
    user: Principal,
    *,
    part_id: uuid.UUID,
    location_id: uuid.UUID,
    qty_delta: Decimal,
    reason: str,
    lot_code: str | None,
) -> StockAdjustment:
    user.require("inventory:adjust")
    if qty_delta == 0:
        raise AppError("Quantity change cannot be zero", code="zero_quantity")
    await get_location(session, location_id)
    adj = StockAdjustment(
        part_id=part_id,
        location_id=location_id,
        qty_delta=qty_delta,
        reason=reason,
        lot_code=lot_code,
        requested_by=user.id,
    )
    session.add(adj)
    await session.flush()
    await session.commit()
    return adj


async def decide_adjustment(
    session: AsyncSession,
    user: Principal,
    adjustment_id: uuid.UUID,
    *,
    row_version: int,
    approve: bool,
    note: str | None,
) -> StockAdjustment:
    """Approval posts the ADJUST ledger entry. Nobody approves their own request."""
    user.require("inventory:approve_adjustment")
    adj = (
        await session.execute(
            select(StockAdjustment).where(StockAdjustment.id == adjustment_id).with_for_update()
        )
    ).scalar_one_or_none()
    if adj is None or adj.is_deleted:
        raise NotFoundError("Adjustment not found", details={"id": str(adjustment_id)})
    check_version(adj, row_version)
    if adj.status != AdjustmentStatus.PENDING.value:
        raise ConflictError(f"The adjustment is already {adj.status}", code="already_decided")
    if adj.requested_by == user.id:
        raise PermissionDeniedError(
            "Someone else must approve your own adjustment request", code="self_approval"
        )
    if approve:
        entry = await post_movement(
            session,
            part_id=adj.part_id,
            location_id=adj.location_id,
            qty_delta=adj.qty_delta,
            reason=LedgerReason.ADJUST,
            ref_type="stock_adjustment",
            ref_id=adj.id,
            lot_code=adj.lot_code,
            note=adj.reason,
        )
        adj.ledger_entry_id = entry.id
    adj.status = (AdjustmentStatus.APPROVED if approve else AdjustmentStatus.REJECTED).value
    adj.decided_by = user.id
    adj.decided_at = utcnow()
    adj.decision_note = note
    await session.flush()
    await session.commit()
    return adj


async def list_adjustments(
    session: AsyncSession, user: Principal, *, status: str | None = None
) -> list[StockAdjustment]:
    user.require("inventory:read")
    stmt = select(StockAdjustment).where(StockAdjustment.is_deleted.is_(False))
    if status:
        stmt = stmt.where(StockAdjustment.status == status)
    rows = await session.execute(stmt.order_by(StockAdjustment.created_at.desc()))
    return list(rows.scalars().all())


async def list_reservations(
    session: AsyncSession,
    user: Principal,
    *,
    project_id: uuid.UUID | None = None,
    include_closed: bool = False,
) -> list[StockReservation]:
    user.require("inventory:read")
    stmt = select(StockReservation).where(StockReservation.is_deleted.is_(False))
    if not include_closed:
        stmt = stmt.where(StockReservation.status == ReservationStatus.ACTIVE.value)
    if project_id:
        stmt = stmt.where(StockReservation.project_id == project_id)
    scope = await org.scoped_project_ids(session, user)
    if scope is not None:
        stmt = stmt.where(StockReservation.project_id.in_(scope))
    rows = await session.execute(stmt.order_by(StockReservation.created_at.desc()))
    return list(rows.scalars().all())


async def user_reserve(
    session: AsyncSession,
    user: Principal,
    *,
    part_id: uuid.UUID,
    project_id: uuid.UUID,
    qty: Decimal,
    location_id: uuid.UUID | None,
    note: str | None,
) -> StockReservation:
    """Set free stock aside for a project. Cannot reserve more than is available."""
    user.require("inventory:transfer")
    await org.get_project(session, user, project_id)
    if location_id:
        await get_location(session, location_id)
    # Serialise reservations of the same part: lock its balance rows.
    await session.execute(
        select(StockBalance.part_id).where(StockBalance.part_id == part_id).with_for_update()
    )
    rows = await part_stock_for(session, part_id)
    if qty > rows["available"]:
        raise InsufficientStockError(
            "Not enough free stock to reserve",
            details={"available": str(rows["available"]), "requested": str(qty)},
        )
    reservation = await reserve(
        session, part_id=part_id, project_id=project_id, qty=qty, location_id=location_id, note=note
    )
    await session.commit()
    return reservation


async def part_stock_for(session: AsyncSession, part_id: uuid.UUID) -> dict[str, Decimal]:
    usable = (
        await session.execute(
            select(func.coalesce(func.sum(StockBalance.qty_on_hand), 0))
            .join(InventoryLocation, InventoryLocation.id == StockBalance.location_id)
            .where(StockBalance.part_id == part_id, InventoryLocation.kind.in_(USABLE_KINDS))
        )
    ).scalar_one()
    reserved = (await active_reserved(session, [part_id])).get(part_id, Decimal(0))
    return {
        "usable": Decimal(usable),
        "reserved": reserved,
        "available": Decimal(usable) - reserved,
    }


async def release_reservation(
    session: AsyncSession, user: Principal, reservation_id: uuid.UUID, row_version: int
) -> StockReservation:
    user.require("inventory:transfer")
    r = await session.get(StockReservation, reservation_id)
    if r is None or r.is_deleted:
        raise NotFoundError("Reservation not found", details={"id": str(reservation_id)})
    await org.get_project(session, user, r.project_id)
    check_version(r, row_version)
    if r.status != ReservationStatus.ACTIVE.value:
        raise ConflictError(f"The reservation is already {r.status}", code="already_closed")
    r.status = ReservationStatus.RELEASED.value
    await session.flush()
    await session.commit()
    return r
