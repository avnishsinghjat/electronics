import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_sample: bool
    row_version: int


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    division_id: uuid.UUID
    code: str
    name: str
    client_name: str
    client_po_ref: str | None
    start_date: date | None
    due_date: date | None
    status: str
    project_manager_id: uuid.UUID | None
    notes: str | None
    is_sample: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int
    page: int
    page_size: int
