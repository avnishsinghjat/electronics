import uuid
from datetime import datetime

from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: uuid.UUID
    ref_type: str
    ref_id: uuid.UUID
    original_name: str
    mime: str
    size_bytes: int
    sha256: str
    uploaded_by: uuid.UUID | None
    uploaded_by_name: str | None
    created_at: datetime
    previewable: bool
    row_version: int
