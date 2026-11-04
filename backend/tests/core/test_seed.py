from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.inventory.models import InventoryLocation
from app.modules.org.models import Division, Module, PcbAssembly, Project
from app.modules.parts.models import Part, PartPreferredVendor
from app.modules.procurement.models import Vendor
from app.modules.production.models import StageTemplate, StageTemplateStep
from app.seed import seed_reference_data, seed_sample_data


async def _count(session: AsyncSession, model: type, **where: object) -> int:
    stmt = select(func.count()).select_from(model)
    for key, value in where.items():
        stmt = stmt.where(getattr(model, key) == value)
    return int((await session.execute(stmt)).scalar_one())


async def test_seed_creates_expected_counts_and_is_idempotent(db_session: AsyncSession) -> None:
    await seed_reference_data(db_session)
    created = await seed_sample_data(db_session)
    assert created > 0
    assert await _count(db_session, Division, is_sample=True) == 2
    assert await _count(db_session, Project, is_sample=True) == 3
    assert await _count(db_session, Module) == 4
    assert await _count(db_session, PcbAssembly) == 5
    assert await _count(db_session, Part, is_sample=True) == 60
    assert await _count(db_session, Vendor, is_sample=True) == 5
    assert await _count(db_session, PartPreferredVendor) == 60
    assert await _count(db_session, InventoryLocation) == 7
    assert await _count(db_session, StageTemplateStep) == 12
    assert await _count(db_session, StageTemplate, is_default=True) == 1

    vendors = (await db_session.execute(select(Vendor.name))).scalars().all()
    assert all("(Sample)" in name for name in vendors)
    codes = sorted((await db_session.execute(select(Project.code))).scalars().all())
    assert len(codes) == 3 and all(c.startswith("PRJ-") for c in codes)

    assert await seed_reference_data(db_session) == 0
    assert await seed_sample_data(db_session) == 0
    assert await _count(db_session, Part, is_sample=True) == 60


async def test_seed_is_audited(db_session: AsyncSession) -> None:
    await seed_reference_data(db_session)
    await seed_sample_data(db_session)
    assert await _count(db_session, AuditLog, entity_type="parts", action="insert") == 60
