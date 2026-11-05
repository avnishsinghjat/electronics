"""Company settings, branding, document numbering and the first-run setup wizard."""

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.files import StoredFile, store_file
from app.core.models import utcnow
from app.core.numbering import DocumentNumberConfig, format_number, set_prefix
from app.core.permissions import Role
from app.core.repository import check_version
from app.core.security import hash_password
from app.modules.auth import service as auth
from app.modules.auth.models import User, UserRole
from app.modules.auth.service import Principal
from app.modules.settings.models import CompanySettings
from app.modules.settings.schemas import (
    CompanyUpdate,
    DataDirCheck,
    NumberingOut,
    SetupRequest,
)

LOGO_MAX_BYTES = 2 * 1024 * 1024
# Raster formats only: SVG can carry scripts and the logo is served from our own origin.
_LOGO_MAGIC: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
]
MIN_FREE_BYTES = 1 * 1024**3


async def get_company(session: AsyncSession) -> CompanySettings | None:
    return (await session.execute(select(CompanySettings))).scalar_one_or_none()


async def setup_needed(session: AsyncSession) -> bool:
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    return users == 0


def check_data_dir(data_dir: Path) -> DataDirCheck:
    path = data_dir.resolve()
    exists = path.is_dir()
    writable = False
    detail = None
    if exists:
        try:
            fd, probe = tempfile.mkstemp(dir=path, prefix=".write-test-")
            os.close(fd)
            Path(probe).unlink()
            writable = True
        except OSError as exc:
            detail = f"Not writable: {exc.strerror}"
    else:
        detail = "Directory does not exist"
    free = shutil.disk_usage(path).free if exists else None
    if free is not None and free < MIN_FREE_BYTES:
        detail = "Less than 1 GiB free"
    ok = exists and writable and free is not None and free >= MIN_FREE_BYTES
    return DataDirCheck(
        path=str(path), exists=exists, writable=writable, free_bytes=free, ok=ok, detail=detail
    )


async def list_numbering(session: AsyncSession) -> list[NumberingOut]:
    year = datetime.now(UTC).year
    configs = (
        await session.execute(select(DocumentNumberConfig).order_by(DocumentNumberConfig.doc_type))
    ).scalars()
    return [
        NumberingOut(
            doc_type=c.doc_type,
            description=c.description,
            prefix=c.prefix,
            padding=c.padding,
            yearly_reset=c.yearly_reset,
            example=format_number(c.prefix, year, 1, c.padding, yearly=c.yearly_reset),
        )
        for c in configs
    ]


async def update_numbering(
    session: AsyncSession, user: Principal, doc_type: str, prefix: str
) -> NumberingOut:
    user.require("settings:manage")
    await set_prefix(session, doc_type, prefix)
    await session.commit()
    return next(n for n in await list_numbering(session) if n.doc_type == doc_type)


async def update_company(
    session: AsyncSession, user: Principal, data: CompanyUpdate
) -> CompanySettings:
    user.require("settings:manage")
    company = await get_company(session)
    if company is None:
        raise NotFoundError("Run first-time setup first", code="setup_required")
    check_version(company, data.row_version)
    company.company_name = data.company_name
    company.address = data.address
    company.gstin = data.gstin
    await session.commit()
    return company


def logo_mime(content: bytes) -> str:
    for magic, mime in _LOGO_MAGIC:
        if content.startswith(magic) and (mime != "image/webp" or content[8:12] == b"WEBP"):
            return mime
    raise AppError(
        "Logo must be a PNG, JPEG or WebP image", code="unsupported_media_type", status_code=415
    )


async def set_logo(
    session: AsyncSession, settings: Settings, user: Principal, content: bytes, filename: str
) -> StoredFile:
    user.require("settings:manage")
    if len(content) > LOGO_MAX_BYTES:
        raise AppError("Logo must be 2 MB or smaller", code="payload_too_large", status_code=413)
    mime = logo_mime(content)
    company = await get_company(session)
    if company is None:
        raise NotFoundError("Run first-time setup first", code="setup_required")
    record = await store_file(
        session,
        settings.data_dir,
        content,
        original_name=filename,
        mime=mime,
        ref_type="company_settings",
        ref_id=company.id,
    )
    company.logo_file_id = record.id
    await session.commit()
    return record


async def get_logo(session: AsyncSession) -> StoredFile | None:
    company = await get_company(session)
    if company is None or company.logo_file_id is None:
        return None
    return await session.get(StoredFile, company.logo_file_id)


async def run_setup(session: AsyncSession, settings: Settings, data: SetupRequest) -> User:
    """Creates the first admin, the company record and document prefixes. Only allowed while
    no user exists; the advisory lock makes two simultaneous submissions safe."""
    await session.execute(select(func.pg_advisory_xact_lock(7_202_611)))
    if not await setup_needed(session):
        raise ConflictError("Setup has already been completed", code="setup_complete")
    check = check_data_dir(settings.data_dir)
    if not check.exists or not check.writable:
        raise AppError(
            f"Data directory problem: {check.detail}",
            code="data_dir_unavailable",
            status_code=422,
            details=check.model_dump(),
        )
    auth.validate_new_password(settings, data.admin.password, username=data.admin.username)
    for doc_type, prefix in data.prefixes.items():
        await set_prefix(session, doc_type, prefix)
    admin = User(
        username=data.admin.username,
        full_name=data.admin.full_name,
        password_hash=hash_password(data.admin.password),
        must_change_password=False,  # they just chose it
        password_changed_at=utcnow(),
        is_active=True,
    )
    session.add(admin)
    await session.flush()
    session.add(UserRole(user_id=admin.id, role=Role.ADMIN.value))
    company = await get_company(session)
    if company is None:
        session.add(CompanySettings(company_name=data.company_name, setup_completed_at=utcnow()))
    else:
        company.company_name = data.company_name
        company.setup_completed_at = utcnow()
    # Reference data every plant needs (stock locations, the default stage template), so a
    # fresh install can receive goods without running the seed command. Idempotent.
    from app.seed import seed_reference_data  # local: the seed module imports most modules

    await seed_reference_data(session)
    await session.commit()
    return admin
