import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.inventory import service
from app.modules.inventory.models import LedgerEntry, StockAdjustment, StockReservation
from app.modules.inventory.schemas import (
    AdjustmentDecision,
    AdjustmentIn,
    AdjustmentOut,
    LedgerPage,
    LedgerRow,
    LocationOut,
    PartStock,
    ReservationIn,
    ReservationOut,
    StockRow,
    TransferIn,
    VersionIn,
)
from app.modules.org import service as org
from app.modules.parts import service as parts
from app.modules.users import service as users

router = APIRouter(prefix="/inventory", tags=["inventory"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("inventory:read"))]
Mover = Annotated[Principal, Depends(require("inventory:transfer"))]
Adjuster = Annotated[Principal, Depends(require("inventory:adjust"))]
Approver = Annotated[Principal, Depends(require("inventory:approve_adjustment"))]


async def _location_codes(session: AsyncSession, user: Principal) -> dict[uuid.UUID, str]:
    return {loc.id: loc.code for loc in await service.list_locations(session, user)}


@router.get("/locations", response_model=list[LocationOut], summary="Stock locations")
async def locations(user: Reader, session: SessionDep) -> list[LocationOut]:
    return [
        LocationOut(id=x.id, code=x.code, name=x.name, kind=x.kind, parent_id=x.parent_id)
        for x in await service.list_locations(session, user)
    ]


@router.get("/stock", response_model=list[PartStock], summary="Stock by part (low-stock flag)")
async def stock(
    user: Reader,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    low_only: bool = False,
) -> list[PartStock]:
    return [PartStock(**r) for r in await service.part_stock(session, user, q=q, low_only=low_only)]


@router.get("/balances", response_model=list[StockRow], summary="Stock by part and location")
async def balances(
    user: Reader,
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    location_id: uuid.UUID | None = None,
) -> list[StockRow]:
    return [
        StockRow(
            part_id=p.id,
            mpn=p.mpn,
            manufacturer=p.manufacturer,
            description=p.description,
            category=p.category,
            unit=p.unit,
            msl_level=p.msl_level,
            location_id=loc.id,
            location_code=loc.code,
            location_kind=loc.kind,
            qty_on_hand=qty,
        )
        for p, loc, qty in await service.stock_rows(session, user, q=q, location_id=location_id)
    ]


async def _ledger_rows(
    session: AsyncSession, user: Principal, entries: list[LedgerEntry]
) -> list[LedgerRow]:
    part_map = await parts.get_many(session, {e.part_id for e in entries})
    codes = await _location_codes(session, user)
    labels = await org.project_labels(session, {e.project_id for e in entries if e.project_id})
    names = await users.display_names(session, [e.user_id for e in entries])
    return [
        LedgerRow(
            id=e.id,
            created_at=e.created_at,
            part_id=e.part_id,
            mpn=part_map[e.part_id].mpn,
            location_code=codes.get(e.location_id, "?"),
            qty_delta=e.qty_delta,
            reason=e.reason,
            ref_type=e.ref_type,
            ref_id=e.ref_id,
            ref_label=None,
            lot_code=e.lot_code,
            project_code=labels[e.project_id][0] if e.project_id in labels else None,
            note=e.note,
            user_name=names.get(e.user_id) if e.user_id else None,
        )
        for e in entries
    ]


@router.get("/ledger", response_model=LedgerPage, summary="Inventory ledger (newest first)")
async def ledger(
    user: Reader,
    session: SessionDep,
    part_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    reason: Annotated[
        str | None, Query(pattern="^(GRN|ISSUE|RETURN|ADJUST|SCRAP|TRANSFER)$")
    ] = None,
    project_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LedgerPage:
    entries, total = await service.ledger_page(
        session,
        user,
        part_id=part_id,
        location_id=location_id,
        reason=reason,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    return LedgerPage(items=await _ledger_rows(session, user, entries), total=total)


@router.post("/transfers", response_model=list[LedgerRow], status_code=201, summary="Move stock")
async def transfer(data: TransferIn, user: Mover, session: SessionDep) -> list[LedgerRow]:
    pair = await service.user_transfer(
        session,
        user,
        part_id=data.part_id,
        from_location_id=data.from_location_id,
        to_location_id=data.to_location_id,
        qty=data.qty,
        lot_code=data.lot_code,
        note=data.note,
    )
    return await _ledger_rows(session, user, list(pair))


async def _adjustment_outs(
    session: AsyncSession, user: Principal, items: list[StockAdjustment]
) -> list[AdjustmentOut]:
    part_map = await parts.get_many(session, {a.part_id for a in items})
    codes = await _location_codes(session, user)
    names = await users.display_names(
        session, [a.requested_by for a in items] + [a.decided_by for a in items]
    )
    return [
        AdjustmentOut(
            id=a.id,
            part_id=a.part_id,
            mpn=part_map[a.part_id].mpn,
            location_id=a.location_id,
            location_code=codes.get(a.location_id, "?"),
            qty_delta=a.qty_delta,
            reason=a.reason,
            lot_code=a.lot_code,
            status=a.status,
            requested_by_name=names.get(a.requested_by) if a.requested_by else None,
            requested_at=a.created_at,
            decided_by_name=names.get(a.decided_by) if a.decided_by else None,
            decided_at=a.decided_at,
            decision_note=a.decision_note,
            row_version=a.row_version,
        )
        for a in items
    ]


@router.get("/adjustments", response_model=list[AdjustmentOut], summary="Stock adjustments")
async def adjustments(
    user: Reader,
    session: SessionDep,
    status: Annotated[str | None, Query(pattern="^(pending|approved|rejected)$")] = None,
) -> list[AdjustmentOut]:
    return await _adjustment_outs(
        session, user, await service.list_adjustments(session, user, status=status)
    )


@router.post(
    "/adjustments", response_model=AdjustmentOut, status_code=201, summary="Request an adjustment"
)
async def request_adjustment(
    data: AdjustmentIn, user: Adjuster, session: SessionDep
) -> AdjustmentOut:
    await parts.get(session, data.part_id)
    adj = await service.request_adjustment(
        session,
        user,
        part_id=data.part_id,
        location_id=data.location_id,
        qty_delta=data.qty_delta,
        reason=data.reason,
        lot_code=data.lot_code,
    )
    return (await _adjustment_outs(session, user, [adj]))[0]


@router.post(
    "/adjustments/{adjustment_id}/decision",
    response_model=AdjustmentOut,
    summary="Approve (posts to the ledger) or reject",
)
async def decide_adjustment(
    adjustment_id: uuid.UUID, data: AdjustmentDecision, user: Approver, session: SessionDep
) -> AdjustmentOut:
    adj = await service.decide_adjustment(
        session,
        user,
        adjustment_id,
        row_version=data.row_version,
        approve=data.approve,
        note=data.note,
    )
    return (await _adjustment_outs(session, user, [adj]))[0]


async def _reservation_outs(
    session: AsyncSession, user: Principal, items: list[StockReservation]
) -> list[ReservationOut]:
    part_map = await parts.get_many(session, {r.part_id for r in items})
    codes = await _location_codes(session, user)
    labels = await org.project_labels(session, {r.project_id for r in items})
    return [
        ReservationOut(
            id=r.id,
            part_id=r.part_id,
            mpn=part_map[r.part_id].mpn,
            project_id=r.project_id,
            project_code=labels.get(r.project_id, ("", ""))[0],
            location_code=codes.get(r.location_id) if r.location_id else None,
            qty=r.qty,
            status=r.status,
            note=r.note,
            created_at=r.created_at,
            row_version=r.row_version,
        )
        for r in items
    ]


@router.get("/reservations", response_model=list[ReservationOut], summary="Project reservations")
async def reservations(
    user: Reader,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    include_closed: bool = False,
) -> list[ReservationOut]:
    items = await service.list_reservations(
        session, user, project_id=project_id, include_closed=include_closed
    )
    return await _reservation_outs(session, user, items)


@router.post(
    "/reservations", response_model=ReservationOut, status_code=201, summary="Reserve for a project"
)
async def reserve(data: ReservationIn, user: Mover, session: SessionDep) -> ReservationOut:
    await parts.get(session, data.part_id)
    r = await service.user_reserve(
        session,
        user,
        part_id=data.part_id,
        project_id=data.project_id,
        qty=data.qty,
        location_id=data.location_id,
        note=data.note,
    )
    return (await _reservation_outs(session, user, [r]))[0]


@router.post(
    "/reservations/{reservation_id}/release", response_model=ReservationOut, summary="Release"
)
async def release(
    reservation_id: uuid.UUID, data: VersionIn, user: Mover, session: SessionDep
) -> ReservationOut:
    r = await service.release_reservation(session, user, reservation_id, data.row_version)
    return (await _reservation_outs(session, user, [r]))[0]
