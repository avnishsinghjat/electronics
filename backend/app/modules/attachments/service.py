"""Attachments: any module registers how to authorise access to its record type, then
users can attach, list, download and delete files on those records.

Bytes live in the content-addressed store (``app.core.files``); this module adds the
access rules, type detection and safe serving.
"""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.files import StoredFile, store_file
from app.core.repository import check_version
from app.modules.auth.models import User
from app.modules.auth.service import Principal
from app.modules.org import service as org
from app.modules.org.models import PcbAssembly

# A resolver raises NotFoundError if the record does not exist or is outside the user's scope.
Resolver = Callable[[AsyncSession, Principal, uuid.UUID], Awaitable[None]]
_RESOLVERS: dict[str, Resolver] = {}

# Types a browser may display inline. Everything else downloads as an attachment.
PREVIEWABLE = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}
_MAGIC: list[tuple[bytes, int, str]] = [
    (b"%PDF-", 0, "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png"),
    (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"GIF87a", 0, "image/gif"),
    (b"GIF89a", 0, "image/gif"),
    (b"WEBP", 8, "image/webp"),
    (b"PK\x03\x04", 0, "application/zip"),
]


def register_ref_type(ref_type: str, resolver: Resolver) -> None:
    _RESOLVERS[ref_type] = resolver


def ref_types() -> list[str]:
    return sorted(_RESOLVERS)


def sniff_mime(content: bytes, declared: str | None) -> str:
    """Type from the file's magic bytes; the browser-declared type is trusted only for
    plain text-like formats we never render inline."""
    for magic, offset, mime in _MAGIC:
        if content[offset : offset + len(magic)] == magic:
            return mime
    declared = (declared or "").split(";")[0].strip().lower()
    if declared in {
        "text/csv",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return declared
    return "application/octet-stream"


async def _authorise(
    session: AsyncSession, user: Principal, ref_type: str, ref_id: uuid.UUID
) -> None:
    resolver = _RESOLVERS.get(ref_type)
    if resolver is None:
        raise AppError(
            f"Files cannot be attached to '{ref_type}'",
            code="invalid_ref_type",
            status_code=422,
            details={"allowed": ref_types()},
        )
    await resolver(session, user, ref_id)


async def upload(
    session: AsyncSession,
    settings: Settings,
    user: Principal,
    *,
    ref_type: str,
    ref_id: uuid.UUID,
    content: bytes,
    filename: str,
    declared_mime: str | None,
) -> StoredFile:
    user.require("files:upload")
    await _authorise(session, user, ref_type, ref_id)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(
            f"Files must be {settings.max_upload_mb} MB or smaller",
            code="payload_too_large",
            status_code=413,
        )
    record = await store_file(
        session,
        settings.data_dir,
        content,
        original_name=filename,
        mime=sniff_mime(content, declared_mime),
        ref_type=ref_type,
        ref_id=ref_id,
    )
    await session.commit()
    return record


async def list_for(
    session: AsyncSession, user: Principal, ref_type: str, ref_id: uuid.UUID
) -> list[tuple[StoredFile, str | None]]:
    user.require("projects:read")
    await _authorise(session, user, ref_type, ref_id)
    rows = await session.execute(
        select(StoredFile, User.full_name)
        .outerjoin(User, User.id == StoredFile.uploaded_by)
        .where(
            StoredFile.ref_type == ref_type,
            StoredFile.ref_id == ref_id,
            StoredFile.is_deleted.is_(False),
        )
        .order_by(StoredFile.created_at.desc())
    )
    return [(f, name) for f, name in rows.all()]


async def get(session: AsyncSession, user: Principal, file_id: uuid.UUID) -> StoredFile:
    user.require("projects:read")
    record = await session.get(StoredFile, file_id)
    if record is None or record.is_deleted or record.ref_type is None or record.ref_id is None:
        raise NotFoundError("File not found", details={"id": str(file_id)})
    try:
        await _authorise(session, user, record.ref_type, record.ref_id)
    except (NotFoundError, AppError) as exc:
        raise NotFoundError("File not found", details={"id": str(file_id)}) from exc
    return record


async def delete(
    session: AsyncSession, user: Principal, file_id: uuid.UUID, row_version: int
) -> None:
    user.require("files:delete")
    record = await get(session, user, file_id)
    check_version(record, row_version)
    in_use = (
        (
            await session.execute(
                select(PcbAssembly.code).where(
                    PcbAssembly.is_deleted.is_(False),
                    or_(
                        PcbAssembly.assembly_drawing_file_id == record.id,
                        PcbAssembly.kicad_project_file_id == record.id,
                    ),
                )
            )
        )
        .scalars()
        .first()
    )
    if in_use:
        raise ConflictError(
            f"This file is the drawing or KiCad project of assembly {in_use}; "
            "unlink it there first",
            code="file_in_use",
        )
    record.is_deleted = True  # bytes stay in the store: other records may share them
    await session.flush()
    await session.commit()


# ---------------------------------------------------------------- org record types


async def _division(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    if ref_id not in {d.id for d in await org.list_divisions(session, user)}:
        raise NotFoundError("Division not found")


async def _project(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    await org.get_project(session, user, ref_id)


async def _module(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    await org.get_module(session, user, ref_id)


async def _assembly(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    await org.get_assembly(session, user, ref_id)


async def _boq(session: AsyncSession, user: Principal, ref_id: uuid.UUID) -> None:
    from app.modules.boq.models import Boq  # BOQ files: uploaded BOQ sources

    boq = await session.get(Boq, ref_id)
    if boq is None or boq.is_deleted:
        raise NotFoundError("BOQ not found")
    await org.get_project(session, user, boq.project_id)


register_ref_type("division", _division)
register_ref_type("boq", _boq)
register_ref_type("project", _project)
register_ref_type("module", _module)
register_ref_type("assembly", _assembly)
