"""BOQ service: BOQs per project (optionally per module/assembly), revisions A, B, C...,
line editing on draft revisions, release, revision compare, and the import wizard.

Rules:
* Only draft revisions are editable; released and superseded revisions are read-only.
* At most one revision is released per BOQ; releasing supersedes the previous one.
* At most one draft at a time per BOQ (finish or delete it before starting another).
* Each line keeps a stable ``line_key`` across revisions so revisions can be diffed.
* Line quantities and status come from ``app.modules.boq.status`` (single source of truth).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.files import StoredFile, store_file
from app.core.ids import uuid7
from app.core.jobs import enqueue
from app.core.models import utcnow
from app.core.repository import check_version
from app.modules.auth.service import Principal
from app.modules.boq import importer
from app.modules.boq.models import (
    Boq,
    BoqImport,
    BoqLine,
    BoqMappingTemplate,
    BoqRevision,
    ImportStatus,
    RevisionStatus,
)
from app.modules.boq.schemas import BoqCreate, BuildUpdate, LineIn
from app.modules.boq.status import LineQuantities, quantities, required_qty
from app.modules.org import service as org
from app.modules.org.models import Module, PcbAssembly, Project
from app.modules.parts import service as parts
from app.modules.procurement import quantities as procurement
from app.modules.settings.models import DEFAULT_ATTRITION, CompanySettings

_LINE_FIELDS = (
    "line_key",
    "line_no",
    "part_id",
    "ref_des",
    "qty_per_unit",
    "mpn",
    "manufacturer",
    "description",
    "value",
    "package",
    "category",
    "unit",
    "dnp",
    "attrition_pct",
    "attrition_override",
    "unit_price",
    "preferred_vendor_id",
    "notes",
)


# ---------------------------------------------------------------- helpers


def next_revision_letter(existing: list[str]) -> str:
    """A, B, ... Z, AA, AB ... (spreadsheet-style)."""
    if not existing:
        return "A"

    def to_int(s: str) -> int:
        n = 0
        for ch in s:
            n = n * 26 + (ord(ch) - 64)
        return n

    def to_letters(n: int) -> str:
        out = ""
        while n:
            n, rem = divmod(n - 1, 26)
            out = chr(65 + rem) + out
        return out

    return to_letters(max(to_int(r) for r in existing) + 1)


def _rev_order(rev: str) -> tuple[int, str]:
    return (len(rev), rev)  # A < B < ... < Z < AA


async def _company_attrition(session: AsyncSession) -> dict[str, float]:
    company = (await session.execute(select(CompanySettings))).scalar_one_or_none()
    return (
        dict(company.attrition_defaults)
        if company and company.attrition_defaults
        else dict(DEFAULT_ATTRITION)
    )


def _category_rate(rates: dict[str, Any], category: str | None) -> Decimal:
    if category and category in rates:
        return Decimal(str(rates[category]))
    return Decimal(0)


async def _boq(session: AsyncSession, user: Principal, boq_id: uuid.UUID) -> Boq:
    user.require("boq:read")
    boq = await session.get(Boq, boq_id)
    if boq is None or boq.is_deleted:
        raise NotFoundError("BOQ not found", details={"id": str(boq_id)})
    try:
        await org.get_project(session, user, boq.project_id)
    except NotFoundError as exc:
        raise NotFoundError("BOQ not found", details={"id": str(boq_id)}) from exc
    return boq


async def _revision(
    session: AsyncSession, user: Principal, revision_id: uuid.UUID
) -> tuple[Boq, BoqRevision]:
    rev = await session.get(BoqRevision, revision_id)
    if rev is None or rev.is_deleted:
        raise NotFoundError("Revision not found", details={"id": str(revision_id)})
    boq = await _boq(session, user, rev.boq_id)
    return boq, rev


def _require_draft(rev: BoqRevision) -> None:
    if rev.status != RevisionStatus.DRAFT.value:
        raise ConflictError(
            f"Revision {rev.revision} is {rev.status} and read-only; "
            "create a new revision to change it",
            code="revision_locked",
        )


async def _revisions(session: AsyncSession, boq_id: uuid.UUID) -> list[BoqRevision]:
    rows = (
        (
            await session.execute(
                select(BoqRevision).where(
                    BoqRevision.boq_id == boq_id, BoqRevision.is_deleted.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    return sorted(rows, key=lambda r: _rev_order(r.revision))


async def _lines(session: AsyncSession, revision_id: uuid.UUID) -> list[BoqLine]:
    rows = await session.execute(
        select(BoqLine)
        .where(BoqLine.revision_id == revision_id, BoqLine.is_deleted.is_(False))
        .order_by(BoqLine.line_no)
    )
    return list(rows.scalars())


async def current_revision(session: AsyncSession, boq_id: uuid.UUID) -> BoqRevision | None:
    """The released revision, else the latest one."""
    revisions = await _revisions(session, boq_id)
    if not revisions:
        return None
    released = [r for r in revisions if r.status == RevisionStatus.RELEASED.value]
    return released[0] if released else revisions[-1]


# ---------------------------------------------------------------- reading


async def key_groups(
    session: AsyncSession, boq_id: uuid.UUID, lines: list[BoqLine]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Line id -> ids of the lines with the same line key in every revision of the BOQ, so
    purchase orders and issues against an earlier revision keep counting."""
    keys = {ln.line_key for ln in lines}
    rows = (
        await session.execute(
            select(BoqLine.line_key, BoqLine.id)
            .join(BoqRevision, BoqRevision.id == BoqLine.revision_id)
            .where(
                BoqRevision.boq_id == boq_id,
                BoqRevision.is_deleted.is_(False),
                BoqLine.is_deleted.is_(False),
                BoqLine.line_key.in_(keys),
            )
        )
    ).all()
    by_key: dict[str, list[uuid.UUID]] = {}
    for key, line_id in rows:
        by_key.setdefault(key, []).append(line_id)
    return {ln.id: by_key.get(ln.line_key, [ln.id]) for ln in lines}


@dataclass
class BoqView:
    boq: Boq
    project: Project
    module: Module | None
    assembly: PcbAssembly | None
    revisions: list[tuple[BoqRevision, int]]


async def _view(session: AsyncSession, boq: Boq) -> BoqView:
    project = await session.get(Project, boq.project_id)
    assert project is not None
    module = await session.get(Module, boq.module_id) if boq.module_id else None
    assembly = await session.get(PcbAssembly, boq.assembly_id) if boq.assembly_id else None
    counts = dict(
        (
            await session.execute(
                select(BoqLine.revision_id, func.count())
                .join(BoqRevision, BoqRevision.id == BoqLine.revision_id)
                .where(BoqRevision.boq_id == boq.id, BoqLine.is_deleted.is_(False))
                .group_by(BoqLine.revision_id)
            )
        ).all()
    )
    revisions = [(r, int(counts.get(r.id, 0))) for r in await _revisions(session, boq.id)]
    return BoqView(boq, project, module, assembly, revisions)


async def list_project_boqs(
    session: AsyncSession, user: Principal, project_id: uuid.UUID
) -> list[BoqView]:
    user.require("boq:read")
    await org.get_project(session, user, project_id)
    boqs = (
        (
            await session.execute(
                select(Boq)
                .where(Boq.project_id == project_id, Boq.is_deleted.is_(False))
                .order_by(Boq.name)
            )
        )
        .scalars()
        .all()
    )
    return [await _view(session, b) for b in boqs]


async def list_all_boqs(session: AsyncSession, user: Principal) -> list[BoqView]:
    user.require("boq:read")
    stmt = org.scope_projects(
        select(Boq)
        .join(Project, Project.id == Boq.project_id)
        .where(Boq.is_deleted.is_(False), Project.is_deleted.is_(False)),
        user,
    ).order_by(Project.code, Boq.name)
    return [await _view(session, b) for b in (await session.execute(stmt)).scalars().all()]


async def get_boq(session: AsyncSession, user: Principal, boq_id: uuid.UUID) -> BoqView:
    return await _view(session, await _boq(session, user, boq_id))


async def revision_lines(
    session: AsyncSession, user: Principal, revision_id: uuid.UUID
) -> tuple[BoqRevision, list[tuple[BoqLine, LineQuantities]]]:
    _, rev = await _revision(session, user, revision_id)
    lines = await _lines(session, rev.id)
    qty = await procurement.line_quantities(session, await key_groups(session, rev.boq_id, lines))
    out = []
    for ln in lines:
        req = required_qty(
            ln.qty_per_unit, rev.build_qty, ln.attrition_pct, unit=ln.unit, dnp=ln.dnp
        )
        ordered, received, issued = qty.get(ln.id, (Decimal(0), Decimal(0), Decimal(0)))
        out.append((ln, quantities(req, ordered, received, issued)))
    return rev, out


# ---------------------------------------------------------------- for procurement


@dataclass
class TrackedLine:
    line: BoqLine
    qty: LineQuantities
    group: list[uuid.UUID]  # this line's id plus the same line key in other revisions


@dataclass
class TrackedBoq:
    view: BoqView
    revision: BoqRevision | None
    lines: list[TrackedLine]


async def project_lines(
    session: AsyncSession, user: Principal, project_id: uuid.UUID
) -> list[TrackedBoq]:
    """Each BOQ of the project with its current revision (released, else the latest) and
    every line's quantities from the status service."""
    out = []
    for view in await list_project_boqs(session, user, project_id):
        rev = await current_revision(session, view.boq.id)
        if rev is None:
            out.append(TrackedBoq(view, None, []))
            continue
        lines = await _lines(session, rev.id)
        groups = await key_groups(session, view.boq.id, lines)
        qty = await procurement.line_quantities(session, groups)
        tracked = []
        for ln in lines:
            req = required_qty(
                ln.qty_per_unit, rev.build_qty, ln.attrition_pct, unit=ln.unit, dnp=ln.dnp
            )
            ordered, received, issued = qty.get(ln.id, (Decimal(0), Decimal(0), Decimal(0)))
            tracked.append(
                TrackedLine(ln, quantities(req, ordered, received, issued), groups[ln.id])
            )
        out.append(TrackedBoq(view, rev, tracked))
    return out


@dataclass(frozen=True)
class LineRef:
    id: uuid.UUID
    boq_id: uuid.UUID
    boq_name: str
    project_id: uuid.UUID
    revision: str
    revision_status: str
    line_no: int
    part_id: uuid.UUID | None
    mpn: str | None
    description: str | None
    ref_des: str | None
    unit: str


async def line_refs(
    session: AsyncSession, user: Principal, line_ids: list[uuid.UUID]
) -> dict[uuid.UUID, LineRef]:
    """BOQ lines by id with their BOQ and project. Raises NotFoundError for a missing line
    or one outside the user's scope."""
    if not line_ids:
        return {}
    rows = (
        await session.execute(
            select(BoqLine, BoqRevision, Boq)
            .join(BoqRevision, BoqRevision.id == BoqLine.revision_id)
            .join(Boq, Boq.id == BoqRevision.boq_id)
            .where(
                BoqLine.id.in_(set(line_ids)),
                BoqLine.is_deleted.is_(False),
                BoqRevision.is_deleted.is_(False),
                Boq.is_deleted.is_(False),
            )
        )
    ).all()
    found = {ln.id: (ln, rev, boq) for ln, rev, boq in rows}
    out: dict[uuid.UUID, LineRef] = {}
    checked: set[uuid.UUID] = set()
    for line_id in line_ids:
        if line_id not in found:
            raise NotFoundError("BOQ line not found", details={"id": str(line_id)})
        ln, rev, boq = found[line_id]
        if boq.project_id not in checked:
            try:
                await org.get_project(session, user, boq.project_id)
            except NotFoundError as exc:
                raise NotFoundError("BOQ line not found", details={"id": str(line_id)}) from exc
            checked.add(boq.project_id)
        out[line_id] = LineRef(
            id=ln.id,
            boq_id=boq.id,
            boq_name=boq.name,
            project_id=boq.project_id,
            revision=rev.revision,
            revision_status=rev.status,
            line_no=ln.line_no,
            part_id=ln.part_id,
            mpn=ln.mpn,
            description=ln.description,
            ref_des=ln.ref_des,
            unit=ln.unit,
        )
    return out


# ---------------------------------------------------------------- BOQ and revisions


async def create_boq(
    session: AsyncSession, user: Principal, project_id: uuid.UUID, data: BoqCreate
) -> Boq:
    user.require("boq:edit")
    await org.get_project(session, user, project_id)
    build_qty = data.build_qty
    module = None
    if data.module_id:
        module = await org.get_module(session, user, data.module_id)
        if module.project_id != project_id:
            raise AppError(
                "Module belongs to another project", code="invalid_reference", status_code=422
            )
    if data.assembly_id:
        assembly = await org.get_assembly(session, user, data.assembly_id)
        if module is None or assembly.module_id != module.id:
            raise AppError(
                "Assembly must belong to the selected module",
                code="invalid_reference",
                status_code=422,
            )
        if build_qty is None:
            build_qty = module.qty_to_deliver * assembly.qty_per_module
    if build_qty is None:
        build_qty = module.qty_to_deliver if module else 1
    boq = Boq(
        project_id=project_id,
        module_id=data.module_id,
        assembly_id=data.assembly_id,
        name=data.name,
        notes=data.notes,
    )
    session.add(boq)
    await session.flush()
    if data.create_revision:
        session.add(
            BoqRevision(
                boq_id=boq.id,
                revision="A",
                status=RevisionStatus.DRAFT.value,
                build_qty=build_qty,
                attrition_by_category=await _company_attrition(session),
            )
        )
    await session.flush()
    await session.commit()
    return boq


async def delete_boq(
    session: AsyncSession, user: Principal, boq_id: uuid.UUID, row_version: int
) -> None:
    user.require("boq:edit")
    boq = await _boq(session, user, boq_id)
    check_version(boq, row_version)
    if any(r.status != RevisionStatus.DRAFT.value for r in await _revisions(session, boq.id)):
        raise ConflictError("A BOQ with a released revision cannot be deleted", code="boq_released")
    boq.is_deleted = True
    await session.flush()
    await session.commit()


async def create_revision(session: AsyncSession, user: Principal, boq_id: uuid.UUID) -> BoqRevision:
    """New draft revision, copied from the current (released, else latest) revision."""
    user.require("boq:edit")
    boq = await _boq(session, user, boq_id)
    revisions = await _revisions(session, boq.id)
    if any(r.status == RevisionStatus.DRAFT.value for r in revisions):
        raise ConflictError(
            "Finish or delete the existing draft revision first", code="draft_exists"
        )
    source = await current_revision(session, boq.id)
    rev = BoqRevision(
        boq_id=boq.id,
        revision=next_revision_letter([r.revision for r in revisions]),
        status=RevisionStatus.DRAFT.value,
        build_qty=source.build_qty if source else 1,
        attrition_by_category=dict(source.attrition_by_category)
        if source
        else await _company_attrition(session),
    )
    session.add(rev)
    await session.flush()
    if source is not None:
        for ln in await _lines(session, source.id):
            session.add(BoqLine(revision_id=rev.id, **{f: getattr(ln, f) for f in _LINE_FIELDS}))
    await session.flush()
    await session.commit()
    return rev


async def delete_revision(
    session: AsyncSession, user: Principal, revision_id: uuid.UUID, row_version: int
) -> None:
    user.require("boq:edit")
    _, rev = await _revision(session, user, revision_id)
    check_version(rev, row_version)
    _require_draft(rev)
    for ln in await _lines(session, rev.id):
        await session.delete(ln)
    rev.is_deleted = True
    await session.flush()
    await session.commit()


async def update_build(
    session: AsyncSession, user: Principal, revision_id: uuid.UUID, data: BuildUpdate
) -> BoqRevision:
    user.require("boq:edit")
    _, rev = await _revision(session, user, revision_id)
    check_version(rev, data.row_version)
    _require_draft(rev)
    if data.build_qty is not None:
        rev.build_qty = data.build_qty
    if "notes" in data.model_fields_set:
        rev.notes = data.notes
    if data.attrition_by_category is not None:
        rates = {k[:32]: float(v) for k, v in data.attrition_by_category.items()}
        if any(not 0 <= v <= 100 for v in rates.values()):
            raise AppError(
                "Attrition must be between 0 and 100 %", code="invalid_attrition", status_code=422
            )
        rev.attrition_by_category = rates
        for ln in await _lines(session, rev.id):
            if not ln.attrition_override:
                ln.attrition_pct = _category_rate(rates, ln.category)
    flag_modified(rev, "updated_by")
    await session.flush()
    await session.commit()
    return rev


async def release(
    session: AsyncSession, user: Principal, revision_id: uuid.UUID, row_version: int
) -> BoqRevision:
    user.require("boq:release")
    boq, rev = await _revision(session, user, revision_id)
    check_version(rev, row_version)
    _require_draft(rev)
    if not await _lines(session, rev.id):
        raise ConflictError("An empty revision cannot be released", code="empty_revision")
    for other in await _revisions(session, boq.id):
        if other.status == RevisionStatus.RELEASED.value:
            other.status = RevisionStatus.SUPERSEDED.value
    await session.flush()  # free the "one released" unique index before taking it
    rev.status = RevisionStatus.RELEASED.value
    rev.released_at = utcnow()
    await session.flush()
    await session.commit()
    return rev


# ---------------------------------------------------------------- lines


_PART_FIELDS = ("mpn", "manufacturer", "description", "package", "value", "category", "unit")
_TEMP_LINE_NO = 1_000_000


def _check_lines(lines: list[LineIn]) -> None:
    problems: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for i, ln in enumerate(lines, start=1):
        if not (ln.mpn or "").strip() and not ln.dnp and ln.part_id is None:
            problems.append(
                {"line": i, "field": "mpn", "message": "MPN is required unless the line is DNP"}
            )
        for ref in importer.split_ref_des(ln.ref_des or ""):
            key = ref.upper()
            if key in seen:
                problems.append(
                    {"line": i, "field": "ref_des", "message": f"{ref} is also on line {seen[key]}"}
                )
            else:
                seen[key] = i
    if problems:
        raise AppError(
            "Some lines are invalid", code="invalid_lines", status_code=422, details=problems
        )


async def save_lines(
    session: AsyncSession,
    user: Principal,
    revision_id: uuid.UUID,
    row_version: int,
    lines: list[LineIn],
) -> BoqRevision:
    """Replace the draft's lines with the grid contents (matched by line_key)."""
    user.require("boq:edit")
    _, rev = await _revision(session, user, revision_id)
    check_version(rev, row_version)
    _require_draft(rev)
    _check_lines(lines)
    existing = {ln.line_key: ln for ln in await _lines(session, rev.id)}
    by_mpn = await parts.by_normalised_mpn(
        session, [ln.mpn or "" for ln in lines if ln.part_id is None]
    )
    keep: set[str] = set()
    rates = rev.attrition_by_category or {}
    pending: list[tuple[BoqLine, int]] = []
    for idx, data in enumerate(lines, start=1):
        key = data.line_key if data.line_key in existing else (data.line_key or uuid7().hex)
        if key in keep:
            key = uuid7().hex  # duplicated key in the payload (copied row)
        keep.add(key)
        part_id = data.part_id
        if part_id is not None:
            await parts.get(session, part_id)
        elif data.mpn:
            match = by_mpn.get(importer.norm_mpn(data.mpn))
            part_id = match.id if match else None
        override = data.attrition_pct is not None
        values = {
            "part_id": part_id,
            "ref_des": ",".join(importer.split_ref_des(data.ref_des or "")) or None,
            "qty_per_unit": data.qty_per_unit,
            "mpn": (data.mpn or "").strip() or None,
            "manufacturer": data.manufacturer,
            "description": data.description,
            "value": data.value,
            "package": data.package,
            "category": importer.normalise_category(data.category or ""),
            "unit": data.unit.lower(),
            "dnp": data.dnp,
            "attrition_override": override,
            "attrition_pct": data.attrition_pct
            if override
            else _category_rate(rates, importer.normalise_category(data.category or "")),
            "unit_price": data.unit_price,
            "notes": data.notes,
        }
        line = existing.get(key)
        if line is None:
            line = BoqLine(revision_id=rev.id, line_key=key, line_no=_TEMP_LINE_NO + idx, **values)
            session.add(line)
        else:
            for k, v in values.items():
                setattr(line, k, v)
            # Temporary number: avoids unique (revision, line_no) clashes while renumbering.
            line.line_no = _TEMP_LINE_NO + idx
        pending.append((line, idx))
    for key, line in existing.items():
        if key not in keep:
            await session.delete(line)
    await session.flush()
    for line, idx in pending:
        line.line_no = idx
    flag_modified(rev, "updated_by")
    await session.flush()
    await session.commit()
    return rev


# ---------------------------------------------------------------- compare


_COMPARE_FIELDS = (
    "ref_des",
    "qty_per_unit",
    "mpn",
    "manufacturer",
    "description",
    "value",
    "package",
    "category",
    "unit",
    "dnp",
    "unit_price",
    "notes",
)


def _line_dict(ln: BoqLine) -> dict[str, Any]:
    return {
        "line_no": ln.line_no,
        "line_key": ln.line_key,
        **{
            f: (str(getattr(ln, f)) if isinstance(getattr(ln, f), Decimal) else getattr(ln, f))
            for f in _COMPARE_FIELDS
        },
    }


async def compare(
    session: AsyncSession, user: Principal, boq_id: uuid.UUID, from_rev: str, to_rev: str
) -> dict[str, Any]:
    boq = await _boq(session, user, boq_id)
    revisions = {r.revision: r for r in await _revisions(session, boq.id)}
    if from_rev not in revisions or to_rev not in revisions:
        raise NotFoundError("Revision not found", details={"from": from_rev, "to": to_rev})
    a = {ln.line_key: ln for ln in await _lines(session, revisions[from_rev].id)}
    b = {ln.line_key: ln for ln in await _lines(session, revisions[to_rev].id)}
    out: list[dict[str, Any]] = []
    summary = {
        "added": 0,
        "removed": 0,
        "qty_changed": 0,
        "substituted": 0,
        "changed": 0,
        "unchanged": 0,
    }
    for key in sorted(set(a) | set(b), key=lambda k: ((b.get(k) or a[k]).line_no, k)):
        old, new = a.get(key), b.get(key)
        fields: list[str]
        if old is None:
            change, fields = "added", []
        elif new is None:
            change, fields = "removed", []
        else:
            fields = [f for f in _COMPARE_FIELDS if getattr(old, f) != getattr(new, f)]
            if old.part_id != new.part_id or importer.norm_mpn(old.mpn or "") != importer.norm_mpn(
                new.mpn or ""
            ):
                change = "substituted"
            elif "qty_per_unit" in fields or "dnp" in fields:
                change = "qty_changed"
            elif fields:
                change = "changed"
            else:
                change = "unchanged"
        summary[change] += 1
        out.append(
            {
                "line_key": key,
                "change": change,
                "changed_fields": fields,
                "from_line": _line_dict(old) if old else None,
                "to_line": _line_dict(new) if new else None,
            }
        )
    return {
        "boq_id": boq.id,
        "from_revision": from_rev,
        "to_revision": to_rev,
        "summary": summary,
        "lines": out,
    }


# ---------------------------------------------------------------- import wizard


async def _import(
    session: AsyncSession, user: Principal, import_id: uuid.UUID
) -> tuple[Boq, BoqImport]:
    imp = await session.get(BoqImport, import_id)
    if imp is None or imp.is_deleted:
        raise NotFoundError("Import not found", details={"id": str(import_id)})
    boq = await _boq(session, user, imp.boq_id)
    return boq, imp


async def start_import(
    session: AsyncSession,
    settings: Settings,
    user: Principal,
    boq_id: uuid.UUID,
    content: bytes,
    filename: str,
    mime: str | None,
) -> BoqImport:
    user.require("boq:import")
    boq = await _boq(session, user, boq_id)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(
            f"Files must be {settings.max_upload_mb} MB or smaller",
            code="payload_too_large",
            status_code=413,
        )
    lower = filename.lower()
    if not lower.endswith((".csv", ".txt", ".tsv", ".xlsx", ".xlsm")):
        raise AppError("Upload a CSV or XLSX file", code="unsupported_media_type", status_code=415)
    record = await store_file(
        session,
        settings.data_dir,
        content,
        original_name=filename,
        mime=mime or "text/csv",
        ref_type="boq",
        ref_id=boq.id,
    )
    imp = BoqImport(boq_id=boq.id, file_id=record.id, status=ImportStatus.PARSING.value)
    session.add(imp)
    await session.flush()
    job = await enqueue(session, "boq.parse", {"import_id": str(imp.id)}, created_by=user.id)
    imp.job_id = job.id
    await session.commit()
    return imp


async def get_import(
    session: AsyncSession, user: Principal, import_id: uuid.UUID
) -> tuple[BoqImport, StoredFile, uuid.UUID | None]:
    boq, imp = await _import(session, user, import_id)
    record = await session.get(StoredFile, imp.file_id)
    assert record is not None
    suggested = None
    if imp.headers:
        project = await session.get(Project, boq.project_id)
        suggested = await _matching_template(
            session, imp.headers, project.client_name if project else None
        )
    return imp, record, suggested


async def _matching_template(
    session: AsyncSession, headers: list[str], client: str | None
) -> uuid.UUID | None:
    """The client's template whose headers all appear in this file, if any."""
    templates = (
        (
            await session.execute(
                select(BoqMappingTemplate).where(BoqMappingTemplate.is_deleted.is_(False))
            )
        )
        .scalars()
        .all()
    )
    normalised = {importer.norm_header(h) for h in headers}
    candidates = [t for t in templates if t.mapping and set(t.mapping.values()) <= normalised]
    candidates.sort(key=lambda t: (t.client_name != client, -len(t.mapping)))
    return candidates[0].id if candidates else None


async def set_mapping(
    session: AsyncSession,
    user: Principal,
    import_id: uuid.UUID,
    *,
    row_version: int,
    header_row: int,
    mapping: dict[str, int],
    decimal_comma: bool,
    save_template_name: str | None,
    template_client: str | None,
) -> BoqImport:
    user.require("boq:import")
    _, imp = await _import(session, user, import_id)
    check_version(imp, row_version)
    if imp.status not in (ImportStatus.PARSED.value, ImportStatus.VALIDATED.value):
        raise ConflictError(f"Import is {imp.status}", code="import_state")
    rows = imp.rows or []
    if header_row >= len(rows):
        raise AppError(
            "Header row is beyond the end of the file", code="invalid_mapping", status_code=422
        )
    headers = rows[header_row]
    unknown = set(mapping) - set(importer.FIELDS)
    bad_cols = [c for c in mapping.values() if not 0 <= c < len(headers)]
    if unknown or bad_cols:
        raise AppError(
            "Invalid column mapping",
            code="invalid_mapping",
            status_code=422,
            details={"unknown_fields": sorted(unknown), "bad_columns": bad_cols},
        )
    imp.header_row = header_row
    imp.headers = headers
    imp.mapping = mapping
    imp.status = ImportStatus.VALIDATING.value
    imp.result = None
    if save_template_name:
        user.require("boq:import")
        existing = (
            await session.execute(
                select(BoqMappingTemplate).where(
                    BoqMappingTemplate.name == save_template_name,
                    BoqMappingTemplate.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        template_map = importer.template_from_mapping(headers, mapping)
        if existing:
            existing.mapping = template_map
            existing.client_name = template_client
            imp.template_id = existing.id
        else:
            tpl = BoqMappingTemplate(
                name=save_template_name, client_name=template_client, mapping=template_map
            )
            session.add(tpl)
            await session.flush()
            imp.template_id = tpl.id
    job = await enqueue(
        session,
        "boq.validate",
        {"import_id": str(imp.id), "decimal_comma": decimal_comma},
        created_by=user.id,
    )
    imp.job_id = job.id
    await session.flush()
    await session.commit()
    return imp


async def apply_template(
    session: AsyncSession, user: Principal, import_id: uuid.UUID, template_id: uuid.UUID
) -> dict[str, int]:
    """Column mapping for this file from a saved template (does not change the import)."""
    user.require("boq:read")
    _, imp = await _import(session, user, import_id)
    tpl = await session.get(BoqMappingTemplate, template_id)
    if tpl is None or tpl.is_deleted:
        raise NotFoundError("Template not found")
    return importer.mapping_from_template(imp.headers or [], tpl.mapping)


async def error_report(session: AsyncSession, user: Principal, import_id: uuid.UUID) -> str:
    _, imp = await _import(session, user, import_id)
    if not imp.result:
        raise ConflictError("Validate the file first", code="import_state")
    issues = [importer.Issue(**i) for i in imp.result["issues"]]
    return importer.error_report_csv(issues)


async def _assign_keys(
    session: AsyncSession, boq_id: uuid.UUID, lines: list[dict[str, Any]]
) -> list[str]:
    """Reuse the previous revision's line keys for the same part (MPN + manufacturer), then
    the same first ref des, so revisions diff line by line."""
    previous = await current_revision(session, boq_id)
    prev_lines = await _lines(session, previous.id) if previous else []
    by_part = {
        (importer.norm_mpn(ln.mpn or ""), (ln.manufacturer or "").upper(), ln.dnp): ln.line_key
        for ln in prev_lines
        if ln.mpn
    }
    by_ref = {
        (ln.ref_des or "").split(",")[0].upper(): ln.line_key for ln in prev_lines if ln.ref_des
    }
    used: set[str] = set()
    keys = []
    for ln in lines:
        key = (
            by_part.get(
                (importer.norm_mpn(ln["mpn"] or ""), (ln["manufacturer"] or "").upper(), ln["dnp"])
            )
            if ln["mpn"]
            else None
        )
        if (key is None or key in used) and ln["ref_des"]:
            key = by_ref.get(ln["ref_des"][0].upper())
        if key is None or key in used:
            key = uuid7().hex
        used.add(key)
        keys.append(key)
    return keys


async def commit_import(
    session: AsyncSession,
    user: Principal,
    import_id: uuid.UUID,
    *,
    row_version: int,
    release_now: bool,
    build_qty: int | None,
) -> BoqRevision:
    """Create the revision from a validated import (nothing was written before this)."""
    user.require("boq:import")
    boq, imp = await _import(session, user, import_id)
    check_version(imp, row_version)
    if imp.status != ImportStatus.VALIDATED.value or not imp.result:
        raise ConflictError("Validate the file before committing", code="import_state")
    if imp.result["stats"].get("errors", 0):
        raise ConflictError(
            "Fix every error before committing",
            code="import_has_errors",
            details={"errors": imp.result["stats"]["errors"]},
        )
    revisions = await _revisions(session, boq.id)
    drafts = [r for r in revisions if r.status == RevisionStatus.DRAFT.value]
    target: BoqRevision | None = None
    if drafts:
        if await _lines(session, drafts[0].id):
            raise ConflictError(
                "This BOQ already has a draft revision with lines; release or delete it first",
                code="draft_exists",
            )
        target = drafts[0]  # empty draft (e.g. a new BOQ): fill it
    source = await current_revision(session, boq.id)
    if target is None:
        target = BoqRevision(
            boq_id=boq.id,
            revision=next_revision_letter([r.revision for r in revisions]),
            status=RevisionStatus.DRAFT.value,
            build_qty=source.build_qty if source else 1,
            attrition_by_category=dict(source.attrition_by_category)
            if source
            else await _company_attrition(session),
        )
        session.add(target)
        await session.flush()
    if build_qty is not None:
        target.build_qty = build_qty
    target.source_file_id = imp.file_id
    rates = target.attrition_by_category or {}

    lines = imp.result["lines"]
    keys = await _assign_keys(session, boq.id, lines)
    known = await parts.by_normalised_mpn(session, [ln["mpn"] for ln in lines if ln["mpn"]])
    new_specs: dict[str, dict[str, Any]] = {}
    for ln in lines:
        norm = importer.norm_mpn(ln["mpn"]) if ln["mpn"] else None
        if norm and norm not in known and norm not in new_specs:
            new_specs[norm] = {k: ln[k] for k in _PART_FIELDS}
    created = await parts.create_for_import(session, list(new_specs.values()))
    known.update(zip(new_specs, created, strict=True))
    for idx, (ln, key) in enumerate(zip(lines, keys, strict=True), start=1):
        part = known.get(importer.norm_mpn(ln["mpn"])) if ln["mpn"] else None
        session.add(
            BoqLine(
                revision_id=target.id,
                line_key=key,
                line_no=idx,
                part_id=part.id if part else None,
                ref_des=",".join(ln["ref_des"]) or None,
                qty_per_unit=Decimal(ln["qty_per_unit"]),
                mpn=part.mpn if part else ln["mpn"],
                manufacturer=ln["manufacturer"] or (part.manufacturer if part else None),
                description=ln["description"],
                value=ln["value"],
                package=ln["package"],
                category=ln["category"],
                unit=ln["unit"],
                dnp=ln["dnp"],
                attrition_pct=_category_rate(rates, ln["category"]),
                unit_price=Decimal(ln["unit_price"]) if ln["unit_price"] is not None else None,
                notes="; ".join(
                    filter(
                        None,
                        [
                            ln["notes"],
                            f"Preferred vendor: {ln['preferred_vendor']}"
                            if ln["preferred_vendor"]
                            else None,
                        ],
                    )
                )
                or None,
            )
        )
    imp.status = ImportStatus.COMMITTED.value
    imp.revision_id = target.id
    imp.rows = None  # the parsed table is no longer needed; the file itself is kept
    await session.flush()
    await session.commit()
    if release_now:
        user.require("boq:release")
        target = await release(session, user, target.id, target.row_version)
    return target


async def list_templates(session: AsyncSession, user: Principal) -> list[BoqMappingTemplate]:
    user.require("boq:read")
    rows = await session.execute(
        select(BoqMappingTemplate)
        .where(BoqMappingTemplate.is_deleted.is_(False))
        .order_by(BoqMappingTemplate.name)
    )
    return list(rows.scalars())


async def delete_template(
    session: AsyncSession, user: Principal, template_id: uuid.UUID, row_version: int
) -> None:
    user.require("boq:import")
    tpl = await session.get(BoqMappingTemplate, template_id)
    if tpl is None or tpl.is_deleted:
        raise NotFoundError("Template not found")
    check_version(tpl, row_version)
    tpl.is_deleted = True
    await session.flush()
    await session.commit()


# ---------------------------------------------------------------- clone support (Phase 4)


async def copy_boqs_for_clone(
    session: AsyncSession,
    source_project_id: uuid.UUID,
    target_project_id: uuid.UUID,
    module_map: dict[uuid.UUID, uuid.UUID],
    assembly_map: dict[uuid.UUID, uuid.UUID],
) -> int:
    """Copies each BOQ's current revision into the cloned project as draft revision A.
    Line keys are preserved so later revisions diff cleanly against the original."""
    boqs = (
        (
            await session.execute(
                select(Boq).where(Boq.project_id == source_project_id, Boq.is_deleted.is_(False))
            )
        )
        .scalars()
        .all()
    )
    copied = 0
    for boq in boqs:
        revision = await current_revision(session, boq.id)
        if revision is None:
            continue
        new_boq = Boq(
            project_id=target_project_id,
            module_id=module_map.get(boq.module_id) if boq.module_id else None,
            assembly_id=assembly_map.get(boq.assembly_id) if boq.assembly_id else None,
            name=boq.name,
            notes=boq.notes,
        )
        session.add(new_boq)
        await session.flush()
        new_rev = BoqRevision(
            boq_id=new_boq.id,
            revision="A",
            status=RevisionStatus.DRAFT.value,
            build_qty=revision.build_qty,
            attrition_by_category=dict(revision.attrition_by_category or {}),
            notes=f"Copied from revision {revision.revision} of the source project.",
        )
        session.add(new_rev)
        await session.flush()
        for line in await _lines(session, revision.id):
            session.add(
                BoqLine(revision_id=new_rev.id, **{f: getattr(line, f) for f in _LINE_FIELDS})
            )
        await session.flush()
        copied += 1
    return copied
