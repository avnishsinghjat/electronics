import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.boq import service
from app.modules.boq.importer import FIELDS
from app.modules.boq.schemas import (
    BoqCreate,
    BoqOut,
    BuildUpdate,
    CommitIn,
    CompareOut,
    FieldInfo,
    ImportOut,
    LineOut,
    LinesSave,
    MappingIn,
    RevisionOut,
    RevisionSummary,
    TemplateOut,
    VersionIn,
)

router = APIRouter(tags=["boq"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[Principal, Depends(require("boq:read"))]
Editor = Annotated[Principal, Depends(require("boq:edit"))]
Importer = Annotated[Principal, Depends(require("boq:import"))]
Version = Annotated[int, Query(ge=1)]


def boq_out(v: service.BoqView) -> BoqOut:
    return BoqOut(
        id=v.boq.id,
        project_id=v.project.id,
        project_code=v.project.code,
        project_name=v.project.name,
        module_id=v.boq.module_id,
        module_code=v.module.code if v.module else None,
        assembly_id=v.boq.assembly_id,
        assembly_label=f"{v.assembly.code} rev {v.assembly.revision}" if v.assembly else None,
        name=v.boq.name,
        notes=v.boq.notes,
        row_version=v.boq.row_version,
        revisions=[
            RevisionSummary(
                id=r.id,
                revision=r.revision,
                status=r.status,
                build_qty=r.build_qty,
                line_count=n,
                released_at=r.released_at,
                created_at=r.created_at,
                row_version=r.row_version,
            )
            for r, n in v.revisions
        ],
    )


@router.get("/boqs", response_model=list[BoqOut], summary="All BOQs in scope")
async def list_all(user: Reader, session: SessionDep) -> list[BoqOut]:
    return [boq_out(v) for v in await service.list_all_boqs(session, user)]


@router.get("/projects/{project_id}/boqs", response_model=list[BoqOut], summary="BOQs of a project")
async def list_for_project(
    project_id: uuid.UUID, user: Reader, session: SessionDep
) -> list[BoqOut]:
    return [boq_out(v) for v in await service.list_project_boqs(session, user, project_id)]


@router.post(
    "/projects/{project_id}/boqs", response_model=BoqOut, status_code=201, summary="Create a BOQ"
)
async def create(
    project_id: uuid.UUID, body: BoqCreate, user: Editor, session: SessionDep
) -> BoqOut:
    """Starts with an empty draft revision A unless `create_revision` is false (import first)."""
    boq = await service.create_boq(session, user, project_id, body)
    return boq_out(await service.get_boq(session, user, boq.id))


@router.get("/boqs/{boq_id}", response_model=BoqOut, summary="Get a BOQ and its revisions")
async def get(boq_id: uuid.UUID, user: Reader, session: SessionDep) -> BoqOut:
    return boq_out(await service.get_boq(session, user, boq_id))


@router.delete("/boqs/{boq_id}", status_code=204, summary="Delete a BOQ that was never released")
async def delete(
    boq_id: uuid.UUID, row_version: Version, user: Editor, session: SessionDep
) -> None:
    await service.delete_boq(session, user, boq_id, row_version)


@router.post(
    "/boqs/{boq_id}/revisions",
    response_model=RevisionSummary,
    status_code=201,
    summary="Start a new revision",
)
async def new_revision(boq_id: uuid.UUID, user: Editor, session: SessionDep) -> RevisionSummary:
    """Copies the current (released, else latest) revision into a new draft."""
    rev = await service.create_revision(session, user, boq_id)
    _, lines = await service.revision_lines(session, user, rev.id)
    return RevisionSummary(
        id=rev.id,
        revision=rev.revision,
        status=rev.status,
        build_qty=rev.build_qty,
        line_count=len(lines),
        released_at=rev.released_at,
        created_at=rev.created_at,
        row_version=rev.row_version,
    )


@router.get(
    "/boq-revisions/{revision_id}",
    response_model=RevisionOut,
    summary="Revision with lines and status",
)
async def get_revision(revision_id: uuid.UUID, user: Reader, session: SessionDep) -> RevisionOut:
    rev, lines = await service.revision_lines(session, user, revision_id)
    return RevisionOut(
        id=rev.id,
        boq_id=rev.boq_id,
        revision=rev.revision,
        status=rev.status,
        build_qty=rev.build_qty,
        attrition_by_category=rev.attrition_by_category or {},
        released_at=rev.released_at,
        notes=rev.notes,
        row_version=rev.row_version,
        lines=[
            LineOut(
                id=ln.id,
                line_key=ln.line_key,
                line_no=ln.line_no,
                part_id=ln.part_id,
                ref_des=ln.ref_des,
                qty_per_unit=ln.qty_per_unit,
                mpn=ln.mpn,
                manufacturer=ln.manufacturer,
                description=ln.description,
                value=ln.value,
                package=ln.package,
                category=ln.category,
                unit=ln.unit,
                dnp=ln.dnp,
                attrition_pct=ln.attrition_pct,
                attrition_override=ln.attrition_override,
                unit_price=ln.unit_price,
                preferred_vendor_id=ln.preferred_vendor_id,
                notes=ln.notes,
                required_qty=q.required,
                ordered_qty=q.ordered,
                received_qty=q.received,
                issued_qty=q.issued,
                shortfall=q.shortfall,
                pending_receipt=q.pending_receipt,
                status=q.status.value,
            )
            for ln, q in lines
        ],
    )


@router.patch(
    "/boq-revisions/{revision_id}",
    response_model=RevisionSummary,
    summary="Build quantity, attrition by category, notes",
)
async def update_build(
    revision_id: uuid.UUID, body: BuildUpdate, user: Editor, session: SessionDep
) -> RevisionSummary:
    rev = await service.update_build(session, user, revision_id, body)
    _, lines = await service.revision_lines(session, user, rev.id)
    return RevisionSummary(
        id=rev.id,
        revision=rev.revision,
        status=rev.status,
        build_qty=rev.build_qty,
        line_count=len(lines),
        released_at=rev.released_at,
        created_at=rev.created_at,
        row_version=rev.row_version,
    )


@router.put(
    "/boq-revisions/{revision_id}/lines",
    response_model=RevisionSummary,
    summary="Save the draft's lines (grid)",
)
async def save_lines(
    revision_id: uuid.UUID, body: LinesSave, user: Editor, session: SessionDep
) -> RevisionSummary:
    rev = await service.save_lines(session, user, revision_id, body.row_version, body.lines)
    _, lines = await service.revision_lines(session, user, rev.id)
    return RevisionSummary(
        id=rev.id,
        revision=rev.revision,
        status=rev.status,
        build_qty=rev.build_qty,
        line_count=len(lines),
        released_at=rev.released_at,
        created_at=rev.created_at,
        row_version=rev.row_version,
    )


@router.post(
    "/boq-revisions/{revision_id}/release",
    response_model=RevisionSummary,
    summary="Release a draft revision",
)
async def release(
    revision_id: uuid.UUID,
    body: VersionIn,
    user: Annotated[Principal, Depends(require("boq:release"))],
    session: SessionDep,
) -> RevisionSummary:
    rev = await service.release(session, user, revision_id, body.row_version)
    _, lines = await service.revision_lines(session, user, rev.id)
    return RevisionSummary(
        id=rev.id,
        revision=rev.revision,
        status=rev.status,
        build_qty=rev.build_qty,
        line_count=len(lines),
        released_at=rev.released_at,
        created_at=rev.created_at,
        row_version=rev.row_version,
    )


@router.delete("/boq-revisions/{revision_id}", status_code=204, summary="Delete a draft revision")
async def delete_revision(
    revision_id: uuid.UUID, row_version: Version, user: Editor, session: SessionDep
) -> None:
    await service.delete_revision(session, user, revision_id, row_version)


@router.get("/boqs/{boq_id}/compare", response_model=CompareOut, summary="Compare two revisions")
async def compare(
    boq_id: uuid.UUID,
    user: Reader,
    session: SessionDep,
    from_rev: Annotated[str, Query(alias="from", max_length=8)],
    to_rev: Annotated[str, Query(alias="to", max_length=8)],
) -> CompareOut:
    return CompareOut(**await service.compare(session, user, boq_id, from_rev, to_rev))


# ---------------------------------------------------------------- import wizard


def import_out(imp, record, suggested) -> ImportOut:  # type: ignore[no-untyped-def]
    rows = imp.rows or []
    return ImportOut(
        id=imp.id,
        boq_id=imp.boq_id,
        file_id=imp.file_id,
        file_name=record.original_name,
        status=imp.status,
        encoding=imp.encoding,
        delimiter=imp.delimiter,
        sheet=imp.sheet,
        header_row=imp.header_row,
        headers=imp.headers,
        preview_rows=rows[:40],
        total_rows=len(rows),
        mapping=imp.mapping,
        suggested_template_id=suggested,
        result=imp.result,
        error=imp.error,
        revision_id=imp.revision_id,
        row_version=imp.row_version,
    )


@router.get(
    "/boq-import-fields", response_model=list[FieldInfo], summary="Fields a column can map to"
)
async def fields(_: Reader) -> list[FieldInfo]:
    return [FieldInfo(field=f, label=label) for f, label in FIELDS.items()]


@router.post(
    "/boqs/{boq_id}/imports",
    response_model=ImportOut,
    status_code=202,
    summary="Upload a BOQ file (CSV/XLSX)",
)
async def start_import(
    boq_id: uuid.UUID,
    user: Importer,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
) -> ImportOut:
    """Parsing runs as a background job; poll the import until `status` is `parsed`."""
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    imp = await service.start_import(
        session, settings, user, boq_id, content, file.filename or "boq.csv", file.content_type
    )
    imp, record, suggested = await service.get_import(session, user, imp.id)
    return import_out(imp, record, suggested)


@router.get(
    "/boq-imports/{import_id}",
    response_model=ImportOut,
    summary="Import status, preview and validation result",
)
async def get_import(import_id: uuid.UUID, user: Reader, session: SessionDep) -> ImportOut:
    return import_out(*await service.get_import(session, user, import_id))


@router.put(
    "/boq-imports/{import_id}/mapping",
    response_model=ImportOut,
    status_code=202,
    summary="Set the column mapping and validate",
)
async def set_mapping(
    import_id: uuid.UUID, body: MappingIn, user: Importer, session: SessionDep
) -> ImportOut:
    """Validation runs as a background job; poll until `status` is `validated`."""
    await service.set_mapping(
        session,
        user,
        import_id,
        row_version=body.row_version,
        header_row=body.header_row,
        mapping=body.mapping,
        decimal_comma=body.decimal_comma,
        save_template_name=body.save_template_name,
        template_client=body.template_client,
    )
    return import_out(*await service.get_import(session, user, import_id))


@router.get(
    "/boq-imports/{import_id}/template/{template_id}",
    response_model=dict[str, int],
    summary="Mapping from a saved template",
)
async def apply_template(
    import_id: uuid.UUID, template_id: uuid.UUID, user: Reader, session: SessionDep
) -> dict[str, int]:
    return await service.apply_template(session, user, import_id, template_id)


@router.get(
    "/boq-imports/{import_id}/errors.csv",
    summary="Validation report as CSV",
    response_class=Response,
)
async def error_csv(import_id: uuid.UUID, user: Reader, session: SessionDep) -> Response:
    body = await service.error_report(session, user, import_id)
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="boq-import-errors.csv"'},
    )


@router.post(
    "/boq-imports/{import_id}/commit",
    response_model=RevisionSummary,
    summary="Create the revision from a validated import",
)
async def commit(
    import_id: uuid.UUID, body: CommitIn, user: Importer, session: SessionDep
) -> RevisionSummary:
    rev = await service.commit_import(
        session,
        user,
        import_id,
        row_version=body.row_version,
        release_now=body.release,
        build_qty=body.build_qty,
    )
    _, lines = await service.revision_lines(session, user, rev.id)
    return RevisionSummary(
        id=rev.id,
        revision=rev.revision,
        status=rev.status,
        build_qty=rev.build_qty,
        line_count=len(lines),
        released_at=rev.released_at,
        created_at=rev.created_at,
        row_version=rev.row_version,
    )


@router.get(
    "/boq-mapping-templates", response_model=list[TemplateOut], summary="Saved column mappings"
)
async def templates(user: Reader, session: SessionDep) -> list[TemplateOut]:
    return [TemplateOut.model_validate(t) for t in await service.list_templates(session, user)]


@router.delete(
    "/boq-mapping-templates/{template_id}", status_code=204, summary="Delete a saved mapping"
)
async def delete_template(
    template_id: uuid.UUID, row_version: Version, user: Importer, session: SessionDep
) -> None:
    await service.delete_template(session, user, template_id, row_version)
