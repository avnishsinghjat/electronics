import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.parts import service
from app.modules.parts.schemas import PartCreate, PartOut, PartStockSettings

router = APIRouter(prefix="/parts", tags=["parts"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[PartOut], summary="Search the part master (MPN autocomplete)")
async def search(
    user: Annotated[Principal, Depends(require("parts:read"))],
    session: SessionDep,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PartOut]:
    return [PartOut.model_validate(p) for p in await service.search(session, user, q, limit)]


@router.post("", response_model=PartOut, status_code=201, summary="Create a part")
async def create(
    body: PartCreate,
    user: Annotated[Principal, Depends(require("parts:manage"))],
    session: SessionDep,
) -> PartOut:
    return PartOut.model_validate(await service.create(session, user, body))


@router.patch("/{part_id}", response_model=PartOut, summary="Set minimum stock and MSL level")
async def update_stock_settings(
    part_id: uuid.UUID,
    body: PartStockSettings,
    user: Annotated[Principal, Depends(require("parts:manage"))],
    session: SessionDep,
) -> PartOut:
    return PartOut.model_validate(await service.update_stock_settings(session, user, part_id, body))
