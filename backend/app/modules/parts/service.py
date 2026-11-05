"""Part master: search (MPN autocomplete) and inline creation."""

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.ids import uuid7
from app.core.repository import check_version
from app.modules.auth.service import Principal
from app.modules.boq.importer import norm_mpn
from app.modules.parts.models import Part, PartPreferredVendor
from app.modules.parts.schemas import PartCreate, PartStockSettings


def _norm_sql(column: Any) -> Any:
    return func.upper(func.regexp_replace(column, r"[\s\-_./]+", "", "g"))


async def search(session: AsyncSession, user: Principal, q: str, limit: int = 20) -> list[Part]:
    if not user.can("boq:read"):
        user.require("parts:read")
    stmt = select(Part).where(Part.is_deleted.is_(False))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                _norm_sql(Part.mpn).like(f"%{norm_mpn(q)}%"),
                Part.description.ilike(like),
                Part.manufacturer.ilike(like),
            )
        )
    key = norm_mpn(q)
    if key:
        # Exact MPN first, then MPNs starting with the query, then the rest.
        norm = _norm_sql(Part.mpn)
        stmt = stmt.order_by((norm == key).desc(), norm.like(f"{key}%").desc(), Part.mpn)
    else:
        stmt = stmt.order_by(Part.mpn)
    stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars())


async def by_normalised_mpn(session: AsyncSession, mpns: list[str]) -> dict[str, Part]:
    """Normalised MPN -> part, for linking BOQ lines and import warnings."""
    keys = {norm_mpn(m) for m in mpns if m}
    if not keys:
        return {}
    rows = (
        await session.execute(
            select(Part).where(Part.is_deleted.is_(False), _norm_sql(Part.mpn).in_(keys))
        )
    ).scalars()
    return {norm_mpn(p.mpn): p for p in rows}


async def get(session: AsyncSession, part_id: uuid.UUID) -> Part:
    part = await session.get(Part, part_id)
    if part is None or part.is_deleted:
        raise NotFoundError("Part not found", details={"id": str(part_id)})
    return part


async def create(
    session: AsyncSession, user: Principal, data: PartCreate, *, commit: bool = True
) -> Part:
    user.require("parts:manage")
    existing = await by_normalised_mpn(session, [data.mpn])
    found = existing.get(norm_mpn(data.mpn))
    if (
        found is not None
        and (found.manufacturer or "").upper() == (data.manufacturer or "").upper()
    ):
        raise ConflictError(
            f"{found.mpn} already exists in the part master",
            code="duplicate",
            details={"id": str(found.id)},
        )
    part = Part(**data.model_dump())
    session.add(part)
    await session.flush()
    if commit:
        await session.commit()
    return part


async def create_for_import(session: AsyncSession, specs: list[dict[str, Any]]) -> list[Part]:
    """Parts created while committing a BOQ import (caller holds boq:import).

    One flush for the whole batch: a 2,000-line client BOQ can bring hundreds of new parts.
    Each spec has mpn, manufacturer, description, package, value, category and unit.
    """
    created = [
        Part(
            id=uuid7(),
            mpn=spec["mpn"],
            manufacturer=spec["manufacturer"],
            description=(spec["description"] or spec["mpn"])[:300],
            package=spec["package"],
            value=spec["value"],
            category=spec["category"] or "Other",
            unit=spec["unit"],
            notes="Created by BOQ import",
        )
        for spec in specs
    ]
    session.add_all(created)
    if created:
        await session.flush()
    return created


async def get_many(session: AsyncSession, part_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Part]:
    wanted = set(part_ids)
    if not wanted:
        return {}
    rows = await session.execute(select(Part).where(Part.id.in_(wanted)))
    return {p.id: p for p in rows.scalars()}


async def preferred_vendors(
    session: AsyncSession, part_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Part id -> its first-ranked preferred vendor."""
    wanted = set(part_ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(PartPreferredVendor.part_id, PartPreferredVendor.vendor_id)
        .where(PartPreferredVendor.part_id.in_(wanted), PartPreferredVendor.is_deleted.is_(False))
        .order_by(PartPreferredVendor.rank.desc())
    )
    return {part_id: vendor_id for part_id, vendor_id in rows.all()}  # rank 1 wins (last)


async def update_stock_settings(
    session: AsyncSession, user: Principal, part_id: uuid.UUID, data: PartStockSettings
) -> Part:
    user.require("parts:manage")
    part = await get(session, part_id)
    check_version(part, data.row_version)
    part.min_stock = data.min_stock
    part.msl_level = data.msl_level
    await session.flush()
    await session.commit()
    return part
