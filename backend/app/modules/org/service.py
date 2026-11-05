"""Organisation structure service: divisions, projects, modules and PCB assemblies.

All reads and writes apply the caller's division/project scope: records outside the scope
behave as if they do not exist (404, not 403), so scoped users cannot even confirm that
other projects exist. Every write checks the permission here as well as in the router.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.files import StoredFile
from app.core.numbering import next_number
from app.core.repository import Repository, check_version
from app.modules.auth.models import User
from app.modules.auth.service import Principal
from app.modules.org.models import Division, Module, PcbAssembly, Project, ProjectStatus
from app.modules.org.schemas import (
    AssemblyCreate,
    AssemblyUpdate,
    DivisionCreate,
    DivisionUpdate,
    ModuleCreate,
    ModuleUpdate,
    ProjectClone,
    ProjectCreate,
    ProjectUpdate,
)
from app.modules.production.models import StageTemplate

OPEN_STATUSES = (ProjectStatus.DRAFT.value, ProjectStatus.ACTIVE.value, ProjectStatus.ON_HOLD.value)


class DivisionRepo(Repository[Division]):
    model = Division
    filterable = frozenset({"code", "name", "is_sample"})
    sortable = frozenset({"code", "name", "created_at"})
    default_sort = "name"
    entity_label = "Division"


class ProjectRepo(Repository[Project]):
    model = Project
    filterable = frozenset(
        {"status", "division_id", "client_name", "project_manager_id", "due_date", "code", "name"}
    )
    sortable = frozenset(
        {"code", "name", "client_name", "status", "due_date", "start_date", "created_at"}
    )
    default_sort = "-created_at"
    entity_label = "Project"


# ---------------------------------------------------------------- scoping


def scope_projects(stmt: Select[Any], user: Principal) -> Select[Any]:
    if user.unrestricted:
        return stmt
    return stmt.where(
        or_(Project.id.in_(user.project_scope), Project.division_id.in_(user.division_scope))
    )


def scope_divisions(stmt: Select[Division], user: Principal) -> Select[Division]:
    if user.unrestricted:
        return stmt
    # A project-scoped user sees the divisions that contain their projects.
    via_projects = select(Project.division_id).where(Project.id.in_(user.project_scope))
    return stmt.where(or_(Division.id.in_(user.division_scope), Division.id.in_(via_projects)))


def division_in_scope(user: Principal, division_id: uuid.UUID) -> bool:
    return user.unrestricted or division_id in user.division_scope


async def can_access_project(session: AsyncSession, user: Principal, project_id: uuid.UUID) -> bool:
    if user.unrestricted or project_id in user.project_scope:
        return True
    division = (
        await session.execute(select(Project.division_id).where(Project.id == project_id))
    ).scalar_one_or_none()
    return division is not None and division in user.division_scope


async def scope_target_exists(session: AsyncSession, scope_type: str, scope_id: uuid.UUID) -> bool:
    found: Division | Project | None = (
        await session.get(Division, scope_id)
        if scope_type == "division"
        else await session.get(Project, scope_id)
    )
    return found is not None and not found.is_deleted


# ---------------------------------------------------------------- divisions


async def list_divisions(session: AsyncSession, user: Principal) -> list[Division]:
    if not user.can("divisions:read"):
        user.require("projects:read")  # project-scoped users still see their divisions
    repo = DivisionRepo(session)
    page = await repo.list(page_size=500, stmt=scope_divisions(repo.base_query(), user))
    return list(page.items)


async def _division(session: AsyncSession, user: Principal, division_id: uuid.UUID) -> Division:
    division = await DivisionRepo(session).get(division_id)
    if not user.unrestricted and division.id not in {
        d.id for d in await list_divisions(session, user)
    }:
        raise NotFoundError("Division not found", details={"id": str(division_id)})
    return division


async def create_division(session: AsyncSession, user: Principal, data: DivisionCreate) -> Division:
    user.require("divisions:manage")
    if not user.unrestricted:
        raise AppError(
            "Only users without a division/project restriction can create divisions",
            code="forbidden",
            status_code=403,
        )
    division = await DivisionRepo(session).create(**data.model_dump())
    await session.commit()
    return division


async def update_division(
    session: AsyncSession, user: Principal, division_id: uuid.UUID, data: DivisionUpdate
) -> Division:
    user.require("divisions:manage")
    division = await _division(session, user, division_id)
    values = data.model_dump(exclude_unset=True, exclude={"row_version"})
    await DivisionRepo(session).update(division, values, expected_version=data.row_version)
    await session.commit()
    return division


async def delete_division(
    session: AsyncSession, user: Principal, division_id: uuid.UUID, row_version: int
) -> None:
    user.require("divisions:manage")
    division = await _division(session, user, division_id)
    live = (
        await session.execute(
            select(func.count()).where(
                Project.division_id == division.id, Project.is_deleted.is_(False)
            )
        )
    ).scalar_one()
    if live:
        raise ConflictError(
            "Move or delete this division's projects first",
            code="has_children",
            details={"projects": live},
        )
    await DivisionRepo(session).soft_delete(division, expected_version=row_version)
    await session.commit()


# ---------------------------------------------------------------- projects


@dataclass(frozen=True)
class ProjectFilters:
    status: list[str] | None = None
    division_id: uuid.UUID | None = None
    project_manager_id: uuid.UUID | None = None
    client: str | None = None
    q: str | None = None
    due_after: date | None = None
    due_before: date | None = None
    overdue: bool = False


_SORTS = {
    "code": Project.code,
    "name": Project.name,
    "client_name": Project.client_name,
    "status": Project.status,
    "due_date": Project.due_date,
    "start_date": Project.start_date,
    "created_at": Project.created_at,
}


def _project_listing() -> Select[Any]:
    modules = (
        select(func.count())
        .where(Module.project_id == Project.id, Module.is_deleted.is_(False))
        .correlate(Project)
        .scalar_subquery()
    )
    return (
        select(Project, Division.code, Division.name, User.full_name, modules)
        .join(Division, Division.id == Project.division_id)
        .outerjoin(User, User.id == Project.project_manager_id)
        .where(Project.is_deleted.is_(False))
    )


def _escape_like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _row_to_item(row: Any) -> dict[str, Any]:
    project, division_code, division_name, pm_name, module_count = row
    return {
        **{c.key: getattr(project, c.key) for c in Project.__table__.columns},
        "division_code": division_code,
        "division_name": division_name,
        "project_manager_name": pm_name,
        "module_count": int(module_count or 0),
    }


async def list_projects(
    session: AsyncSession,
    user: Principal,
    *,
    page: int = 1,
    page_size: int = 50,
    sort: str | None = None,
    filters: ProjectFilters | None = None,
) -> tuple[list[dict[str, Any]], int]:
    user.require("projects:read")
    f = filters or ProjectFilters()
    stmt = scope_projects(_project_listing(), user)
    if f.status:
        stmt = stmt.where(Project.status.in_(f.status))
    if f.division_id:
        stmt = stmt.where(Project.division_id == f.division_id)
    if f.project_manager_id:
        stmt = stmt.where(Project.project_manager_id == f.project_manager_id)
    if f.client:
        stmt = stmt.where(Project.client_name.ilike(_escape_like(f.client), escape="\\"))
    if f.q:
        like = _escape_like(f.q)
        stmt = stmt.where(
            or_(Project.name.ilike(like, escape="\\"), Project.code.ilike(like, escape="\\"))
        )
    if f.due_after:
        stmt = stmt.where(Project.due_date >= f.due_after)
    if f.due_before:
        stmt = stmt.where(Project.due_date <= f.due_before)
    if f.overdue:
        stmt = stmt.where(and_(Project.due_date < date.today(), Project.status.in_(OPEN_STATUSES)))

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    order: list[Any] = []
    for part in (sort or "-created_at").split(","):
        name = part.strip()
        col = _SORTS.get(name.lstrip("-"))
        if col is None:
            raise AppError(
                f"Cannot sort by '{name}'",
                code="invalid_query",
                status_code=400,
                details={"allowed": sorted(_SORTS)},
            )
        order.append(col.desc().nulls_last() if name.startswith("-") else col.asc().nulls_last())
    order.append(Project.id.asc())
    rows = (
        await session.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))
    ).all()
    return [_row_to_item(r) for r in rows], int(total)


async def get_project(session: AsyncSession, user: Principal, project_id: uuid.UUID) -> Project:
    user.require("projects:read")
    stmt = scope_projects(
        select(Project).where(Project.id == project_id, Project.is_deleted.is_(False)), user
    )
    project: Project | None = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise NotFoundError("Project not found", details={"id": str(project_id)})
    return project


async def get_project_item(
    session: AsyncSession, user: Principal, project_id: uuid.UUID
) -> dict[str, Any]:
    await get_project(session, user, project_id)
    row = (await session.execute(_project_listing().where(Project.id == project_id))).one()
    return _row_to_item(row)


async def _check_manager(session: AsyncSession, manager_id: uuid.UUID | None) -> None:
    if manager_id is None:
        return
    manager = await session.get(User, manager_id)
    if manager is None or not manager.is_active or manager.is_deleted:
        raise AppError(
            "Project manager must be an active user", code="invalid_manager", status_code=422
        )


async def create_project(session: AsyncSession, user: Principal, data: ProjectCreate) -> Project:
    user.require("projects:manage")
    division = await DivisionRepo(session).get(data.division_id)
    if not division_in_scope(user, division.id):
        raise NotFoundError("Division not found", details={"id": str(data.division_id)})
    await _check_manager(session, data.project_manager_id)
    project = Project(
        **data.model_dump(exclude={"status"}),
        status=data.status.value,
        code=await next_number(session, "PRJ"),
    )
    session.add(project)
    await session.flush()
    await session.commit()
    return project


async def update_project(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, data: ProjectUpdate
) -> Project:
    user.require("projects:manage")
    project = await get_project(session, user, project_id)
    check_version(project, data.row_version)
    values = data.model_dump(exclude_unset=True, exclude={"row_version"})
    if "status" in values and values["status"] is not None:
        values["status"] = ProjectStatus(values["status"]).value
    if values.get("division_id"):
        target = await DivisionRepo(session).get(values["division_id"])
        if not division_in_scope(user, target.id):
            raise NotFoundError("Division not found", details={"id": str(target.id)})
    if "project_manager_id" in values:
        await _check_manager(session, values["project_manager_id"])
    start = values.get("start_date", project.start_date)
    due = values.get("due_date", project.due_date)
    if start and due and due < start:
        raise AppError(
            "Due date must not be before the start date", code="invalid_dates", status_code=422
        )
    for key in ("name", "client_name", "division_id", "status"):
        if key in values and values[key] is None:
            values.pop(key)
    await ProjectRepo(session).update(project, values, expected_version=data.row_version)
    await session.commit()
    return project


async def delete_project(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, row_version: int
) -> None:
    user.require("projects:manage")
    project = await get_project(session, user, project_id)
    live = (
        await session.execute(
            select(func.count()).where(
                Module.project_id == project.id, Module.is_deleted.is_(False)
            )
        )
    ).scalar_one()
    if live:
        raise ConflictError(
            "Delete the project's modules first", code="has_children", details={"modules": live}
        )
    await ProjectRepo(session).soft_delete(project, expected_version=row_version)
    await session.commit()


# ---------------------------------------------------------------- modules and assemblies


async def list_modules(
    session: AsyncSession, user: Principal, project_id: uuid.UUID
) -> list[Module]:
    await get_project(session, user, project_id)
    rows = await session.execute(
        select(Module)
        .where(Module.project_id == project_id, Module.is_deleted.is_(False))
        .order_by(Module.code)
    )
    return list(rows.scalars())


async def get_module(session: AsyncSession, user: Principal, module_id: uuid.UUID) -> Module:
    user.require("projects:read")
    module = await session.get(Module, module_id)
    if (
        module is None
        or module.is_deleted
        or not await can_access_project(session, user, module.project_id)
    ):
        raise NotFoundError("Module not found", details={"id": str(module_id)})
    await get_project(session, user, module.project_id)  # project itself must be live
    return module


async def create_module(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, data: ModuleCreate
) -> Module:
    user.require("projects:manage")
    await get_project(session, user, project_id)
    module = Module(project_id=project_id, **data.model_dump())
    session.add(module)
    await session.flush()
    await session.commit()
    return module


async def update_module(
    session: AsyncSession, user: Principal, module_id: uuid.UUID, data: ModuleUpdate
) -> Module:
    user.require("projects:manage")
    module = await get_module(session, user, module_id)
    values = {
        k: v
        for k, v in data.model_dump(exclude_unset=True, exclude={"row_version"}).items()
        if v is not None or k == "description"
    }
    check_version(module, data.row_version)
    for key, value in values.items():
        setattr(module, key, value)
    await session.flush()
    await session.commit()
    return module


async def delete_module(
    session: AsyncSession, user: Principal, module_id: uuid.UUID, row_version: int
) -> None:
    user.require("projects:manage")
    module = await get_module(session, user, module_id)
    check_version(module, row_version)
    live = (
        await session.execute(
            select(func.count()).where(
                PcbAssembly.module_id == module.id, PcbAssembly.is_deleted.is_(False)
            )
        )
    ).scalar_one()
    if live:
        raise ConflictError(
            "Delete the module's assemblies first",
            code="has_children",
            details={"assemblies": live},
        )
    module.is_deleted = True
    await session.flush()
    await session.commit()


async def list_assemblies(
    session: AsyncSession, user: Principal, module_id: uuid.UUID
) -> list[PcbAssembly]:
    await get_module(session, user, module_id)
    rows = await session.execute(
        select(PcbAssembly)
        .where(PcbAssembly.module_id == module_id, PcbAssembly.is_deleted.is_(False))
        .order_by(PcbAssembly.code, PcbAssembly.revision)
    )
    return list(rows.scalars())


async def get_assembly(
    session: AsyncSession, user: Principal, assembly_id: uuid.UUID
) -> PcbAssembly:
    user.require("projects:read")
    assembly = await session.get(PcbAssembly, assembly_id)
    if assembly is None or assembly.is_deleted:
        raise NotFoundError("Assembly not found", details={"id": str(assembly_id)})
    try:
        await get_module(session, user, assembly.module_id)
    except NotFoundError as exc:
        raise NotFoundError("Assembly not found", details={"id": str(assembly_id)}) from exc
    return assembly


async def _validate_assembly_refs(
    session: AsyncSession, assembly_id: uuid.UUID | None, values: dict[str, Any]
) -> None:
    template_id = values.get("stage_template_id")
    if template_id is not None:
        template = await session.get(StageTemplate, template_id)
        if template is None or template.is_deleted:
            raise AppError("Stage template not found", code="invalid_reference", status_code=422)
    for key in ("kicad_project_file_id", "assembly_drawing_file_id"):
        file_id = values.get(key)
        if file_id is None:
            continue
        record = await session.get(StoredFile, file_id)
        if (
            record is None
            or record.is_deleted
            or record.ref_type != "assembly"
            or assembly_id is None
            or record.ref_id != assembly_id
        ):
            raise AppError(
                "The file must be attached to this assembly first",
                code="invalid_reference",
                status_code=422,
                details={"field": key},
            )


async def create_assembly(
    session: AsyncSession, user: Principal, module_id: uuid.UUID, data: AssemblyCreate
) -> PcbAssembly:
    user.require("projects:manage")
    await get_module(session, user, module_id)
    values = data.model_dump()
    if values.get("kicad_project_file_id") or values.get("assembly_drawing_file_id"):
        raise AppError(
            "Attach files after creating the assembly", code="invalid_reference", status_code=422
        )
    await _validate_assembly_refs(session, None, values)
    if values.get("stage_template_id") is None:
        values["stage_template_id"] = (
            (
                await session.execute(
                    select(StageTemplate.id).where(
                        StageTemplate.is_default.is_(True), StageTemplate.is_deleted.is_(False)
                    )
                )
            )
            .scalars()
            .first()
        )
    values = {k: v for k, v in values.items() if v is not None}
    assembly = PcbAssembly(module_id=module_id, **values)
    session.add(assembly)
    await session.flush()
    await session.commit()
    return assembly


async def update_assembly(
    session: AsyncSession, user: Principal, assembly_id: uuid.UUID, data: AssemblyUpdate
) -> PcbAssembly:
    user.require("projects:manage")
    assembly = await get_assembly(session, user, assembly_id)
    check_version(assembly, data.row_version)
    values = data.model_dump(exclude_unset=True, exclude={"row_version"})
    await _validate_assembly_refs(session, assembly.id, values)
    for key in ("code", "board_name", "revision", "qty_per_module", "layer_count"):
        if key in values and values[key] is None:
            values.pop(key)
    for key, value in values.items():
        setattr(assembly, key, value)
    await session.flush()
    await session.commit()
    return assembly


async def delete_assembly(
    session: AsyncSession, user: Principal, assembly_id: uuid.UUID, row_version: int
) -> None:
    user.require("projects:manage")
    assembly = await get_assembly(session, user, assembly_id)
    check_version(assembly, row_version)
    assembly.is_deleted = True
    await session.flush()
    await session.commit()


async def project_tree(
    session: AsyncSession, user: Principal, project_id: uuid.UUID
) -> tuple[dict[str, Any], list[tuple[Module, list[PcbAssembly]]]]:
    item = await get_project_item(session, user, project_id)
    modules = await list_modules(session, user, project_id)
    assemblies = (
        (
            await session.execute(
                select(PcbAssembly)
                .where(
                    PcbAssembly.module_id.in_([m.id for m in modules]),
                    PcbAssembly.is_deleted.is_(False),
                )
                .order_by(PcbAssembly.code, PcbAssembly.revision)
            )
        )
        .scalars()
        .all()
    )
    by_module: dict[uuid.UUID, list[PcbAssembly]] = {}
    for a in assemblies:
        by_module.setdefault(a.module_id, []).append(a)
    return item, [(m, by_module.get(m.id, [])) for m in modules]


async def list_stage_templates(session: AsyncSession, user: Principal) -> list[StageTemplate]:
    user.require("projects:read")
    rows = await session.execute(
        select(StageTemplate)
        .where(StageTemplate.is_deleted.is_(False))
        .order_by(StageTemplate.is_default.desc(), StageTemplate.name)
    )
    return list(rows.scalars())


# ---------------------------------------------------------------- clone


async def _copy_file(
    session: AsyncSession, file_id: uuid.UUID | None, new_ref: uuid.UUID
) -> uuid.UUID | None:
    """Content-addressed store: copying a file is a new metadata row over the same bytes."""
    if file_id is None:
        return None
    src = await session.get(StoredFile, file_id)
    if src is None or src.is_deleted:
        return None
    copy = StoredFile(
        sha256=src.sha256,
        original_name=src.original_name,
        mime=src.mime,
        size_bytes=src.size_bytes,
        storage_path=src.storage_path,
        uploaded_by=src.uploaded_by,
        ref_type="assembly",
        ref_id=new_ref,
        exif_json=src.exif_json,
        captured_at=src.captured_at,
    )
    session.add(copy)
    await session.flush()
    return copy.id


async def clone_project(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, data: ProjectClone
) -> Project:
    """Repeat order: copies the project structure (modules, assemblies and their drawing /
    KiCad file links) and optionally each BOQ's current revision. Never copies procurement,
    production or QC records."""
    user.require("projects:manage")
    source = await get_project(session, user, project_id)
    clone = Project(
        division_id=source.division_id,
        code=await next_number(session, "PRJ"),
        name=data.name,
        client_name=source.client_name,
        client_po_ref=data.client_po_ref,
        start_date=data.start_date,
        due_date=data.due_date,
        status=ProjectStatus.DRAFT.value,
        project_manager_id=source.project_manager_id,
        notes=f"Cloned from {source.code}." + (f"\n{source.notes}" if source.notes else ""),
    )
    if clone.start_date and clone.due_date and clone.due_date < clone.start_date:
        raise AppError(
            "Due date must not be before the start date", code="invalid_dates", status_code=422
        )
    session.add(clone)
    await session.flush()

    module_map: dict[uuid.UUID, uuid.UUID] = {}
    assembly_map: dict[uuid.UUID, uuid.UUID] = {}
    for module in await list_modules(session, user, source.id):
        new_module = Module(
            project_id=clone.id,
            code=module.code,
            name=module.name,
            qty_to_deliver=module.qty_to_deliver,
            description=module.description,
        )
        session.add(new_module)
        await session.flush()
        module_map[module.id] = new_module.id
        assemblies = (
            (
                await session.execute(
                    select(PcbAssembly).where(
                        PcbAssembly.module_id == module.id, PcbAssembly.is_deleted.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
        for a in assemblies:
            new_a = PcbAssembly(
                module_id=new_module.id,
                code=a.code,
                board_name=a.board_name,
                revision=a.revision,
                qty_per_module=a.qty_per_module,
                layer_count=a.layer_count,
                size_x_mm=a.size_x_mm,
                size_y_mm=a.size_y_mm,
                finish=a.finish,
                stage_template_id=a.stage_template_id,
                notes=a.notes,
            )
            session.add(new_a)
            await session.flush()
            new_a.kicad_project_file_id = await _copy_file(
                session, a.kicad_project_file_id, new_a.id
            )
            new_a.assembly_drawing_file_id = await _copy_file(
                session, a.assembly_drawing_file_id, new_a.id
            )
            assembly_map[a.id] = new_a.id

    if data.include_boq:
        from app.modules.boq import service as boq_service  # local import: boq depends on org

        await boq_service.copy_boqs_for_clone(
            session, source.id, clone.id, module_map, assembly_map
        )
    await session.flush()
    await session.commit()
    return clone


# ---------------------------------------------------------------- history


async def project_history(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, *, limit: int = 200
) -> list[dict[str, Any]]:
    """Audit entries for the project and everything under it (modules, assemblies, files),
    newest first, with a human label for each record."""
    from app.core.audit import AuditLog  # core model; local import keeps module deps explicit

    user.require("projects:history")
    project = await get_project(session, user, project_id)
    labels: dict[str, str] = {str(project.id): f"Project {project.code}"}
    modules = (
        (await session.execute(select(Module).where(Module.project_id == project.id)))
        .scalars()
        .all()
    )
    for m in modules:
        labels[str(m.id)] = f"Module {m.code}"
    assemblies = (
        (
            await session.execute(
                select(PcbAssembly).where(PcbAssembly.module_id.in_([m.id for m in modules]))
            )
        )
        .scalars()
        .all()
    )
    for a in assemblies:
        labels[str(a.id)] = f"Assembly {a.code} rev {a.revision}"
    owners = [project.id, *[m.id for m in modules], *[a.id for a in assemblies]]
    files = (
        (await session.execute(select(StoredFile).where(StoredFile.ref_id.in_(owners))))
        .scalars()
        .all()
    )
    for f in files:
        labels[str(f.id)] = f"File {f.original_name}"

    rows = (
        await session.execute(
            select(AuditLog, User.full_name)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .where(
                AuditLog.entity_type.in_(["projects", "modules", "pcb_assemblies", "files"]),
                AuditLog.entity_id.in_(list(labels)),
            )
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": log.id,
            "occurred_at": log.occurred_at,
            "actor_name": name,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "label": labels.get(log.entity_id, log.entity_type),
            "changed_fields": log.changed_fields,
        }
        for log, name in rows
    ]


async def directory(session: AsyncSession, user: Principal) -> list[dict[str, Any]]:
    """Active staff for pickers (project manager etc.). Names only, no contact details."""
    from app.modules.auth.models import UserRole

    user.require("directory:read")
    users = (
        (
            await session.execute(
                select(User)
                .where(User.is_active.is_(True), User.is_deleted.is_(False))
                .order_by(User.full_name)
            )
        )
        .scalars()
        .all()
    )
    roles = (
        await session.execute(
            select(UserRole.user_id, UserRole.role).where(UserRole.is_deleted.is_(False))
        )
    ).all()
    by_user: dict[uuid.UUID, list[str]] = {}
    for uid, role in roles:
        by_user.setdefault(uid, []).append(role)
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "roles": sorted(by_user.get(u.id, [])),
        }
        for u in users
    ]


async def scoped_project_ids(session: AsyncSession, user: Principal) -> set[uuid.UUID] | None:
    """Ids of the projects a scoped user may see; None when the user is unrestricted."""
    if user.unrestricted:
        return None
    rows = await session.execute(scope_projects(select(Project.id), user))
    return set(rows.scalars().all())


async def project_labels(
    session: AsyncSession, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str]]:
    """Project id -> (code, name), for listings of other modules."""
    wanted = set(ids)
    if not wanted:
        return {}
    rows = await session.execute(
        select(Project.id, Project.code, Project.name).where(Project.id.in_(wanted))
    )
    return {pid: (code, name) for pid, code, name in rows.all()}
