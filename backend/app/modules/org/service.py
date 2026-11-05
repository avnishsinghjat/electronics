"""Organisation structure service. All reads apply the caller's division/project scope:
records outside the scope behave as if they do not exist (404, not 403), so scoped users
cannot even confirm that other projects exist."""

import uuid

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.repository import Page, Repository
from app.modules.auth.service import Principal
from app.modules.org.models import Division, Project


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


def scope_projects(stmt: Select[Project], user: Principal) -> Select[Project]:
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


async def list_divisions(session: AsyncSession, user: Principal) -> list[Division]:
    if not user.can("divisions:read"):
        user.require("projects:read")  # project-scoped users still see their divisions
    repo = DivisionRepo(session)
    page = await repo.list(page_size=500, stmt=scope_divisions(repo.base_query(), user))
    return list(page.items)


async def list_projects(
    session: AsyncSession,
    user: Principal,
    *,
    page: int = 1,
    page_size: int = 50,
    sort: str | None = None,
    filters: dict[str, object] | None = None,
) -> Page[Project]:
    user.require("projects:read")
    repo = ProjectRepo(session)
    return await repo.list(
        page=page,
        page_size=page_size,
        sort=sort,
        filters=filters,
        stmt=scope_projects(repo.base_query(), user),
    )


async def get_project(session: AsyncSession, user: Principal, project_id: uuid.UUID) -> Project:
    user.require("projects:read")
    repo = ProjectRepo(session)
    stmt = scope_projects(repo.base_query().where(Project.id == project_id), user)
    project = (await session.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise NotFoundError("Project not found", details={"id": str(project_id)})
    return project


async def can_access_project(session: AsyncSession, user: Principal, project_id: uuid.UUID) -> bool:
    if user.unrestricted:
        return True
    if project_id in user.project_scope:
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
