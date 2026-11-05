"""Two people receive the same PO line at the same moment: they must not be able to receive
more than is outstanding between them. Runs on real, separately committed connections (not
the per-test rollback transaction), because only those can actually race."""

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.errors import ConflictError
from app.modules.auth.models import User
from app.modules.auth.service import load_principal
from app.modules.inventory import service as inventory
from app.modules.inventory.models import InventoryLocation
from app.modules.procurement import service
from app.modules.procurement.models import GrnLine, PoLine, PurchaseOrder
from app.modules.procurement.schemas import GrnCreate, GrnLineIn
from app.seed import seed_reference_data
from tests.factories import PartFactory, VendorFactory, make_user, uniq


async def test_concurrent_receipts_cannot_over_receive(
    engine: AsyncEngine, test_database_url: str
) -> None:
    del engine  # requested so the throwaway test database exists and is migrated
    racers = create_async_engine(test_database_url, pool_size=10, max_overflow=0)
    maker = async_sessionmaker(racers, expire_on_commit=False)
    try:
        async with maker() as s:
            await seed_reference_data(s)
            part = PartFactory.build(mpn=uniq("RACE"))
            vendor = VendorFactory.build()
            s.add_all([part, vendor])
            await s.flush()
            po = PurchaseOrder(number=uniq("PO-RACE"), vendor_id=vendor.id, status="issued")
            s.add(po)
            await s.flush()
            line = PoLine(
                purchase_order_id=po.id, line_no=1, part_id=part.id, qty_ordered=Decimal(10)
            )
            s.add(line)
            store = (
                await s.execute(select(InventoryLocation).where(InventoryLocation.code == "STORES"))
            ).scalar_one()
            user = await make_user(s, uniq("racer").replace("-", "_"), roles=("stores",))
            await s.commit()

        async def receive(qty: int) -> str:
            async with maker() as session:
                u = await session.get(User, user.id)
                assert u is not None
                principal = await load_principal(session, u)
                data = GrnCreate(
                    purchase_order_id=po.id,
                    lines=[
                        GrnLineIn(
                            po_line_id=line.id,
                            location_id=store.id,
                            qty_received=Decimal(qty),
                            qty_accepted=Decimal(qty),
                        )
                    ],
                )
                try:
                    grn = await service.receive(session, principal, data)
                    return grn.number
                except ConflictError as exc:
                    await session.rollback()
                    return exc.code

        # Eight clerks each try to book 4 of the 10 outstanding at the same moment.
        results = await asyncio.gather(*(receive(4) for _ in range(8)))
        posted = [r for r in results if r.startswith("GRN")]
        refused = [r for r in results if r == "over_receipt"]
        assert len(posted) == 2 and len(refused) == 6, results

        async with maker() as s:
            total = sum(
                (
                    gl.qty_accepted
                    for gl in (
                        await s.execute(select(GrnLine).where(GrnLine.po_line_id == line.id))
                    ).scalars()
                ),
                Decimal(0),
            )
            assert total == 8
            assert await inventory.stock_on_hand(s, part.id) == 8
            assert await inventory.verify_balances(s) == []
            refreshed = await s.get(PurchaseOrder, po.id)
            assert refreshed is not None and refreshed.status == "partially_received"
    finally:
        await racers.dispose()
