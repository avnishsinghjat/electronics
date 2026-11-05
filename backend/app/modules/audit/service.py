import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, AuditLog
from app.core.errors import AppError
from app.modules.audit.schemas import AuditEntryOut
from app.modules.auth.models import User
from app.modules.auth.service import Principal


async def list_entries(
    session: AsyncSession,
    user: Principal,
    *,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: AuditAction | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditEntryOut], int]:
    user.require("audit:read")
    if date_from and date_to and date_to < date_from:
        raise AppError("'To' date is before 'from' date", code="invalid_query", status_code=400)
    conds = []
    if actor_id:
        conds.append(AuditLog.actor_id == actor_id)
    if entity_type:
        conds.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conds.append(AuditLog.entity_id == entity_id)
    if action:
        conds.append(AuditLog.action == action.value)
    if date_from:
        conds.append(AuditLog.occurred_at >= datetime.combine(date_from, time.min).astimezone())
    if date_to:
        conds.append(
            AuditLog.occurred_at
            < datetime.combine(date_to + timedelta(days=1), time.min).astimezone()
        )

    total = (
        await session.execute(select(func.count()).select_from(AuditLog).where(*conds))
    ).scalar_one()
    rows = (
        await session.execute(
            select(AuditLog, User.username, User.full_name)
            .outerjoin(User, User.id == AuditLog.actor_id)
            .where(*conds)
            .order_by(AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        AuditEntryOut(
            id=log.id,
            occurred_at=log.occurred_at,
            actor_id=log.actor_id,
            actor_username=username,
            actor_name=full_name,
            action=log.action,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            before=log.before,
            after=log.after,
            changed_fields=log.changed_fields,
            request_id=log.request_id,
        )
        for log, username, full_name in rows
    ]
    return items, int(total)


async def entity_types(session: AsyncSession, user: Principal) -> list[str]:
    user.require("audit:read")
    return list(
        (
            await session.execute(
                select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
            )
        ).scalars()
    )
