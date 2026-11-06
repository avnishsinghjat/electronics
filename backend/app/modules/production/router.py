import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.org.models import PcbAssembly
from app.modules.production import labels, service, views
from app.modules.production.schemas import (
    BoardColumn,
    Genealogy,
    KitBatchIn,
    KitIssueIn,
    KitOut,
    KitRecord,
    ProgressIn,
    ProgressOut,
    ReleaseIn,
    ScanResult,
    SerialsIn,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
    UnitOut,
    VersionIn,
    WoCreate,
    WoDetail,
    WoOut,
    WoUpdate,
)

router = APIRouter(tags=["production"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("production:read"))]
Planner = Annotated[Principal, Depends(require("wo:manage"))]
Releaser = Annotated[Principal, Depends(require("wo:release"))]
Kitter = Annotated[Principal, Depends(require("kitting:issue"))]
Operator = Annotated[Principal, Depends(require("stage:progress"))]
Version = Annotated[int, Query(ge=1)]


def _csv(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


# ---------------------------------------------------------------- stage templates


@router.get(
    "/production/stage-templates",
    response_model=list[TemplateOut],
    summary="Stage templates with steps",
)
async def list_templates(user: Reader, session: SessionDep) -> list[TemplateOut]:
    usage = await service.template_usage(session)
    return [
        await views.template_out(session, t, usage)
        for t in await service.list_templates(session, user)
    ]


@router.get(
    "/stage-templates/{template_id}", response_model=TemplateOut, summary="One stage template"
)
async def get_template(template_id: uuid.UUID, user: Reader, session: SessionDep) -> TemplateOut:
    t = await service.get_template(session, user, template_id)
    return await views.template_out(session, t, await service.template_usage(session))


@router.post(
    "/stage-templates",
    response_model=TemplateOut,
    status_code=201,
    summary="Create a stage template",
)
async def create_template(data: TemplateCreate, user: Planner, session: SessionDep) -> TemplateOut:
    t = await service.create_template(session, user, data)
    return await views.template_out(session, t, await service.template_usage(session))


@router.put(
    "/stage-templates/{template_id}", response_model=TemplateOut, summary="Edit steps (order, QC)"
)
async def update_template(
    template_id: uuid.UUID, data: TemplateUpdate, user: Planner, session: SessionDep
) -> TemplateOut:
    t = await service.update_template(session, user, template_id, data)
    return await views.template_out(session, t, await service.template_usage(session))


@router.delete(
    "/stage-templates/{template_id}", status_code=204, summary="Delete an unused template"
)
async def delete_template(
    template_id: uuid.UUID, row_version: Version, user: Planner, session: SessionDep
) -> Response:
    await service.delete_template(session, user, template_id, row_version)
    return Response(status_code=204)


# ---------------------------------------------------------------- work orders


@router.get("/work-orders", response_model=list[WoOut], summary="Work orders")
async def list_wos(
    user: Reader,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
) -> list[WoOut]:
    return await views.wo_outs(
        session, await service.list_wos(session, user, project_id=project_id, status=_csv(status))
    )


@router.get("/work-orders/{wo_id}", response_model=WoDetail, summary="One work order")
async def get_wo(wo_id: uuid.UUID, user: Reader, session: SessionDep) -> WoDetail:
    return await views.wo_detail(session, user, await service.get_wo(session, user, wo_id))


@router.post(
    "/work-orders", response_model=WoDetail, status_code=201, summary="Create a work order"
)
async def create_wo(data: WoCreate, user: Planner, session: SessionDep) -> WoDetail:
    return await views.wo_detail(session, user, await service.create_wo(session, user, data))


@router.put("/work-orders/{wo_id}", response_model=WoDetail, summary="Edit a draft work order")
async def update_wo(
    wo_id: uuid.UUID, data: WoUpdate, user: Planner, session: SessionDep
) -> WoDetail:
    return await views.wo_detail(session, user, await service.update_wo(session, user, wo_id, data))


@router.post(
    "/work-orders/{wo_id}/release",
    response_model=WoDetail,
    summary="Release (needs clear to build, or a PM override with a reason)",
)
async def release_wo(
    wo_id: uuid.UUID, data: ReleaseIn, user: Releaser, session: SessionDep
) -> WoDetail:
    wo = await service.release_wo(session, user, wo_id, data.row_version, data.override_reason)
    return await views.wo_detail(session, user, wo)


@router.post("/work-orders/{wo_id}/cancel", response_model=WoDetail, summary="Cancel")
async def cancel_wo(
    wo_id: uuid.UUID, data: VersionIn, user: Planner, session: SessionDep
) -> WoDetail:
    return await views.wo_detail(
        session, user, await service.cancel_wo(session, user, wo_id, data.row_version)
    )


@router.post(
    "/work-orders/{wo_id}/close", response_model=WoDetail, summary="Close a completed order"
)
async def close_wo(
    wo_id: uuid.UUID, data: VersionIn, user: Planner, session: SessionDep
) -> WoDetail:
    return await views.wo_detail(
        session, user, await service.close_wo(session, user, wo_id, data.row_version)
    )


# ---------------------------------------------------------------- kitting


@router.get("/work-orders/{wo_id}/kit", response_model=KitOut, summary="Kit list and shortages")
async def kit(wo_id: uuid.UUID, user: Reader, session: SessionDep) -> KitOut:
    return await views.kit_out(session, user, await service.get_wo(session, user, wo_id))


@router.get(
    "/work-orders/{wo_id}/kit/records", response_model=list[KitRecord], summary="Issues and returns"
)
async def kit_records(wo_id: uuid.UUID, user: Reader, session: SessionDep) -> list[KitRecord]:
    return await views.kit_records(session, user, await service.kit_records(session, user, wo_id))


@router.post(
    "/work-orders/{wo_id}/kit/issue",
    response_model=list[KitRecord],
    status_code=201,
    summary="Issue parts to the work order (ledger ISSUE)",
)
async def issue(
    wo_id: uuid.UUID, data: KitBatchIn, user: Kitter, session: SessionDep
) -> list[KitRecord]:
    records = await service.issue_kit(session, user, wo_id, [i.model_dump() for i in data.issues])
    return await views.kit_records(session, user, records)


@router.post(
    "/work-orders/{wo_id}/kit/return",
    response_model=KitRecord,
    status_code=201,
    summary="Return unused parts (ledger RETURN)",
)
async def return_parts(
    wo_id: uuid.UUID, data: KitIssueIn, user: Kitter, session: SessionDep
) -> KitRecord:
    rec = await service.return_kit(
        session,
        user,
        wo_id,
        boq_line_id=data.boq_line_id,
        location_id=data.location_id,
        qty=data.qty,
        lot_code=data.lot_code,
        note=data.note,
    )
    return (await views.kit_records(session, user, [rec]))[0]


# ---------------------------------------------------------------- serials, progress, genealogy


@router.get("/work-orders/{wo_id}/units", response_model=list[UnitOut], summary="Serialised units")
async def units(wo_id: uuid.UUID, user: Reader, session: SessionDep) -> list[UnitOut]:
    return await views.unit_outs(session, await service.get_wo(session, user, wo_id))


@router.post(
    "/work-orders/{wo_id}/serials",
    response_model=list[UnitOut],
    status_code=201,
    summary="Generate serials",
)
async def generate_serials(
    wo_id: uuid.UUID, data: SerialsIn, user: Planner, session: SessionDep
) -> list[UnitOut]:
    await service.generate_serials(session, user, wo_id, data.count)
    return await views.unit_outs(session, await service.get_wo(session, user, wo_id))


@router.get(
    "/work-orders/{wo_id}/labels.pdf",
    summary="Serial labels with QR codes (PDF, A4 3x8)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def labels_pdf(wo_id: uuid.UUID, user: Reader, session: SessionDep) -> Response:
    number, content = await labels.labels_pdf(session, user, wo_id)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{number}-labels.pdf"'},
    )


@router.get(
    "/work-orders/{wo_id}/progress", response_model=list[ProgressOut], summary="Stage progress"
)
async def progress(wo_id: uuid.UUID, user: Reader, session: SessionDep) -> list[ProgressOut]:
    return await views.progress_outs(session, await service.get_wo(session, user, wo_id))


@router.post(
    "/work-order-stages/{stage_id}/progress",
    response_model=ProgressOut,
    summary="Start, finish (awaiting QC) or complete a stage for a lot or serial",
)
async def record_progress(
    stage_id: uuid.UUID, data: ProgressIn, user: Operator, session: SessionDep
) -> ProgressOut:
    p = await service.record_progress(
        session,
        user,
        stage_id,
        action=data.action,
        serial_unit_id=data.serial_unit_id,
        qty_passed=data.qty_passed,
        qty_failed=data.qty_failed,
        passed=data.passed,
        notes=data.notes,
    )
    return await views.single_progress(session, p)


@router.get(
    "/serial-units/{unit_id}/genealogy", response_model=Genealogy, summary="Part lots in a serial"
)
async def genealogy(unit_id: uuid.UUID, user: Reader, session: SessionDep) -> Genealogy:
    g = await service.genealogy(session, user, unit_id)
    assembly = await session.get(PcbAssembly, g.wo.assembly_id)
    label = f"{assembly.code} rev {assembly.revision}" if assembly else ""
    return await views.genealogy_out(g, label)


@router.get(
    "/production/scan", response_model=ScanResult, summary="Find a unit by its serial (QR scan)"
)
async def scan(
    user: Reader, session: SessionDep, code: Annotated[str, Query(min_length=1, max_length=64)]
) -> ScanResult:
    return await views.scan_result(session, user, await service.find_serial(session, user, code))


@router.get(
    "/production/board", response_model=list[BoardColumn], summary="Work order board by stage"
)
async def board(user: Reader, session: SessionDep) -> list[BoardColumn]:
    return await views.board(session, user)
