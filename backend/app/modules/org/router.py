import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.org import service
from app.modules.org.schemas import DivisionOut, ProjectOut, ProjectPage

router = APIRouter(tags=["org"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/divisions", response_model=list[DivisionOut], summary="List divisions in scope")
async def list_divisions(
    user: Annotated[Principal, Depends(require("projects:read"))], session: SessionDep
) -> list[DivisionOut]:
    return [DivisionOut.model_validate(d) for d in await service.list_divisions(session, user)]


@router.get("/projects", response_model=ProjectPage, summary="List projects in scope")
async def list_projects(
    user: Annotated[Principal, Depends(require("projects:read"))],
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    sort: str | None = None,
    status: str | None = None,
    division_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> ProjectPage:
    filters: dict[str, object] = {}
    if status:
        filters["status__in"] = status
    if division_id:
        filters["division_id"] = division_id
    if q:
        filters["name__contains"] = q
    result = await service.list_projects(
        session, user, page=page, page_size=page_size, sort=sort, filters=filters
    )
    return ProjectPage(
        items=[ProjectOut.model_validate(p) for p in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/projects/{project_id}", response_model=ProjectOut, summary="Get a project")
async def get_project(
    project_id: uuid.UUID,
    user: Annotated[Principal, Depends(require("projects:read"))],
    session: SessionDep,
) -> ProjectOut:
    return ProjectOut.model_validate(await service.get_project(session, user, project_id))
