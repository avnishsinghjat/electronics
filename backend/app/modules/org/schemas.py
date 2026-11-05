import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.org.models import ProjectStatus

CODE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$"


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_sample: bool
    row_version: int


class DivisionCreate(BaseModel):
    code: str = Field(pattern=CODE)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class DivisionUpdate(BaseModel):
    row_version: int
    code: str | None = Field(default=None, pattern=CODE)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


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


class ProjectListItem(ProjectOut):
    division_code: str
    division_name: str
    project_manager_name: str | None
    module_count: int


class ProjectPage(BaseModel):
    items: list[ProjectListItem]
    total: int
    page: int
    page_size: int


class _ProjectFields(BaseModel):
    @model_validator(mode="after")
    def _dates(self) -> "_ProjectFields":
        start = getattr(self, "start_date", None)
        due = getattr(self, "due_date", None)
        if start and due and due < start:
            raise ValueError("Due date must not be before the start date")
        return self


class ProjectCreate(_ProjectFields):
    division_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    client_name: str = Field(min_length=1, max_length=200)
    client_po_ref: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    due_date: date | None = None
    status: ProjectStatus = ProjectStatus.DRAFT
    project_manager_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ProjectUpdate(_ProjectFields):
    row_version: int
    division_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    client_po_ref: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    due_date: date | None = None
    status: ProjectStatus | None = None
    project_manager_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ProjectClone(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    client_po_ref: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    due_date: date | None = None
    include_boq: bool = False


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    name: str
    qty_to_deliver: int
    description: str | None
    row_version: int


class ModuleCreate(BaseModel):
    code: str = Field(pattern=CODE)
    name: str = Field(min_length=1, max_length=200)
    qty_to_deliver: int = Field(ge=0, le=10_000_000)
    description: str | None = Field(default=None, max_length=2000)


class ModuleUpdate(BaseModel):
    row_version: int
    code: str | None = Field(default=None, pattern=CODE)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    qty_to_deliver: int | None = Field(default=None, ge=0, le=10_000_000)
    description: str | None = Field(default=None, max_length=2000)


class AssemblyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    module_id: uuid.UUID
    code: str
    board_name: str
    revision: str
    qty_per_module: int
    layer_count: int
    size_x_mm: Decimal | None
    size_y_mm: Decimal | None
    finish: str | None
    kicad_project_file_id: uuid.UUID | None
    assembly_drawing_file_id: uuid.UUID | None
    stage_template_id: uuid.UUID | None
    notes: str | None
    row_version: int


class _AssemblyFields(BaseModel):
    board_name: str | None = Field(default=None, min_length=1, max_length=200)
    revision: str | None = Field(default=None, min_length=1, max_length=16)
    qty_per_module: int | None = Field(default=None, ge=1, le=1000)
    layer_count: int | None = Field(default=None, ge=1, le=64)
    size_x_mm: Decimal | None = Field(default=None, gt=0, le=2000)
    size_y_mm: Decimal | None = Field(default=None, gt=0, le=2000)
    finish: str | None = Field(default=None, max_length=64)
    kicad_project_file_id: uuid.UUID | None = None
    assembly_drawing_file_id: uuid.UUID | None = None
    stage_template_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class AssemblyCreate(_AssemblyFields):
    code: str = Field(pattern=CODE)
    board_name: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=16)


class AssemblyUpdate(_AssemblyFields):
    row_version: int
    code: str | None = Field(default=None, pattern=CODE)


class ProjectTree(BaseModel):
    project: ProjectListItem
    modules: list["ModuleWithAssemblies"]


class ModuleWithAssemblies(ModuleOut):
    assemblies: list[AssemblyOut]


class StageTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_default: bool


class DirectoryUser(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    roles: list[str]


class HistoryEntry(BaseModel):
    id: int
    occurred_at: datetime
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: str
    label: str
    changed_fields: list[str] | None
