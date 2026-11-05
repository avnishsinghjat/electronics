import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction
from app.core.db import get_session
from app.modules.audit import service
from app.modules.audit.schemas import AuditPage
from app.modules.auth.deps import require
from app.modules.auth.service import Principal

router = APIRouter(prefix="/audit", tags=["audit"])
Reader = Annotated[Principal, Depends(require("audit:read"))]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=AuditPage, summary="Search the audit log")
async def list_audit(
    user: Reader,
    session: SessionDep,
    actor_id: uuid.UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    action: AuditAction | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> AuditPage:
    items, total = await service.list_entries(
        session,
        user,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return AuditPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/entity-types", response_model=list[str], summary="Entity types present in the log")
async def entity_types(user: Reader, session: SessionDep) -> list[str]:
    return await service.entity_types(session, user)
