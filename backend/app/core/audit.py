"""Audit log: one row per insert, update, soft delete, restore or hard delete of any
business record (classes inheriting :class:`app.core.models.Audited`).

The hook runs inside the same flush and transaction as the change itself, so an
audited change can never be committed without its audit row (rule 5).
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Uuid, event, insert, inspect
from sqlalchemy.orm import Mapped, Session, UOWTransaction, mapped_column

from app.core.context import current_actor_id
from app.core.logging import request_id_var
from app.core.models import Audited, Base, BusinessMixin, JsonB, utcnow


class AuditAction(enum.StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    SOFT_DELETE = "soft_delete"
    RESTORE = "restore"
    DELETE = "delete"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), index=True)
    action: Mapped[str] = mapped_column(String(16))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    changed_fields: Mapped[list[str] | None] = mapped_column(JsonB)
    request_id: Mapped[str | None] = mapped_column(String(64))


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return str(value.normalize()) if value == value.to_integral() else str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID | enum.Enum):
        return str(value.value if isinstance(value, enum.Enum) else value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(v) for v in value]
    return str(value)


def _columns(obj: Any) -> list[str]:
    return [attr.key for attr in inspect(obj).mapper.column_attrs]


def _snapshot(obj: Any) -> dict[str, Any]:
    return {key: _json_value(getattr(obj, key)) for key in _columns(obj)}


def _before_snapshot(obj: Any) -> tuple[dict[str, Any], list[str]]:
    state = inspect(obj)
    before: dict[str, Any] = {}
    changed: list[str] = []
    for key in _columns(obj):
        hist = state.attrs[key].history
        if hist.has_changes() and key not in ("updated_at", "updated_by", "row_version"):
            changed.append(key)
        if hist.deleted:
            before[key] = _json_value(hist.deleted[0])
        elif hist.unchanged:
            before[key] = _json_value(hist.unchanged[0])
        else:
            before[key] = _json_value(getattr(obj, key))
    return before, changed


def _entity_id(obj: Any) -> str:
    identity = inspect(obj).identity
    if identity:
        return ":".join(str(v) for v in identity)
    return str(getattr(obj, "id", ""))


_BEFORE_KEY = "_audit_before_images"


@event.listens_for(Session, "before_flush")
def _stamp_actor(session: Session, _ctx: UOWTransaction, _instances: object) -> None:
    """Stamp actors and capture before-images.

    Before-images must be taken here: during the flush the mapper bumps row_version
    and applies onupdate defaults without recording attribute history.
    """
    actor = current_actor_id.get()
    images: dict[int, tuple[dict[str, Any], list[str]]] = session.info.setdefault(_BEFORE_KEY, {})
    for obj in session.new:
        if isinstance(obj, BusinessMixin):
            if obj.created_by is None:
                obj.created_by = actor
            if obj.updated_by is None:
                obj.updated_by = actor
    for obj in session.dirty:
        if not isinstance(obj, Audited) or not session.is_modified(obj, include_collections=False):
            continue
        images[id(obj)] = _before_snapshot(obj)
        if isinstance(obj, BusinessMixin) and images[id(obj)][1]:
            obj.updated_by = actor


@event.listens_for(Session, "after_flush")
def _write_audit(session: Session, _ctx: UOWTransaction) -> None:
    actor = current_actor_id.get()
    rid = request_id_var.get()
    rows: list[dict[str, Any]] = []
    images: dict[int, tuple[dict[str, Any], list[str]]] = session.info.pop(_BEFORE_KEY, {})

    def add(obj: Any, action: AuditAction, before: Any, after: Any, changed: Any) -> None:
        rows.append(
            {
                "occurred_at": utcnow(),
                "actor_id": actor,
                "action": action.value,
                "entity_type": obj.__tablename__,
                "entity_id": _entity_id(obj),
                "before": before,
                "after": after,
                "changed_fields": changed,
                "request_id": rid,
            }
        )

    for obj in session.new:
        if isinstance(obj, Audited):
            add(obj, AuditAction.INSERT, None, _snapshot(obj), None)

    for obj in session.dirty:
        if not isinstance(obj, Audited) or id(obj) not in images:
            continue
        before, changed = images[id(obj)]
        if not changed:
            continue
        action = AuditAction.UPDATE
        if "is_deleted" in changed:
            deleted = getattr(obj, "is_deleted", False)
            action = AuditAction.SOFT_DELETE if deleted else AuditAction.RESTORE
        add(obj, action, before, _snapshot(obj), changed)

    for obj in session.deleted:
        if isinstance(obj, Audited):
            add(obj, AuditAction.DELETE, _snapshot(obj), None, None)

    if rows:
        session.connection().execute(insert(AuditLog), rows)
