import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.org import service
from app.modules.org.schemas import (
    AssemblyCreate,
    AssemblyOut,
    AssemblyUpdate,
    DirectoryUser,
    DivisionCreate,
    DivisionOut,
    DivisionUpdate,
    HistoryEntry,
    ModuleCreate,
    ModuleOut,
    ModuleUpdate,
    ModuleWithAssemblies,
    ProjectClone,
    ProjectCreate,
    ProjectListItem,
    ProjectOut,
    ProjectPage,
    ProjectTree,
    ProjectUpdate,
    StageTemplateOut,
)

router = APIRouter(tags=["org"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
Reader = Annotated[Principal, Depends(require("projects:read"))]
Manager = Annotated[Principal, Depends(require("projects:manage"))]
DivisionManager = Annotated[Principal, Depends(require("divisions:manage"))]
Version = Annotated[int, Query(ge=1, description="row_version the client last saw (409 if stale)")]


# ---------------------------------------------------------------- divisions


@router.get("/divisions", response_model=list[DivisionOut], summary="List divisions in scope")
async def list_divisions(user: Reader, session: SessionDep) -> list[DivisionOut]:
    return [DivisionOut.model_validate(d) for d in await service.list_divisions(session, user)]


@router.post("/divisions", response_model=DivisionOut, status_code=201, summary="Create a division")
async def create_division(
    body: DivisionCreate, user: DivisionManager, session: SessionDep
) -> DivisionOut:
    return DivisionOut.model_validate(await service.create_division(session, user, body))


@router.patch("/divisions/{division_id}", response_model=DivisionOut, summary="Edit a division")
async def update_division(
    division_id: uuid.UUID, body: DivisionUpdate, user: DivisionManager, session: SessionDep
) -> DivisionOut:
    return DivisionOut.model_validate(
        await service.update_division(session, user, division_id, body)
    )


@router.delete("/divisions/{division_id}", status_code=204, summary="Delete an empty division")
async def delete_division(
    division_id: uuid.UUID, row_version: Version, user: DivisionManager, session: SessionDep
) -> None:
    await service.delete_division(session, user, division_id, row_version)


# ---------------------------------------------------------------- projects


@router.get("/projects", response_model=ProjectPage, summary="List projects in scope")
async def list_projects(
    user: Reader,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    sort: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
    division_id: uuid.UUID | None = None,
    project_manager_id: uuid.UUID | None = None,
    client: Annotated[str | None, Query(max_length=100)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    due_after: date | None = None,
    due_before: date | None = None,
    overdue: bool = False,
) -> ProjectPage:
    filters = service.ProjectFilters(
        status=[s for s in status.split(",") if s] if status else None,
        division_id=division_id,
        project_manager_id=project_manager_id,
        client=client,
        q=q,
        due_after=due_after,
        due_before=due_before,
        overdue=overdue,
    )
    items, total = await service.list_projects(
        session, user, page=page, page_size=page_size, sort=sort, filters=filters
    )
    return ProjectPage(
        items=[ProjectListItem(**i) for i in items], total=total, page=page, page_size=page_size
    )


@router.post("/projects", response_model=ProjectOut, status_code=201, summary="Create a project")
async def create_project(body: ProjectCreate, user: Manager, session: SessionDep) -> ProjectOut:
    """The project code comes from document numbering (e.g. PRJ-2026-0004)."""
    return ProjectOut.model_validate(await service.create_project(session, user, body))


@router.get("/projects/{project_id}", response_model=ProjectListItem, summary="Get a project")
async def get_project(project_id: uuid.UUID, user: Reader, session: SessionDep) -> ProjectListItem:
    return ProjectListItem(**await service.get_project_item(session, user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut, summary="Edit a project")
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, user: Manager, session: SessionDep
) -> ProjectOut:
    return ProjectOut.model_validate(await service.update_project(session, user, project_id, body))


@router.delete(
    "/projects/{project_id}", status_code=204, summary="Delete a project without modules"
)
async def delete_project(
    project_id: uuid.UUID, row_version: Version, user: Manager, session: SessionDep
) -> None:
    await service.delete_project(session, user, project_id, row_version)


@router.post(
    "/projects/{project_id}/clone",
    response_model=ProjectOut,
    status_code=201,
    summary="Clone for a repeat order",
)
async def clone_project(
    project_id: uuid.UUID, body: ProjectClone, user: Manager, session: SessionDep
) -> ProjectOut:
    """Copies modules and assemblies (with drawing and KiCad file links) and, with
    `include_boq`, each BOQ's current revision as a new draft revision A."""
    return ProjectOut.model_validate(await service.clone_project(session, user, project_id, body))


@router.get(
    "/projects/{project_id}/tree",
    response_model=ProjectTree,
    summary="Project with modules and assemblies",
)
async def project_tree(project_id: uuid.UUID, user: Reader, session: SessionDep) -> ProjectTree:
    item, modules = await service.project_tree(session, user, project_id)
    return ProjectTree(
        project=ProjectListItem(**item),
        modules=[
            ModuleWithAssemblies(
                **ModuleOut.model_validate(m).model_dump(),
                assemblies=[AssemblyOut.model_validate(a) for a in asm],
            )
            for m, asm in modules
        ],
    )


@router.get(
    "/projects/{project_id}/history",
    response_model=list[HistoryEntry],
    summary="Change history of a project",
)
async def project_history(
    project_id: uuid.UUID,
    user: Annotated[Principal, Depends(require("projects:history"))],
    session: SessionDep,
) -> list[HistoryEntry]:
    return [HistoryEntry(**h) for h in await service.project_history(session, user, project_id)]


# ---------------------------------------------------------------- modules


@router.get(
    "/projects/{project_id}/modules", response_model=list[ModuleOut], summary="Modules of a project"
)
async def list_modules(project_id: uuid.UUID, user: Reader, session: SessionDep) -> list[ModuleOut]:
    return [
        ModuleOut.model_validate(m) for m in await service.list_modules(session, user, project_id)
    ]


@router.post(
    "/projects/{project_id}/modules",
    response_model=ModuleOut,
    status_code=201,
    summary="Add a module",
)
async def create_module(
    project_id: uuid.UUID, body: ModuleCreate, user: Manager, session: SessionDep
) -> ModuleOut:
    return ModuleOut.model_validate(await service.create_module(session, user, project_id, body))


@router.patch("/modules/{module_id}", response_model=ModuleOut, summary="Edit a module")
async def update_module(
    module_id: uuid.UUID, body: ModuleUpdate, user: Manager, session: SessionDep
) -> ModuleOut:
    return ModuleOut.model_validate(await service.update_module(session, user, module_id, body))


@router.delete(
    "/modules/{module_id}", status_code=204, summary="Delete a module without assemblies"
)
async def delete_module(
    module_id: uuid.UUID, row_version: Version, user: Manager, session: SessionDep
) -> None:
    await service.delete_module(session, user, module_id, row_version)


# ---------------------------------------------------------------- assemblies


@router.get(
    "/modules/{module_id}/assemblies",
    response_model=list[AssemblyOut],
    summary="Assemblies of a module",
)
async def list_assemblies(
    module_id: uuid.UUID, user: Reader, session: SessionDep
) -> list[AssemblyOut]:
    return [
        AssemblyOut.model_validate(a)
        for a in await service.list_assemblies(session, user, module_id)
    ]


@router.post(
    "/modules/{module_id}/assemblies",
    response_model=AssemblyOut,
    status_code=201,
    summary="Add a PCB assembly",
)
async def create_assembly(
    module_id: uuid.UUID, body: AssemblyCreate, user: Manager, session: SessionDep
) -> AssemblyOut:
    return AssemblyOut.model_validate(await service.create_assembly(session, user, module_id, body))


@router.get("/assemblies/{assembly_id}", response_model=AssemblyOut, summary="Get an assembly")
async def get_assembly(assembly_id: uuid.UUID, user: Reader, session: SessionDep) -> AssemblyOut:
    return AssemblyOut.model_validate(await service.get_assembly(session, user, assembly_id))


@router.patch("/assemblies/{assembly_id}", response_model=AssemblyOut, summary="Edit an assembly")
async def update_assembly(
    assembly_id: uuid.UUID, body: AssemblyUpdate, user: Manager, session: SessionDep
) -> AssemblyOut:
    """Drawing and KiCad file ids must be files attached to this assembly."""
    return AssemblyOut.model_validate(
        await service.update_assembly(session, user, assembly_id, body)
    )


@router.delete("/assemblies/{assembly_id}", status_code=204, summary="Delete an assembly")
async def delete_assembly(
    assembly_id: uuid.UUID, row_version: Version, user: Manager, session: SessionDep
) -> None:
    await service.delete_assembly(session, user, assembly_id, row_version)


# ---------------------------------------------------------------- lookups


@router.get(
    "/stage-templates", response_model=list[StageTemplateOut], summary="Production stage templates"
)
async def stage_templates(user: Reader, session: SessionDep) -> list[StageTemplateOut]:
    return [
        StageTemplateOut.model_validate(t)
        for t in await service.list_stage_templates(session, user)
    ]


@router.get(
    "/directory/users", response_model=list[DirectoryUser], summary="Active staff for pickers"
)
async def directory(
    user: Annotated[Principal, Depends(require("directory:read"))], session: SessionDep
) -> list[DirectoryUser]:
    return [DirectoryUser(**u) for u in await service.directory(session, user)]
