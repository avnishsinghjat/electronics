"""Production: stage templates, work orders (release gate), kitting, serialisation and stage
progress per lot and per serial, with QC gating enforced here.

Rules (tested in tests/production):
- Release needs the module to be clear to build (the tracker's rule), or a PM override with
  a reason, written to the audit log as a release_override event.
- Kitting issues stock against the work order's BOQ lines through the inventory ledger
  (ISSUE / RETURN, ref boq_line), so "Issued" reaches the tracker. Each issue records the
  part lot (genealogy) and uses up the project's reservations. A line cannot be issued
  beyond what this order needs.
- A stage can start for a lot or serial only after the previous stage is completed (and,
  for a serial, passed). A stage that requires QC cannot be completed until a passed QC
  inspection covers it.
- Serial numbers: {prefix}-{assembly code}-{year}-{5-digit running number}, the running
  number taken under a row lock per assembly and year.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, record_event
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.models import utcnow
from app.core.numbering import next_number
from app.core.repository import check_version
from app.modules.auth.service import Principal
from app.modules.boq import service as boq
from app.modules.boq.models import Boq, BoqLine
from app.modules.boq.status import required_qty
from app.modules.inventory import service as inventory
from app.modules.org import service as org
from app.modules.org.models import (
    BuildLot,
    LotStatus,
    Module,
    PcbAssembly,
    Project,
    SerialUnit,
    UnitStatus,
)
from app.modules.parts import service as parts
from app.modules.procurement import tracker
from app.modules.production.models import (
    KitIssue,
    KitKind,
    SerialSequence,
    StageProgress,
    StageStatus,
    StageTemplate,
    StageTemplateStep,
    WorkOrder,
    WorkOrderStage,
    WoStatus,
)
from app.modules.production.schemas import TemplateCreate, TemplateUpdate, WoCreate, WoUpdate
from app.modules.qc import service as qc
from app.modules.settings.models import CompanySettings

ZERO = Decimal(0)
_ACTIVE = (WoStatus.RELEASED.value, WoStatus.IN_PROGRESS.value)


# ---------------------------------------------------------------- stage templates


async def _template(session: AsyncSession, template_id: uuid.UUID) -> StageTemplate:
    t = await session.get(StageTemplate, template_id)
    if t is None or t.is_deleted:
        raise NotFoundError("Stage template not found", details={"id": str(template_id)})
    return t


async def template_steps(session: AsyncSession, template_id: uuid.UUID) -> list[StageTemplateStep]:
    rows = await session.execute(
        select(StageTemplateStep)
        .where(
            StageTemplateStep.template_id == template_id, StageTemplateStep.is_deleted.is_(False)
        )
        .order_by(StageTemplateStep.seq)
    )
    return list(rows.scalars().all())


async def template_usage(session: AsyncSession) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(PcbAssembly.stage_template_id, func.count())
        .where(PcbAssembly.is_deleted.is_(False), PcbAssembly.stage_template_id.is_not(None))
        .group_by(PcbAssembly.stage_template_id)
    )
    return {tid: int(n) for tid, n in rows.all() if tid is not None}


async def list_templates(session: AsyncSession, user: Principal) -> list[StageTemplate]:
    user.require("production:read")
    rows = await session.execute(
        select(StageTemplate)
        .where(StageTemplate.is_deleted.is_(False))
        .order_by(StageTemplate.is_default.desc(), StageTemplate.name)
    )
    return list(rows.scalars().all())


async def get_template(
    session: AsyncSession, user: Principal, template_id: uuid.UUID
) -> StageTemplate:
    user.require("production:read")
    return await _template(session, template_id)


async def _name_taken(session: AsyncSession, name: str, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(StageTemplate.id).where(
        func.lower(StageTemplate.name) == name.strip().lower(), StageTemplate.is_deleted.is_(False)
    )
    if exclude:
        stmt = stmt.where(StageTemplate.id != exclude)
    return (await session.execute(stmt)).first() is not None


async def create_template(
    session: AsyncSession, user: Principal, data: TemplateCreate
) -> StageTemplate:
    """A new template, copied from another (default: the default template)."""
    user.require("wo:manage")
    if await _name_taken(session, data.name):
        raise ConflictError(f"A template named {data.name} exists", code="duplicate_name")
    source_id = data.copy_from_id
    if source_id is None:
        source_id = (
            await session.execute(
                select(StageTemplate.id).where(
                    StageTemplate.is_default.is_(True), StageTemplate.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
    t = StageTemplate(name=data.name.strip(), description=data.description)
    session.add(t)
    await session.flush()
    if source_id is not None:
        await _template(session, source_id)
        for step in await template_steps(session, source_id):
            session.add(
                StageTemplateStep(
                    template_id=t.id,
                    seq=step.seq,
                    stage_code=step.stage_code,
                    name=step.name,
                    requires_qc=step.requires_qc,
                )
            )
    await session.flush()
    await session.commit()
    return t


async def update_template(
    session: AsyncSession, user: Principal, template_id: uuid.UUID, data: TemplateUpdate
) -> StageTemplate:
    """Rename and replace the step list (order = list order). Work orders already created
    keep their own copy of the stages."""
    user.require("wo:manage")
    t = await _template(session, template_id)
    check_version(t, data.row_version)
    if await _name_taken(session, data.name, exclude=t.id):
        raise ConflictError(f"A template named {data.name} exists", code="duplicate_name")
    for step in await template_steps(session, t.id):
        await session.delete(step)
    await session.flush()
    for seq, step_in in enumerate(data.steps, start=1):
        session.add(
            StageTemplateStep(
                template_id=t.id,
                seq=seq,
                stage_code=step_in.stage_code.value,
                name=step_in.name.strip(),
                requires_qc=step_in.requires_qc,
            )
        )
    t.name = data.name.strip()
    t.description = data.description
    t.updated_at = utcnow()
    await session.flush()
    await session.commit()
    return t


async def delete_template(
    session: AsyncSession, user: Principal, template_id: uuid.UUID, row_version: int
) -> None:
    user.require("wo:manage")
    t = await _template(session, template_id)
    check_version(t, row_version)
    if t.is_default:
        raise ConflictError("The default template cannot be deleted", code="template_is_default")
    used = (await template_usage(session)).get(t.id, 0)
    if used:
        raise ConflictError(
            f"{used} assembl{'y uses' if used == 1 else 'ies use'} this template",
            code="template_in_use",
        )
    t.is_deleted = True
    await session.flush()
    await session.commit()


# ---------------------------------------------------------------- work orders


async def _wo(
    session: AsyncSession, user: Principal, wo_id: uuid.UUID, *, lock: bool = False
) -> WorkOrder:
    user.require("production:read")
    stmt = select(WorkOrder).where(WorkOrder.id == wo_id, WorkOrder.is_deleted.is_(False))
    if lock:
        stmt = stmt.with_for_update()
    wo = (await session.execute(stmt)).scalar_one_or_none()
    if wo is None:
        raise NotFoundError("Work order not found", details={"id": str(wo_id)})
    try:
        await org.get_project(session, user, wo.project_id)
    except NotFoundError as exc:
        raise NotFoundError("Work order not found", details={"id": str(wo_id)}) from exc
    if lock:
        await session.refresh(wo)
    return wo


async def get_wo(session: AsyncSession, user: Principal, wo_id: uuid.UUID) -> WorkOrder:
    return await _wo(session, user, wo_id)


async def lot_of(session: AsyncSession, wo_id: uuid.UUID) -> BuildLot | None:
    return (
        await session.execute(
            select(BuildLot).where(BuildLot.work_order_id == wo_id, BuildLot.is_deleted.is_(False))
        )
    ).scalar_one_or_none()


async def stages_of(session: AsyncSession, wo_id: uuid.UUID) -> list[WorkOrderStage]:
    rows = await session.execute(
        select(WorkOrderStage)
        .where(WorkOrderStage.work_order_id == wo_id, WorkOrderStage.is_deleted.is_(False))
        .order_by(WorkOrderStage.seq)
    )
    return list(rows.scalars().all())


async def _pick_boq(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, assembly: PcbAssembly
) -> uuid.UUID | None:
    """The BOQ for this board: one made for the assembly, else the module's own BOQ."""
    views = await boq.list_project_boqs(session, user, project_id)
    for v in views:
        if v.boq.assembly_id == assembly.id:
            return v.boq.id
    for v in views:
        if v.boq.module_id == assembly.module_id and v.boq.assembly_id is None:
            return v.boq.id
    return None


async def _check_boq(session: AsyncSession, project_id: uuid.UUID, boq_id: uuid.UUID) -> None:
    b = await session.get(Boq, boq_id)
    if b is None or b.is_deleted or b.project_id != project_id:
        raise AppError(
            "The BOQ must belong to the work order's project", code="wrong_boq", status_code=422
        )


async def create_wo(session: AsyncSession, user: Principal, data: WoCreate) -> WorkOrder:
    user.require("wo:manage")
    assembly = await org.get_assembly(session, user, data.assembly_id)
    module = await session.get(Module, assembly.module_id)
    assert module is not None
    if data.boq_id:
        await _check_boq(session, module.project_id, data.boq_id)
    template_id = (
        assembly.stage_template_id
        or (
            await session.execute(
                select(StageTemplate.id).where(
                    StageTemplate.is_default.is_(True), StageTemplate.is_deleted.is_(False)
                )
            )
        ).scalar_one_or_none()
    )
    steps = await template_steps(session, template_id) if template_id else []
    if not steps:
        raise ConflictError(
            "The assembly has no production stages: give it a stage template first",
            code="no_stages",
        )
    wo = WorkOrder(
        number=await next_number(session, "WO"),
        project_id=module.project_id,
        module_id=module.id,
        assembly_id=assembly.id,
        boq_id=data.boq_id or await _pick_boq(session, user, module.project_id, assembly),
        build_qty=data.build_qty,
        planned_start=data.planned_start,
        planned_end=data.planned_end,
        track_serials=data.track_serials,
        notes=data.notes,
    )
    session.add(wo)
    await session.flush()
    for step in steps:
        session.add(
            WorkOrderStage(
                work_order_id=wo.id,
                seq=step.seq,
                stage_code=step.stage_code,
                name=step.name,
                requires_qc=step.requires_qc,
            )
        )
    session.add(
        BuildLot(
            assembly_id=assembly.id,
            work_order_id=wo.id,
            lot_number=await next_number(session, "LOT"),
            qty=data.build_qty,
        )
    )
    await session.flush()
    await session.commit()
    return wo


async def update_wo(
    session: AsyncSession, user: Principal, wo_id: uuid.UUID, data: WoUpdate
) -> WorkOrder:
    user.require("wo:manage")
    wo = await _wo(session, user, wo_id)
    check_version(wo, data.row_version)
    if wo.status != WoStatus.DRAFT.value:
        raise ConflictError(
            "Only a draft work order can be edited", code="invalid_status_transition"
        )
    if data.boq_id:
        await _check_boq(session, wo.project_id, data.boq_id)
    wo.build_qty = data.build_qty
    wo.planned_start = data.planned_start
    wo.planned_end = data.planned_end
    wo.track_serials = data.track_serials
    wo.boq_id = data.boq_id
    wo.notes = data.notes
    lot = await lot_of(session, wo.id)
    if lot is not None:
        lot.qty = data.build_qty
    await session.flush()
    await session.commit()
    return wo


@dataclass
class ReadinessView:
    clear_to_build: bool
    reason: str | None
    lines: int
    lines_received: int


async def readiness(session: AsyncSession, user: Principal, wo: WorkOrder) -> ReadinessView:
    """Clear to build for the order's module, exactly as the tracker shows it."""
    t = await tracker.project_tracker(session, user, wo.project_id)
    for m in t["modules"]:
        if m["module_id"] == wo.module_id:
            return ReadinessView(m["clear_to_build"], m["reason"], m["lines"], m["lines_received"])
    return ReadinessView(False, "No BOQ", 0, 0)


async def release_wo(
    session: AsyncSession,
    user: Principal,
    wo_id: uuid.UUID,
    row_version: int,
    override_reason: str | None,
) -> WorkOrder:
    user.require("wo:release")
    wo = await _wo(session, user, wo_id, lock=True)
    check_version(wo, row_version)
    if wo.status != WoStatus.DRAFT.value:
        raise ConflictError(f"{wo.number} is already {wo.status}", code="invalid_status_transition")
    ready = await readiness(session, user, wo)
    reason = (override_reason or "").strip()
    if not ready.clear_to_build:
        if not reason:
            raise ConflictError(
                f"Not clear to build: {ready.reason}. A project manager can release with a reason.",
                code="not_clear_to_build",
                details={
                    "reason": ready.reason,
                    "lines": ready.lines,
                    "lines_received": ready.lines_received,
                },
            )
        user.require("wo:override_release")
        wo.release_override_reason = reason
        await record_event(
            session,
            AuditAction.RELEASE_OVERRIDE,
            entity_type="work_orders",
            entity_id=str(wo.id),
            actor_id=user.id,
            details={"number": wo.number, "reason": reason, "readiness": ready.reason},
        )
    wo.status = WoStatus.RELEASED.value
    wo.released_at = utcnow()
    await session.flush()
    await session.commit()
    return wo


async def cancel_wo(
    session: AsyncSession, user: Principal, wo_id: uuid.UUID, row_version: int
) -> WorkOrder:
    user.require("wo:manage")
    wo = await _wo(session, user, wo_id, lock=True)
    check_version(wo, row_version)
    if wo.status not in (WoStatus.DRAFT.value, WoStatus.RELEASED.value):
        raise ConflictError(
            f"{wo.number} is {wo.status.replace('_', ' ')} and cannot be cancelled",
            code="invalid_status_transition",
        )
    if any(q > 0 for q in (await net_issued(session, wo.id)).values()):
        raise ConflictError("Return the kitted parts to stores first", code="kit_not_returned")
    wo.status = WoStatus.CANCELLED.value
    lot = await lot_of(session, wo.id)
    if lot is not None:
        lot.status = LotStatus.SCRAPPED.value
    await session.flush()
    await session.commit()
    return wo


async def close_wo(
    session: AsyncSession, user: Principal, wo_id: uuid.UUID, row_version: int
) -> WorkOrder:
    user.require("wo:manage")
    wo = await _wo(session, user, wo_id)
    check_version(wo, row_version)
    if wo.status != WoStatus.COMPLETED.value:
        raise ConflictError(
            "Only a completed work order can be closed", code="invalid_status_transition"
        )
    wo.status = WoStatus.CLOSED.value
    await session.flush()
    await session.commit()
    return wo


async def list_wos(
    session: AsyncSession,
    user: Principal,
    *,
    project_id: uuid.UUID | None = None,
    status: list[str] | None = None,
) -> list[WorkOrder]:
    user.require("production:read")
    stmt = (
        select(WorkOrder)
        .where(WorkOrder.is_deleted.is_(False))
        .order_by(WorkOrder.created_at.desc())
    )
    scope = await org.scoped_project_ids(session, user)
    if scope is not None:
        stmt = stmt.where(WorkOrder.project_id.in_(scope))
    if project_id:
        stmt = stmt.where(WorkOrder.project_id == project_id)
    if status:
        stmt = stmt.where(WorkOrder.status.in_(status))
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------- kitting


@dataclass
class KitLineView:
    line: BoqLine
    group: list[uuid.UUID]
    required: Decimal
    issued: Decimal
    available: Decimal
    reserved_for_project: Decimal

    @property
    def shortage(self) -> Decimal:
        return max(self.required - self.issued, ZERO)


async def net_issued(
    session: AsyncSession, wo_id: uuid.UUID
) -> dict[tuple[uuid.UUID, str | None], Decimal]:
    """(BOQ line id, lot) -> quantity issued to this order minus returned."""
    rows = await session.execute(
        select(KitIssue.boq_line_id, KitIssue.lot_code, KitIssue.kind, func.sum(KitIssue.qty))
        .where(KitIssue.work_order_id == wo_id, KitIssue.is_deleted.is_(False))
        .group_by(KitIssue.boq_line_id, KitIssue.lot_code, KitIssue.kind)
    )
    out: dict[tuple[uuid.UUID, str | None], Decimal] = defaultdict(lambda: ZERO)
    for line_id, lot, kind, qty in rows.all():
        out[(line_id, lot)] += Decimal(qty) if kind == KitKind.ISSUE.value else -Decimal(qty)
    return dict(out)


async def kit_lines(
    session: AsyncSession, user: Principal, wo: WorkOrder
) -> tuple[boq.TrackedBoq | None, list[KitLineView]]:
    if wo.boq_id is None:
        return None, []
    tracked = next(
        (
            tb
            for tb in await boq.project_lines(session, user, wo.project_id)
            if tb.view.boq.id == wo.boq_id
        ),
        None,
    )
    if tracked is None or tracked.revision is None:
        return tracked, []
    issued_by: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    for (line_id, _lot), q in (await net_issued(session, wo.id)).items():
        issued_by[line_id] += q
    out = []
    for tl in tracked.lines:
        ln = tl.line
        req = required_qty(
            ln.qty_per_unit, wo.build_qty, ln.attrition_pct, unit=ln.unit, dnp=ln.dnp
        )
        stock = (
            await inventory.part_stock_for(session, ln.part_id) if ln.part_id else {"usable": ZERO}
        )
        reserved = (
            await inventory.project_reserved(session, ln.part_id, wo.project_id)
            if ln.part_id
            else ZERO
        )
        out.append(
            KitLineView(
                line=ln,
                group=tl.group,
                required=req,
                issued=sum((issued_by[i] for i in tl.group), ZERO),
                available=stock["usable"],
                reserved_for_project=reserved,
            )
        )
    return tracked, out


async def issue_kit(
    session: AsyncSession,
    user: Principal,
    wo_id: uuid.UUID,
    issues: list[dict[str, Any]],
) -> list[KitIssue]:
    """Issue parts to the order. All lines or none (one transaction)."""
    user.require("kitting:issue")
    wo = await _wo(session, user, wo_id, lock=True)
    if wo.status not in _ACTIVE:
        raise ConflictError("Release the work order before kitting", code="wo_not_released")
    _, lines = await kit_lines(session, user, wo)
    by_id = {lv.line.id: lv for lv in lines}
    for lv in lines:  # an issue may name the same line in an earlier revision
        for gid in lv.group:
            by_id.setdefault(gid, lv)
    planned: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    records = []
    for item in issues:
        found = by_id.get(item["boq_line_id"])
        if found is None:
            raise NotFoundError(
                "That BOQ line is not on this work order's kit",
                details={"id": str(item["boq_line_id"])},
            )
        lv = found
        ln = lv.line
        if ln.part_id is None:
            raise ConflictError(
                f"Line {ln.line_no} has no part in the part master", code="line_without_part"
            )
        qty = Decimal(item["qty"])
        planned[ln.id] += qty
        if lv.issued + planned[ln.id] > lv.required:
            left = (lv.required - lv.issued).normalize()
            raise ConflictError(
                f"{ln.mpn}: only {left:f} more is needed for {wo.number}",
                code="over_issue",
                details={"required": str(lv.required), "issued": str(lv.issued)},
            )
        await inventory.get_location(session, item["location_id"])
        lot = item.get("lot_code") or None
        on_lot = await inventory.lot_on_hand(session, ln.part_id, item["location_id"], lot)
        if qty > on_lot:
            raise inventory.InsufficientStockError(
                f"{ln.mpn}: only {on_lot.normalize():f} of lot {lot or '(none)'} there",
                details={"on_hand": str(on_lot), "requested": str(qty)},
            )
        entry = await inventory.issue_to_boq_line(
            session,
            part_id=ln.part_id,
            location_id=item["location_id"],
            qty=qty,
            boq_line_id=ln.id,
            project_id=wo.project_id,
            lot_code=lot,
            note=f"Kitted to {wo.number}",
        )
        await inventory.consume_reservations(
            session, part_id=ln.part_id, project_id=wo.project_id, qty=qty
        )
        rec = KitIssue(
            work_order_id=wo.id,
            boq_line_id=ln.id,
            part_id=ln.part_id,
            location_id=item["location_id"],
            kind=KitKind.ISSUE.value,
            qty=qty,
            lot_code=lot,
            ledger_entry_id=entry.id,
            note=item.get("note"),
        )
        session.add(rec)
        records.append(rec)
    await session.flush()
    await session.commit()
    return records


async def return_kit(
    session: AsyncSession,
    user: Principal,
    wo_id: uuid.UUID,
    *,
    boq_line_id: uuid.UUID,
    location_id: uuid.UUID,
    qty: Decimal,
    lot_code: str | None,
    note: str | None,
) -> KitIssue:
    """Return unused parts to stores; they are reserved for the project again."""
    user.require("kitting:issue")
    wo = await _wo(session, user, wo_id, lock=True)
    if wo.status in (WoStatus.DRAFT.value, WoStatus.CANCELLED.value):
        raise ConflictError("Nothing was kitted to this order", code="invalid_status_transition")
    lot = lot_code or None
    issued = (await net_issued(session, wo.id)).get((boq_line_id, lot), ZERO)
    if qty > issued:
        raise ConflictError(
            f"Only {issued.normalize():f} of lot {lot or '(no lot)'} was issued to this line",
            code="return_exceeds_issue",
            details={"issued": str(issued)},
        )
    ln = await session.get(BoqLine, boq_line_id)
    assert ln is not None
    assert ln.part_id is not None
    await inventory.get_location(session, location_id)
    entry = await inventory.return_from_boq_line(
        session,
        part_id=ln.part_id,
        location_id=location_id,
        qty=qty,
        boq_line_id=ln.id,
        project_id=wo.project_id,
        lot_code=lot,
        note=f"Returned from {wo.number}" + (f": {note}" if note else ""),
    )
    await inventory.reserve(
        session,
        part_id=ln.part_id,
        project_id=wo.project_id,
        qty=qty,
        location_id=location_id,
        note=f"Returned from {wo.number}",
    )
    rec = KitIssue(
        work_order_id=wo.id,
        boq_line_id=ln.id,
        part_id=ln.part_id,
        location_id=location_id,
        kind=KitKind.RETURN.value,
        qty=qty,
        lot_code=lot,
        ledger_entry_id=entry.id,
        note=note,
    )
    session.add(rec)
    await session.flush()
    await session.commit()
    return rec


async def kit_records(session: AsyncSession, user: Principal, wo_id: uuid.UUID) -> list[KitIssue]:
    await _wo(session, user, wo_id)
    rows = await session.execute(
        select(KitIssue)
        .where(KitIssue.work_order_id == wo_id, KitIssue.is_deleted.is_(False))
        .order_by(KitIssue.created_at.desc())
    )
    return list(rows.scalars().all())


# ---------------------------------------------------------------- serials


_CODE_CLEAN = re.compile(r"[^A-Z0-9]+")


def serial_format(prefix: str, assembly_code: str, year: int, n: int) -> str:
    code = _CODE_CLEAN.sub("", assembly_code.upper()) or "ASM"
    return f"{prefix.upper()}-{code}-{year}-{n:05d}"


async def _next_serials(session: AsyncSession, assembly_id: uuid.UUID, count: int) -> list[int]:
    year = datetime.now(UTC).year
    await session.execute(
        pg_insert(SerialSequence)
        .values(assembly_id=assembly_id, year=year, last_value=0)
        .on_conflict_do_nothing()
    )
    seq = (
        await session.execute(
            select(SerialSequence)
            .where(SerialSequence.assembly_id == assembly_id, SerialSequence.year == year)
            .with_for_update()
        )
    ).scalar_one()
    await session.refresh(seq)
    start = seq.last_value + 1
    seq.last_value += count
    await session.flush()
    return list(range(start, start + count))


async def generate_serials(
    session: AsyncSession, user: Principal, wo_id: uuid.UUID, count: int | None
) -> list[SerialUnit]:
    user.require("wo:manage")
    wo = await _wo(session, user, wo_id, lock=True)
    if not wo.track_serials:
        raise ConflictError(f"{wo.number} is tracked by lot only", code="lot_tracked")
    if wo.status in (WoStatus.CANCELLED.value, WoStatus.CLOSED.value):
        raise ConflictError(f"{wo.number} is {wo.status}", code="invalid_status_transition")
    lot = await lot_of(session, wo.id)
    assert lot is not None
    existing = len(await units_of(session, lot.id))
    room = lot.qty - existing
    n = count or room
    if n <= 0 or n > room:
        raise ConflictError(
            f"The lot has {lot.qty} units and {existing} serials already", code="serials_exceed_lot"
        )
    assembly = await session.get(PcbAssembly, wo.assembly_id)
    assert assembly is not None
    company = (await session.execute(select(CompanySettings))).scalar_one_or_none()
    prefix = company.serial_prefix if company else "SN"
    year = datetime.now(UTC).year
    units = [
        SerialUnit(
            assembly_id=assembly.id,
            lot_id=lot.id,
            serial_number=serial_format(prefix, assembly.code, year, number),
        )
        for number in await _next_serials(session, assembly.id, n)
    ]
    session.add_all(units)
    await session.flush()
    await session.commit()
    return units


async def units_of(session: AsyncSession, lot_id: uuid.UUID) -> list[SerialUnit]:
    rows = await session.execute(
        select(SerialUnit)
        .where(SerialUnit.lot_id == lot_id, SerialUnit.is_deleted.is_(False))
        .order_by(SerialUnit.serial_number)
    )
    return list(rows.scalars().all())


# ---------------------------------------------------------------- stage progress


async def progress_rows(session: AsyncSession, stage_ids: list[uuid.UUID]) -> list[StageProgress]:
    if not stage_ids:
        return []
    rows = await session.execute(
        select(StageProgress).where(
            StageProgress.work_order_stage_id.in_(stage_ids), StageProgress.is_deleted.is_(False)
        )
    )
    return list(rows.scalars().all())


@dataclass
class StageCounts:
    units_in: int
    done: int
    failed: int
    awaiting_qc: int
    started: int


def stage_counts(
    stages: list[WorkOrderStage], progress: list[StageProgress], *, lot_qty: int, serial: bool
) -> dict[uuid.UUID, StageCounts]:
    """Units reaching each stage, passed / failed / awaiting QC there."""
    by_stage: dict[uuid.UUID, list[StageProgress]] = defaultdict(list)
    for p in progress:
        by_stage[p.work_order_stage_id].append(p)
    out: dict[uuid.UUID, StageCounts] = {}
    units_in = lot_qty
    for st in stages:
        rows = by_stage[st.id]
        done = sum(p.qty_passed for p in rows if p.status == StageStatus.COMPLETED.value)
        failed = sum(p.qty_failed for p in rows if p.status == StageStatus.COMPLETED.value)
        awaiting = sum(
            (1 if serial else p.qty_passed + p.qty_failed)
            for p in rows
            if p.status == StageStatus.AWAITING_QC.value
        )
        started = len(rows) if serial else sum(1 for _ in rows)
        out[st.id] = StageCounts(units_in, done, failed, awaiting, started)
        units_in = done
    return out


async def _refresh_statuses(session: AsyncSession, wo: WorkOrder) -> None:
    stages = await stages_of(session, wo.id)
    lot = await lot_of(session, wo.id)
    assert lot is not None
    progress = await progress_rows(session, [s.id for s in stages])
    counts = stage_counts(stages, progress, lot_qty=lot.qty, serial=wo.track_serials)
    by_stage: dict[uuid.UUID, list[StageProgress]] = defaultdict(list)
    for p in progress:
        by_stage[p.work_order_stage_id].append(p)
    previous_done = True
    for st in stages:
        c = counts[st.id]
        rows = by_stage[st.id]
        if (
            previous_done
            and c.units_in > 0
            and c.done + c.failed >= c.units_in
            and all(p.status == StageStatus.COMPLETED.value for p in rows)
        ):
            status = StageStatus.COMPLETED
        elif previous_done and c.units_in == 0:
            status = StageStatus.COMPLETED  # nothing reached it (all failed earlier)
        elif any(p.status == StageStatus.AWAITING_QC.value for p in rows):
            status = StageStatus.AWAITING_QC
        elif rows:
            status = StageStatus.IN_PROGRESS
        else:
            status = StageStatus.NOT_STARTED
        st.status = status.value
        previous_done = status == StageStatus.COMPLETED
    if progress and wo.status == WoStatus.RELEASED.value:
        wo.status = WoStatus.IN_PROGRESS.value
        lot.status = LotStatus.IN_PROGRESS.value
    if (
        stages
        and all(s.status == StageStatus.COMPLETED.value for s in stages)
        and wo.status in _ACTIVE
    ):
        wo.status = WoStatus.COMPLETED.value
        lot.status = LotStatus.COMPLETED.value
    await session.flush()


async def record_progress(
    session: AsyncSession,
    user: Principal,
    stage_id: uuid.UUID,
    *,
    action: str,
    serial_unit_id: uuid.UUID | None,
    qty_passed: int | None,
    qty_failed: int | None,
    passed: bool | None,
    notes: str | None,
) -> StageProgress:
    """start -> in progress; finish -> awaiting QC (QC stages); complete -> completed.
    Completing a QC stage needs a passed inspection; nothing here can skip it."""
    user.require("stage:progress")
    stage = await session.get(WorkOrderStage, stage_id)
    if stage is None or stage.is_deleted:
        raise NotFoundError("Stage not found", details={"id": str(stage_id)})
    wo = await _wo(session, user, stage.work_order_id, lock=True)
    if wo.status not in _ACTIVE:
        raise ConflictError(
            f"{wo.number} is {wo.status.replace('_', ' ')}; release it first",
            code="wo_not_released",
        )
    lot = await lot_of(session, wo.id)
    assert lot is not None
    stages = await stages_of(session, wo.id)
    idx = next(i for i, s in enumerate(stages) if s.id == stage.id)
    prev = stages[idx - 1] if idx > 0 else None
    unit: SerialUnit | None = None
    if wo.track_serials:
        if serial_unit_id is None:
            raise AppError("Choose the serial number", code="serial_required", status_code=422)
        unit = await session.get(SerialUnit, serial_unit_id)
        if unit is None or unit.lot_id != lot.id or unit.is_deleted:
            raise NotFoundError(
                "Serial not found on this work order", details={"id": str(serial_unit_id)}
            )
    elif serial_unit_id is not None:
        raise AppError(f"{wo.number} is tracked by lot", code="lot_tracked", status_code=422)

    async def row_for(st: WorkOrderStage) -> StageProgress | None:
        stmt = select(StageProgress).where(
            StageProgress.work_order_stage_id == st.id,
            StageProgress.lot_id == lot.id,
            StageProgress.is_deleted.is_(False),
        )
        stmt = stmt.where(
            StageProgress.serial_unit_id == unit.id
            if unit
            else StageProgress.serial_unit_id.is_(None)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    # Units available at this stage.
    if prev is None:
        units_in = 1 if unit else lot.qty
    else:
        before = await row_for(prev)
        ok = before is not None and before.status == StageStatus.COMPLETED.value
        if unit:
            ok = ok and before is not None and before.qty_passed == 1
        if not ok:
            raise ConflictError(
                f"Complete {prev.name} first" + (" (with a pass)" if unit else ""),
                code="previous_stage_open",
            )
        assert before is not None
        units_in = 1 if unit else before.qty_passed
    if unit is not None and unit.status in (UnitStatus.FAILED.value, UnitStatus.SCRAPPED.value):
        raise ConflictError(f"{unit.serial_number} failed an earlier stage", code="unit_failed")

    row = await row_for(stage)
    now = utcnow()
    if action == "start":
        if row is not None:
            raise ConflictError(
                f"{stage.name} is already {row.status.replace('_', ' ')}", code="already_started"
            )
        row = StageProgress(
            work_order_stage_id=stage.id,
            lot_id=lot.id,
            serial_unit_id=unit.id if unit else None,
            status=StageStatus.IN_PROGRESS.value,
            started_at=now,
            operator_id=user.id,
            notes=notes,
        )
        session.add(row)
    else:
        if row is None or row.status == StageStatus.COMPLETED.value:
            raise ConflictError(
                f"{stage.name} is {'completed' if row else 'not started'}",
                code="invalid_status_transition",
            )
        if row.status == StageStatus.IN_PROGRESS.value:
            # Record the outcome now (it is what QC will check).
            if unit:
                if passed is None:
                    raise AppError(
                        "Say whether the unit passed", code="result_required", status_code=422
                    )
                row.qty_passed, row.qty_failed = (1, 0) if passed else (0, 1)
            else:
                good, bad = qty_passed or 0, qty_failed or 0
                if good + bad != units_in:
                    raise AppError(
                        f"Passed + failed must equal the {units_in} units at this stage",
                        code="qty_mismatch",
                        status_code=422,
                    )
                row.qty_passed, row.qty_failed = good, bad
        if notes:
            row.notes = f"{row.notes}\n{notes}".strip() if row.notes else notes
        row.operator_id = user.id
        if action == "finish":
            if not stage.requires_qc:
                raise AppError(
                    f"{stage.name} needs no QC: complete it", code="no_qc_needed", status_code=422
                )
            row.status = StageStatus.AWAITING_QC.value
        else:  # complete
            if stage.requires_qc and not await qc.passed_inspection_exists(
                session,
                work_order_stage_id=stage.id,
                lot_id=lot.id,
                serial_unit_id=unit.id if unit else None,
            ):
                raise ConflictError(
                    f"{stage.name} requires a passed QC inspection before it can be completed",
                    code="qc_required",
                )
            row.status = StageStatus.COMPLETED.value
            row.completed_at = now
            if unit is not None:
                if row.qty_failed:
                    unit.status = UnitStatus.FAILED.value
                elif idx == len(stages) - 1:
                    unit.status = UnitStatus.PASSED.value
    await session.flush()
    await _refresh_statuses(session, wo)
    await session.commit()
    return row


# ---------------------------------------------------------------- genealogy and scan


@dataclass
class GenealogyView:
    unit: SerialUnit
    wo: WorkOrder
    lot: BuildLot
    parts: list[tuple[BoqLine, str, str | None, Decimal]]


async def genealogy(
    session: AsyncSession, user: Principal, serial_unit_id: uuid.UUID
) -> GenealogyView:
    """Which part lots went into a serial: the net kit issues of its work order by BOQ line
    and lot (kitting is per work order, so every unit of the order shares these lots)."""
    unit = await session.get(SerialUnit, serial_unit_id)
    if unit is None or unit.is_deleted or unit.lot_id is None:
        raise NotFoundError("Serial not found", details={"id": str(serial_unit_id)})
    lot = await session.get(BuildLot, unit.lot_id)
    assert lot is not None
    assert lot.work_order_id is not None
    wo = await _wo(session, user, lot.work_order_id)
    net = {k: v for k, v in (await net_issued(session, wo.id)).items() if v > 0}
    lines = (
        {
            ln.id: ln
            for ln in (
                await session.execute(select(BoqLine).where(BoqLine.id.in_({k[0] for k in net})))
            ).scalars()
        }
        if net
        else {}
    )
    part_map = await parts.get_many(session, [ln.part_id for ln in lines.values() if ln.part_id])
    out = []
    for (line_id, lot_code), q in sorted(
        net.items(), key=lambda kv: (lines[kv[0][0]].line_no, kv[0][1] or "")
    ):
        ln = lines[line_id]
        mpn = part_map[ln.part_id].mpn if ln.part_id in part_map else (ln.mpn or "")
        out.append((ln, mpn, lot_code, q))
    return GenealogyView(unit, wo, lot, out)


async def find_serial(session: AsyncSession, user: Principal, code: str) -> SerialUnit:
    user.require("production:read")
    rows = (
        (
            await session.execute(
                select(SerialUnit).where(
                    func.upper(SerialUnit.serial_number) == code.strip().upper(),
                    SerialUnit.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise NotFoundError(f"No unit with serial {code.strip()}", code="serial_not_found")
    if len(rows) > 1:
        raise ConflictError("That serial exists on several assemblies", code="ambiguous_serial")
    unit = rows[0]
    lot = await session.get(BuildLot, unit.lot_id) if unit.lot_id else None
    if lot is None or lot.work_order_id is None:
        raise NotFoundError("The unit is not on a work order", code="serial_not_found")
    await _wo(session, user, lot.work_order_id)  # scope
    return unit


async def unit_position(
    session: AsyncSession, wo: WorkOrder, unit: SerialUnit
) -> tuple[WorkOrderStage | None, StageProgress | None]:
    """The stage the unit is at: its open progress, else the next stage to start."""
    stages = await stages_of(session, wo.id)
    rows = {
        p.work_order_stage_id: p
        for p in await progress_rows(session, [s.id for s in stages])
        if p.serial_unit_id == unit.id
    }
    for st in stages:
        p = rows.get(st.id)
        if p is None or p.status != StageStatus.COMPLETED.value:
            return st, p
        if p.qty_failed:
            return st, p
    return None, None


def next_action(
    stage: WorkOrderStage | None, p: StageProgress | None, unit_status: str
) -> str | None:
    if stage is None or unit_status in (UnitStatus.FAILED.value, UnitStatus.SCRAPPED.value):
        return None
    if p is None:
        return "start"
    if p.status == StageStatus.IN_PROGRESS.value:
        return "finish" if stage.requires_qc else "complete"
    if p.status == StageStatus.AWAITING_QC.value:
        return "complete"
    return None


# ---------------------------------------------------------------- views for lists and the board


@dataclass
class WoFacts:
    project: Project
    module: Module | None
    assembly: PcbAssembly
    lot: BuildLot | None
    stages: list[WorkOrderStage]
    counts: dict[uuid.UUID, StageCounts]
    serial_count: int

    @property
    def current(self) -> WorkOrderStage | None:
        return next((s for s in self.stages if s.status != StageStatus.COMPLETED.value), None)

    @property
    def units_completed(self) -> int:
        return self.counts[self.stages[-1].id].done if self.stages else 0

    @property
    def units_failed(self) -> int:
        return sum(c.failed for c in self.counts.values())


async def facts(session: AsyncSession, wo: WorkOrder) -> WoFacts:
    project = await session.get(Project, wo.project_id)
    module = await session.get(Module, wo.module_id) if wo.module_id else None
    assembly = await session.get(PcbAssembly, wo.assembly_id)
    assert project is not None
    assert assembly is not None
    lot = await lot_of(session, wo.id)
    stages = await stages_of(session, wo.id)
    progress = await progress_rows(session, [s.id for s in stages])
    counts = stage_counts(
        stages, progress, lot_qty=lot.qty if lot else wo.build_qty, serial=wo.track_serials
    )
    serials = len(await units_of(session, lot.id)) if lot else 0
    return WoFacts(project, module, assembly, lot, stages, counts, serials)
