"""Generic async repository: get, paginated list with whitelisted filters and sorting,
create, optimistic-locked update, soft delete and restore.

Filter keys use ``field`` or ``field__op`` where op is one of
``eq, ne, in, contains, gte, lte, isnull``. Only fields listed in ``filterable`` /
``sortable`` are accepted; anything else is a 400 so clients cannot probe columns.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.models import BusinessMixin

MAX_PAGE_SIZE = 500
_OPS = {"eq", "ne", "in", "contains", "gte", "lte", "isnull"}
_IMMUTABLE = {"id", "created_at", "created_by", "row_version", "is_deleted"}


@dataclass(frozen=True)
class Page[T]:
    items: Sequence[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


class InvalidQueryError(AppError):
    status_code = 400
    code = "invalid_query"


def check_version(obj: BusinessMixin, expected_version: int) -> None:
    if obj.row_version != expected_version:
        raise ConflictError(
            "This record was changed by someone else. Reload and try again.",
            code="stale_row_version",
            details={
                "expected_row_version": expected_version,
                "current_row_version": obj.row_version,
            },
        )


class Repository[M: BusinessMixin]:
    model: type[M]
    filterable: ClassVar[frozenset[str]] = frozenset()
    sortable: ClassVar[frozenset[str]] = frozenset({"created_at", "updated_at"})
    default_sort: ClassVar[str] = "-created_at"
    entity_label: ClassVar[str] = "Record"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def base_query(self, *, include_deleted: bool = False) -> Select[M]:
        stmt = select(self.model)
        if not include_deleted:
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    async def get(self, id_: uuid.UUID, *, include_deleted: bool = False) -> M:
        obj = await self.session.get(self.model, id_)
        if obj is None or (obj.is_deleted and not include_deleted):
            raise NotFoundError(f"{self.entity_label} not found", details={"id": str(id_)})
        return obj

    def _column(self, name: str, allowed: frozenset[str], kind: str) -> Any:
        if name not in allowed:
            raise InvalidQueryError(
                f"Cannot {kind} by '{name}'", details={"allowed": sorted(allowed)}
            )
        return getattr(self.model, name)

    def _filter_clause(self, key: str, value: Any) -> ColumnElement[bool]:
        field, _, op = key.partition("__")
        op = op or "eq"
        if op not in _OPS:
            raise InvalidQueryError(
                f"Unknown filter operator '{op}'", details={"allowed": sorted(_OPS)}
            )
        col = self._column(field, self.filterable, "filter")
        match op:
            case "eq":
                return col == value  # type: ignore[no-any-return]
            case "ne":
                return col != value  # type: ignore[no-any-return]
            case "in":
                values = value if isinstance(value, list | tuple | set) else str(value).split(",")
                return col.in_(list(values))  # type: ignore[no-any-return]
            case "contains":
                escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                return col.ilike(f"%{escaped}%", escape="\\")  # type: ignore[no-any-return]
            case "gte":
                return col >= value  # type: ignore[no-any-return]
            case "lte":
                return col <= value  # type: ignore[no-any-return]
            case _:  # isnull
                truthy = value if isinstance(value, bool) else str(value).lower() in {"1", "true"}
                return col.is_(None) if truthy else col.is_not(None)  # type: ignore[no-any-return]

    async def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        sort: str | None = None,
        filters: Mapping[str, Any] | None = None,
        include_deleted: bool = False,
        stmt: Select[M] | None = None,
    ) -> Page[M]:
        if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise InvalidQueryError(f"page must be >= 1 and page_size 1..{MAX_PAGE_SIZE}")
        query = stmt if stmt is not None else self.base_query(include_deleted=include_deleted)
        for key, value in (filters or {}).items():
            query = query.where(self._filter_clause(key, value))

        total = (
            await self.session.execute(
                select(func.count()).select_from(query.order_by(None).subquery())
            )
        ).scalar_one()

        order = []
        for part in (sort or self.default_sort).split(","):
            name = part.strip()
            if not name:
                continue
            desc = name.startswith("-")
            col = self._column(name.lstrip("-+"), self.sortable, "sort")
            order.append(col.desc() if desc else col.asc())
        order.append(self.model.id.asc())  # deterministic tie-break
        rows = (
            (
                await self.session.execute(
                    query.order_by(*order).offset((page - 1) * page_size).limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return Page(items=rows, total=total, page=page, page_size=page_size)

    async def create(self, **values: Any) -> M:
        obj = self.model(**values)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: M, values: Mapping[str, Any], *, expected_version: int) -> M:
        check_version(obj, expected_version)
        for key, value in values.items():
            if key in _IMMUTABLE or not hasattr(self.model, key):
                raise InvalidQueryError(f"Field '{key}' cannot be updated")
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def soft_delete(self, obj: M, *, expected_version: int) -> M:
        check_version(obj, expected_version)
        obj.is_deleted = True
        await self.session.flush()
        return obj

    async def restore(self, obj: M, *, expected_version: int) -> M:
        check_version(obj, expected_version)
        obj.is_deleted = False
        await self.session.flush()
        return obj
