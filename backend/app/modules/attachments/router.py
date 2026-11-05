import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.files import StoredFile
from app.modules.attachments import service
from app.modules.attachments.schemas import AttachmentOut
from app.modules.auth.deps import require
from app.modules.auth.service import Principal

router = APIRouter(prefix="/files", tags=["attachments"])
# Served files can never run script, even if a crafted PDF is opened directly.
FILE_CSP = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def out(record: StoredFile, uploader: str | None) -> AttachmentOut:
    assert record.ref_type is not None
    assert record.ref_id is not None
    return AttachmentOut(
        id=record.id,
        ref_type=record.ref_type,
        ref_id=record.ref_id,
        original_name=record.original_name,
        mime=record.mime,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        uploaded_by=record.uploaded_by,
        uploaded_by_name=uploader,
        created_at=record.created_at,
        previewable=record.mime in service.PREVIEWABLE,
        row_version=record.row_version,
    )


@router.post("", response_model=AttachmentOut, status_code=201, summary="Attach a file to a record")
async def upload(
    user: Annotated[Principal, Depends(require("files:upload"))],
    session: SessionDep,
    settings: SettingsDep,
    ref_type: Annotated[str, Form(max_length=64)],
    ref_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> AttachmentOut:
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    record = await service.upload(
        session,
        settings,
        user,
        ref_type=ref_type,
        ref_id=ref_id,
        content=content,
        filename=file.filename or "file",
        declared_mime=file.content_type,
    )
    return out(record, user.full_name)


@router.get("", response_model=list[AttachmentOut], summary="Files attached to a record")
async def list_files(
    user: Annotated[Principal, Depends(require("projects:read"))],
    session: SessionDep,
    ref_type: Annotated[str, Query(max_length=64)],
    ref_id: uuid.UUID,
) -> list[AttachmentOut]:
    return [out(f, name) for f, name in await service.list_for(session, user, ref_type, ref_id)]


@router.get("/{file_id}", response_model=AttachmentOut, summary="File details")
async def get_file(
    file_id: uuid.UUID,
    user: Annotated[Principal, Depends(require("projects:read"))],
    session: SessionDep,
) -> AttachmentOut:
    record = await service.get(session, user, file_id)
    return out(record, None)


@router.get("/{file_id}/content", response_class=FileResponse, summary="Download or preview a file")
async def content(
    file_id: uuid.UUID,
    user: Annotated[Principal, Depends(require("projects:read"))],
    session: SessionDep,
    settings: SettingsDep,
    disposition: Literal["attachment", "inline"] = "attachment",
) -> FileResponse:
    record = await service.get(session, user, file_id)
    inline = disposition == "inline" and record.mime in service.PREVIEWABLE
    media_type = record.mime if record.mime in service.PREVIEWABLE else "application/octet-stream"
    name = quote(record.original_name)
    kind = "inline" if inline else "attachment"
    return FileResponse(
        settings.data_dir / record.storage_path,
        media_type=media_type,
        headers={
            "Content-Disposition": f"{kind}; filename*=UTF-8''{name}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": FILE_CSP,
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
    )


@router.delete("/{file_id}", status_code=204, summary="Delete an attachment")
async def delete(
    file_id: uuid.UUID,
    row_version: Annotated[int, Query(ge=1)],
    user: Annotated[Principal, Depends(require("files:delete"))],
    session: SessionDep,
) -> None:
    await service.delete(session, user, file_id, row_version)
