import random
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.inventory.models import LedgerEntry, LedgerReason, StockBalance
from app.modules.inventory.service import (
    InsufficientStockError,
    post_movement,
    stock_on_hand,
    transfer,
    verify_balances,
)
from tests.factories import LocationFactory, PartFactory, create


async def _balance(session: AsyncSession, part_id, location_id) -> Decimal:
    value = (
        await session.execute(
            select(StockBalance.qty_on_hand).where(
                StockBalance.part_id == part_id, StockBalance.location_id == location_id
            )
        )
    ).scalar_one_or_none()
    return Decimal(value or 0)


async def _ledger_sum(session: AsyncSession, part_id, location_id) -> Decimal:
    return Decimal(
        (
            await session.execute(
                select(func.coalesce(func.sum(LedgerEntry.qty_delta), 0)).where(
                    LedgerEntry.part_id == part_id, LedgerEntry.location_id == location_id
                )
            )
        ).scalar_one()
    )


async def test_fifty_random_deltas_balance_equals_ledger_sum_every_time(
    db_session: AsyncSession,
) -> None:
    rng = random.Random(20261104)
    parts = [await create(db_session, PartFactory) for _ in range(3)]
    locations = [await create(db_session, LocationFactory) for _ in range(2)]
    accepted = rejected = 0
    for _ in range(50):
        part, loc = rng.choice(parts), rng.choice(locations)
        reason = rng.choice(list(LedgerReason))
        magnitude = Decimal(rng.randint(1, 400)) / Decimal(4)  # quarter units, e.g. metres of wire
        if reason in (LedgerReason.GRN, LedgerReason.RETURN):
            delta = magnitude
        elif reason in (LedgerReason.ISSUE, LedgerReason.SCRAP):
            delta = -magnitude
        else:
            delta = magnitude if rng.random() < 0.5 else -magnitude
        try:
            await post_movement(
                db_session, part_id=part.id, location_id=loc.id, qty_delta=delta, reason=reason
            )
            accepted += 1
        except InsufficientStockError:
            rejected += 1
        for p in parts:
            for location in locations:
                assert await _balance(db_session, p.id, location.id) == await _ledger_sum(
                    db_session, p.id, location.id
                )
                assert await _balance(db_session, p.id, location.id) >= 0
    assert accepted + rejected == 50
    assert accepted > 25  # the random walk mostly succeeds
    assert await verify_balances(db_session) == []


async def test_issue_beyond_stock_is_rejected_and_nothing_is_written(
    db_session: AsyncSession,
) -> None:
    part = await create(db_session, PartFactory)
    loc = await create(db_session, LocationFactory)
    await post_movement(
        db_session, part_id=part.id, location_id=loc.id, qty_delta=10, reason=LedgerReason.GRN
    )
    with pytest.raises(InsufficientStockError) as exc:
        await post_movement(
            db_session,
            part_id=part.id,
            location_id=loc.id,
            qty_delta=-11,
            reason=LedgerReason.ISSUE,
        )
    assert exc.value.status_code == 409
    assert await stock_on_hand(db_session, part.id) == 10
    count = (
        await db_session.execute(select(func.count()).where(LedgerEntry.part_id == part.id))
    ).scalar_one()
    assert count == 1


@pytest.mark.parametrize(
    ("reason", "qty", "code"),
    [
        (LedgerReason.GRN, -1, "invalid_movement_sign"),
        (LedgerReason.RETURN, -1, "invalid_movement_sign"),
        (LedgerReason.ISSUE, 1, "invalid_movement_sign"),
        (LedgerReason.SCRAP, 1, "invalid_movement_sign"),
        (LedgerReason.ADJUST, 0, "zero_quantity"),
    ],
)
async def test_movement_sign_rules(
    db_session: AsyncSession, reason: LedgerReason, qty: int, code: str
) -> None:
    part = await create(db_session, PartFactory)
    loc = await create(db_session, LocationFactory)
    with pytest.raises(AppError) as exc:
        await post_movement(
            db_session, part_id=part.id, location_id=loc.id, qty_delta=qty, reason=reason
        )
    assert exc.value.code == code


async def test_transfer_moves_stock_between_locations(db_session: AsyncSession) -> None:
    part = await create(db_session, PartFactory)
    stores, wip = (
        await create(db_session, LocationFactory),
        await create(db_session, LocationFactory),
    )
    await post_movement(
        db_session,
        part_id=part.id,
        location_id=stores.id,
        qty_delta=100,
        reason=LedgerReason.GRN,
        lot_code="L1",
    )
    await transfer(
        db_session,
        part_id=part.id,
        from_location_id=stores.id,
        to_location_id=wip.id,
        qty=30,
        lot_code="L1",
    )
    assert await stock_on_hand(db_session, part.id, stores.id) == 70
    assert await stock_on_hand(db_session, part.id, wip.id) == 30
    assert await stock_on_hand(db_session, part.id) == 100
    with pytest.raises(AppError):
        await transfer(
            db_session, part_id=part.id, from_location_id=wip.id, to_location_id=wip.id, qty=1
        )
    with pytest.raises(InsufficientStockError):
        await transfer(
            db_session, part_id=part.id, from_location_id=wip.id, to_location_id=stores.id, qty=31
        )


async def test_ledger_is_append_only(db_session: AsyncSession) -> None:
    part = await create(db_session, PartFactory)
    loc = await create(db_session, LocationFactory)
    entry = await post_movement(
        db_session, part_id=part.id, location_id=loc.id, qty_delta=5, reason=LedgerReason.GRN
    )
    for sql in (
        "UPDATE inventory_ledger SET qty_delta = 500 WHERE id = :id",
        "DELETE FROM inventory_ledger WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(sql), {"id": entry.id})


async def test_verify_balances_detects_tampering(db_session: AsyncSession) -> None:
    part = await create(db_session, PartFactory)
    loc = await create(db_session, LocationFactory)
    await post_movement(
        db_session, part_id=part.id, location_id=loc.id, qty_delta=5, reason=LedgerReason.GRN
    )
    await db_session.execute(
        text("UPDATE stock_balances SET qty_on_hand = 7 WHERE part_id = :p"), {"p": part.id}
    )
    [mismatch] = await verify_balances(db_session)
    assert mismatch.part_id == part.id
    assert mismatch.ledger_sum == 5
    assert mismatch.balance == 7
