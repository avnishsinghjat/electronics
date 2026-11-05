"""BOQ service. Phase 4 provides the deep copy used when cloning a project; the BOQ
editor, import wizard and revision workflow arrive in Phase 5."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boq.models import Boq, BoqLine, BoqRevision, RevisionStatus

_LINE_FIELDS = (
    "line_key",
    "line_no",
    "part_id",
    "ref_des",
    "qty_per_unit",
    "mpn",
    "manufacturer",
    "description",
    "value",
    "package",
    "category",
    "unit",
    "dnp",
    "attrition_pct",
    "unit_price",
    "preferred_vendor_id",
    "notes",
)


def _rev_order(rev: str) -> tuple[int, str]:
    return (len(rev), rev)  # A < B < ... < Z < AA


async def current_revision(session: AsyncSession, boq_id: uuid.UUID) -> BoqRevision | None:
    """The released revision, else the latest one."""
    revisions = (
        (
            await session.execute(
                select(BoqRevision).where(
                    BoqRevision.boq_id == boq_id, BoqRevision.is_deleted.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    if not revisions:
        return None
    released = [r for r in revisions if r.status == RevisionStatus.RELEASED.value]
    if released:
        return released[0]
    return max(revisions, key=lambda r: _rev_order(r.revision))


async def copy_boqs_for_clone(
    session: AsyncSession,
    source_project_id: uuid.UUID,
    target_project_id: uuid.UUID,
    module_map: dict[uuid.UUID, uuid.UUID],
    assembly_map: dict[uuid.UUID, uuid.UUID],
) -> int:
    """Copies each BOQ's current revision into the cloned project as a new draft
    revision A. Line keys are preserved so later revisions diff cleanly against the
    original. Returns the number of BOQs copied."""
    boqs = (
        (
            await session.execute(
                select(Boq).where(Boq.project_id == source_project_id, Boq.is_deleted.is_(False))
            )
        )
        .scalars()
        .all()
    )
    copied = 0
    for boq in boqs:
        revision = await current_revision(session, boq.id)
        if revision is None:
            continue
        new_boq = Boq(
            project_id=target_project_id,
            module_id=module_map.get(boq.module_id) if boq.module_id else None,
            assembly_id=assembly_map.get(boq.assembly_id) if boq.assembly_id else None,
            name=boq.name,
            notes=boq.notes,
        )
        session.add(new_boq)
        await session.flush()
        new_rev = BoqRevision(
            boq_id=new_boq.id,
            revision="A",
            status=RevisionStatus.DRAFT.value,
            build_qty=revision.build_qty,
            notes=f"Copied from revision {revision.revision} of the source project.",
        )
        session.add(new_rev)
        await session.flush()
        lines = (
            (
                await session.execute(
                    select(BoqLine).where(
                        BoqLine.revision_id == revision.id, BoqLine.is_deleted.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        for line in lines:
            session.add(
                BoqLine(revision_id=new_rev.id, **{f: getattr(line, f) for f in _LINE_FIELDS})
            )
        await session.flush()
        copied += 1
    return copied
