from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import NotFoundError
from app.modules.auth import service as auth
from app.modules.auth.deps import public, require
from app.modules.auth.router import set_refresh_cookie, token_out
from app.modules.auth.schemas import TokenOut
from app.modules.auth.service import Principal
from app.modules.settings import service
from app.modules.settings.schemas import (
    BrandingOut,
    CompanyOut,
    CompanyUpdate,
    FileRef,
    NumberingOut,
    NumberingUpdate,
    SetupRequest,
    SetupStatus,
)

router = APIRouter(tags=["settings"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get(
    "/setup/status",
    response_model=SetupStatus,
    dependencies=[Depends(public)],
    summary="First-run status",
)
async def setup_status(session: SessionDep, settings: SettingsDep) -> SetupStatus:
    needed = await service.setup_needed(session)
    return SetupStatus(
        needs_setup=needed,
        data_dir=service.check_data_dir(settings.data_dir),
        numbering=await service.list_numbering(session) if needed else [],
    )


@router.post(
    "/setup",
    response_model=TokenOut,
    status_code=201,
    dependencies=[Depends(public)],
    summary="Run first-time setup",
)
async def run_setup(
    body: SetupRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenOut:
    """Only works while no user exists (409 `setup_complete` afterwards). Signs the new admin in."""
    admin = await service.run_setup(session, settings, body)
    issued = await auth.login(
        session,
        settings,
        admin.username,
        body.admin.password,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    set_refresh_cookie(response, settings, issued)
    return token_out(issued)


@router.get(
    "/settings/branding",
    response_model=BrandingOut,
    dependencies=[Depends(public)],
    summary="Company name and logo for the login page",
)
async def branding(session: SessionDep) -> BrandingOut:
    company = await service.get_company(session)
    has_logo = company is not None and company.logo_file_id is not None
    return BrandingOut(
        company_name=company.company_name if company else None,
        has_logo=has_logo,
        logo_url="/api/settings/logo" if has_logo else None,
        setup_complete=company is not None and company.setup_completed_at is not None,
    )


@router.get(
    "/settings/logo",
    dependencies=[Depends(public)],
    summary="Company logo image",
    response_class=FileResponse,
)
async def logo(session: SessionDep, settings: SettingsDep) -> FileResponse:
    record = await service.get_logo(session)
    if record is None:
        raise NotFoundError("No logo uploaded")
    return FileResponse(
        settings.data_dir / record.storage_path,
        media_type=record.mime,
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/settings/logo", response_model=FileRef, summary="Upload the company logo")
async def upload_logo(
    user: Annotated[Principal, Depends(require("settings:manage"))],
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="PNG, JPEG or WebP, max 2 MB")],
) -> FileRef:
    content = await file.read(service.LOGO_MAX_BYTES + 1)
    record = await service.set_logo(session, settings, user, content, file.filename or "logo")
    return FileRef(id=record.id, sha256=record.sha256)


@router.get("/settings/company", response_model=CompanyOut, summary="Company details")
async def company(
    _: Annotated[Principal, Depends(require("settings:read"))], session: SessionDep
) -> CompanyOut:
    c = await service.get_company(session)
    if c is None:
        raise NotFoundError("Run first-time setup first", code="setup_required")
    return CompanyOut(
        company_name=c.company_name,
        address=c.address,
        gstin=c.gstin,
        has_logo=c.logo_file_id is not None,
        row_version=c.row_version,
    )


@router.put("/settings/company", response_model=CompanyOut, summary="Update company details")
async def update_company(
    body: CompanyUpdate,
    user: Annotated[Principal, Depends(require("settings:manage"))],
    session: SessionDep,
) -> CompanyOut:
    c = await service.update_company(session, user, body)
    return CompanyOut(
        company_name=c.company_name,
        address=c.address,
        gstin=c.gstin,
        has_logo=c.logo_file_id is not None,
        row_version=c.row_version,
    )


@router.get(
    "/settings/numbering", response_model=list[NumberingOut], summary="Document number prefixes"
)
async def numbering(
    _: Annotated[Principal, Depends(require("settings:read"))], session: SessionDep
) -> list[NumberingOut]:
    return await service.list_numbering(session)


@router.put(
    "/settings/numbering/{doc_type}",
    response_model=NumberingOut,
    summary="Change a document prefix",
)
async def update_numbering(
    doc_type: str,
    body: NumberingUpdate,
    user: Annotated[Principal, Depends(require("settings:manage"))],
    session: SessionDep,
) -> NumberingOut:
    return await service.update_numbering(session, user, doc_type, body.prefix)
