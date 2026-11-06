"""Response builders for the production API (read-only; rules live in service.py)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import Principal
from app.modules.inventory import service as inventory
from app.modules.org.models import SerialUnit
from app.modules.parts import service as parts
from app.modules.production import service
from app.modules.production.models import (
    DEFAULT_STAGES,
    KitIssue,
    StageProgress,
    StageStatus,
    StageTemplate,
    WorkOrder,
    WoStatus,
)
from app.modules.production.schemas import (
    BoardCard,
    BoardColumn,
    Genealogy,
    GenealogyPart,
    KitLine,
    KitOut,
    KitRecord,
    ProgressOut,
    Readiness,
    ScanResult,
    StageSummary,
    StepOut,
    TemplateOut,
    UnitOut,
    WoDetail,
    WoOut,
)
from app.modules.users import service as users


async def template_out(
    session: AsyncSession, t: StageTemplate, usage: dict[uuid.UUID, int]
) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        description=t.description,
        is_default=t.is_default,
        assembly_count=usage.get(t.id, 0),
        steps=[
            StepOut(
                id=s.id, seq=s.seq, stage_code=s.stage_code, name=s.name, requires_qc=s.requires_qc
            )
            for s in await service.template_steps(session, t.id)
        ],
        row_version=t.row_version,
    )


def _wo_out(wo: WorkOrder, f: service.WoFacts) -> WoOut:
    current = f.current
    return WoOut(
        id=wo.id,
        number=wo.number,
        project_id=wo.project_id,
        project_code=f.project.code,
        project_name=f.project.name,
        module_id=wo.module_id,
        module_code=f.module.code if f.module else None,
        assembly_id=wo.assembly_id,
        assembly_label=f"{f.assembly.code} rev {f.assembly.revision} · {f.assembly.board_name}",
        boq_id=wo.boq_id,
        build_qty=wo.build_qty,
        status=wo.status,
        planned_start=wo.planned_start,
        planned_end=wo.planned_end,
        released_at=wo.released_at,
        release_override_reason=wo.release_override_reason,
        track_serials=wo.track_serials,
        notes=wo.notes,
        lot_id=f.lot.id if f.lot else None,
        lot_number=f.lot.lot_number if f.lot else None,
        current_stage=current.name
        if current and wo.status not in (WoStatus.DRAFT.value,)
        else None,
        units_completed=f.units_completed,
        units_failed=f.units_failed,
        serial_count=f.serial_count,
        created_at=wo.created_at,
        row_version=wo.row_version,
    )


async def wo_outs(session: AsyncSession, orders: list[WorkOrder]) -> list[WoOut]:
    return [_wo_out(wo, await service.facts(session, wo)) for wo in orders]


async def wo_detail(session: AsyncSession, user: Principal, wo: WorkOrder) -> WoDetail:
    f = await service.facts(session, wo)
    ready = None
    if wo.status == WoStatus.DRAFT.value:
        r = await service.readiness(session, user, wo)
        ready = Readiness(
            clear_to_build=r.clear_to_build,
            reason=r.reason,
            lines=r.lines,
            lines_received=r.lines_received,
        )
    return WoDetail(
        **_wo_out(wo, f).model_dump(),
        stages=[
            StageSummary(
                id=s.id,
                seq=s.seq,
                stage_code=s.stage_code,
                name=s.name,
                requires_qc=s.requires_qc,
                status=s.status,
                units_in=f.counts[s.id].units_in,
                units_done=f.counts[s.id].done,
                units_failed=f.counts[s.id].failed,
                units_awaiting_qc=f.counts[s.id].awaiting_qc,
            )
            for s in f.stages
        ],
        readiness=ready,
    )


async def kit_out(session: AsyncSession, user: Principal, wo: WorkOrder) -> KitOut:
    tracked, lines = await service.kit_lines(session, user, wo)
    out = [
        KitLine(
            boq_line_id=lv.line.id,
            line_no=lv.line.line_no,
            ref_des=lv.line.ref_des,
            part_id=lv.line.part_id,
            mpn=lv.line.mpn,
            description=lv.line.description,
            unit=lv.line.unit,
            dnp=lv.line.dnp,
            required=lv.required,
            issued=lv.issued,
            shortage=lv.shortage,
            available=lv.available,
            reserved_for_project=lv.reserved_for_project,
        )
        for lv in lines
    ]
    return KitOut(
        boq_id=tracked.view.boq.id if tracked else None,
        boq_name=tracked.view.boq.name if tracked else None,
        revision=tracked.revision.revision if tracked and tracked.revision else None,
        lines=out,
        complete=bool(out) and all(line.shortage == 0 for line in out),
    )


async def kit_records(
    session: AsyncSession, user: Principal, items: list[KitIssue]
) -> list[KitRecord]:
    part_map = await parts.get_many(session, {i.part_id for i in items})
    codes = (
        {loc.id: loc.code for loc in await inventory.list_locations(session, user)}
        if user.can("inventory:read")
        else {}
    )
    names = await users.display_names(session, [i.created_by for i in items])
    return [
        KitRecord(
            id=i.id,
            kind=i.kind,
            boq_line_id=i.boq_line_id,
            mpn=part_map[i.part_id].mpn,
            location_code=codes.get(i.location_id, ""),
            lot_code=i.lot_code,
            qty=i.qty,
            note=i.note,
            created_at=i.created_at,
            created_by_name=names.get(i.created_by) if i.created_by else None,
        )
        for i in items
    ]


async def progress_outs(session: AsyncSession, wo: WorkOrder) -> list[ProgressOut]:
    stages = {s.id: s for s in await service.stages_of(session, wo.id)}
    rows = await service.progress_rows(session, list(stages))
    serials = (
        {u.id: u.serial_number for u in await service.units_of(session, rows[0].lot_id)}
        if rows
        else {}
    )
    names = await users.display_names(session, [p.operator_id for p in rows])
    return sorted(
        (
            _progress_out(
                p,
                stages[p.work_order_stage_id].name,
                stages[p.work_order_stage_id].seq,
                serials,
                names,
            )
            for p in rows
        ),
        key=lambda p: (p.serial_number or "", p.seq),
    )


def _progress_out(
    p: StageProgress,
    stage_name: str,
    seq: int,
    serials: dict[uuid.UUID, str],
    names: dict[uuid.UUID, str],
) -> ProgressOut:
    return ProgressOut(
        id=p.id,
        work_order_stage_id=p.work_order_stage_id,
        stage_name=stage_name,
        seq=seq,
        serial_unit_id=p.serial_unit_id,
        serial_number=serials.get(p.serial_unit_id) if p.serial_unit_id else None,
        status=p.status,
        started_at=p.started_at,
        completed_at=p.completed_at,
        qty_passed=p.qty_passed,
        qty_failed=p.qty_failed,
        operator_name=names.get(p.operator_id) if p.operator_id else None,
        notes=p.notes,
    )


async def single_progress(session: AsyncSession, p: StageProgress) -> ProgressOut:
    from app.modules.production.models import WorkOrderStage

    stage = await session.get(WorkOrderStage, p.work_order_stage_id)
    assert stage is not None
    unit = await session.get(SerialUnit, p.serial_unit_id) if p.serial_unit_id else None
    names = await users.display_names(session, [p.operator_id])
    return _progress_out(
        p, stage.name, stage.seq, {unit.id: unit.serial_number} if unit else {}, names
    )


async def unit_outs(session: AsyncSession, wo: WorkOrder) -> list[UnitOut]:
    lot = await service.lot_of(session, wo.id)
    out = []
    for u in await service.units_of(session, lot.id) if lot else []:
        stage, p = await service.unit_position(session, wo, u)
        out.append(
            UnitOut(
                id=u.id,
                serial_number=u.serial_number,
                status=u.status,
                current_stage=stage.name if stage else None,
                current_stage_id=stage.id if stage else None,
                current_stage_status=(p.status if p else StageStatus.NOT_STARTED.value)
                if stage
                else None,
            )
        )
    return out


async def scan_result(session: AsyncSession, user: Principal, unit: SerialUnit) -> ScanResult:
    from app.modules.org.models import BuildLot

    lot = await session.get(BuildLot, unit.lot_id) if unit.lot_id else None
    assert lot is not None
    assert lot.work_order_id is not None
    wo = await service.get_wo(session, user, lot.work_order_id)
    stage, p = await service.unit_position(session, wo, unit)
    return ScanResult(
        serial_unit_id=unit.id,
        serial_number=unit.serial_number,
        work_order_id=wo.id,
        work_order_number=wo.number,
        unit_status=unit.status,
        stage=await single_progress(session, p) if p else None,
        stage_id=stage.id if stage else None,
        stage_name=stage.name if stage else None,
        stage_requires_qc=stage.requires_qc if stage else False,
        next_action=service.next_action(stage, p, unit.status)
        if wo.status in ("released", "in_progress")
        else None,
    )


async def genealogy_out(view: service.GenealogyView, assembly_label: str) -> Genealogy:
    return Genealogy(
        serial_number=view.unit.serial_number,
        work_order_id=view.wo.id,
        work_order_number=view.wo.number,
        lot_number=view.lot.lot_number,
        assembly_label=assembly_label,
        parts=[
            GenealogyPart(boq_line_id=ln.id, ref_des=ln.ref_des, mpn=mpn, lot_code=lot, qty=q)
            for ln, mpn, lot, q in view.parts
        ],
    )


async def board(session: AsyncSession, user: Principal) -> list[BoardColumn]:
    """Kanban: planned (draft), released and not started, one column per stage type in the
    default order (custom stages last), then completed."""
    orders = await service.list_wos(
        session,
        user,
        status=[
            WoStatus.DRAFT.value,
            WoStatus.RELEASED.value,
            WoStatus.IN_PROGRESS.value,
            WoStatus.COMPLETED.value,
        ],
    )
    columns: dict[str, BoardColumn] = {"draft": BoardColumn(key="draft", label="Planned", cards=[])}
    columns["released"] = BoardColumn(key="released", label="Released, not started", cards=[])
    for code, name, _qc in DEFAULT_STAGES:
        columns[code.value] = BoardColumn(key=code.value, label=name, cards=[])
    columns["custom"] = BoardColumn(key="custom", label="Other stages", cards=[])
    columns["completed"] = BoardColumn(key="completed", label="Completed", cards=[])
    for wo in orders:
        f = await service.facts(session, wo)
        current = f.current
        c = f.counts.get(current.id) if current else None
        card = BoardCard(
            work_order_id=wo.id,
            number=wo.number,
            project_code=f.project.code,
            assembly_label=f"{f.assembly.code} rev {f.assembly.revision}",
            build_qty=wo.build_qty,
            status=wo.status,
            stage_name=current.name if current else None,
            stage_seq=current.seq if current else None,
            stage_count=len(f.stages),
            units_at_stage=c.units_in if c else 0,
            units_done_at_stage=c.done if c else 0,
            awaiting_qc=c.awaiting_qc if c else 0,
            planned_end=wo.planned_end,
        )
        if wo.status == WoStatus.DRAFT.value:
            key = "draft"
        elif wo.status == WoStatus.COMPLETED.value or current is None:
            key = "completed"
        elif wo.status == WoStatus.RELEASED.value:
            key = "released"
        else:
            key = current.stage_code if current.stage_code in columns else "custom"
        columns[key].cards.append(card)
    return list(columns.values())
