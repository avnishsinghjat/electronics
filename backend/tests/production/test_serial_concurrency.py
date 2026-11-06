"""Serial numbers stay unique and gap-free when several work orders of the same assembly
generate them at the same moment (real, separately committed connections)."""

import asyncio
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.modules.auth.models import User
from app.modules.auth.service import load_principal
from app.modules.org.models import BuildLot, SerialUnit
from app.modules.production import service
from app.modules.production.models import WorkOrder
from app.seed import seed_reference_data
from tests.factories import (
    AssemblyFactory,
    DivisionFactory,
    ModuleFactory,
    ProjectFactory,
    make_user,
    uniq,
)


async def test_concurrent_serial_generation_is_unique_and_gap_free(
    engine: AsyncEngine, test_database_url: str
) -> None:
    del engine  # requested so the throwaway test database exists and is migrated
    racers = create_async_engine(test_database_url, pool_size=10, max_overflow=0)
    maker = async_sessionmaker(racers, expire_on_commit=False)
    try:
        async with maker() as s:
            await seed_reference_data(s)
            division = DivisionFactory.build()
            s.add(division)
            await s.flush()
            project = ProjectFactory.build(division_id=division.id)
            s.add(project)
            await s.flush()
            module = ModuleFactory.build(project_id=project.id)
            s.add(module)
            await s.flush()
            assembly = AssemblyFactory.build(module_id=module.id, code=uniq("race").upper())
            s.add(assembly)
            await s.flush()
            orders = []
            for _ in range(8):
                wo = WorkOrder(
                    number=uniq("WO-RACE"),
                    project_id=project.id,
                    module_id=module.id,
                    assembly_id=assembly.id,
                    build_qty=5,
                    status="released",
                    track_serials=True,
                )
                s.add(wo)
                await s.flush()
                s.add(
                    BuildLot(
                        assembly_id=assembly.id,
                        work_order_id=wo.id,
                        lot_number=uniq("LOT-RACE"),
                        qty=5,
                    )
                )
                orders.append(wo)
            user = await make_user(s, uniq("planner").replace("-", "_"), roles=("project_manager",))
            await s.commit()

        async def generate(wo_id: object) -> list[str]:
            async with maker() as session:
                u = await session.get(User, user.id)
                assert u is not None
                principal = await load_principal(session, u)
                units = await service.generate_serials(session, principal, wo_id, None)  # type: ignore[arg-type]
                return [x.serial_number for x in units]

        results = await asyncio.gather(*(generate(wo.id) for wo in orders))
        serials = [sn for batch in results for sn in batch]
        assert len(serials) == 40 and len(set(serials)) == 40
        pattern = re.compile(r"^[A-Z0-9]+-[A-Z0-9]+-\d{4}-(\d{5})$")
        numbers = sorted(int(m.group(1)) for sn in serials if (m := pattern.match(sn)))
        assert numbers == list(range(1, 41))
        for batch in results:  # each order got a consecutive block
            ns = [int(sn[-5:]) for sn in batch]
            assert ns == list(range(ns[0], ns[0] + 5))
        async with maker() as s:
            stored = (
                (
                    await s.execute(
                        select(SerialUnit.serial_number).where(
                            SerialUnit.assembly_id == assembly.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(stored) == sorted(serials)
    finally:
        await racers.dispose()
