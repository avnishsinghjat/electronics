import uuid

from pydantic import BaseModel, Field


class BrandingOut(BaseModel):
    company_name: str | None
    has_logo: bool
    logo_url: str | None
    setup_complete: bool


class CompanyOut(BaseModel):
    company_name: str
    address: str | None
    gstin: str | None
    serial_prefix: str
    has_logo: bool
    row_version: int


class CompanyUpdate(BaseModel):
    row_version: int
    company_name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    gstin: str | None = Field(
        default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
    )
    serial_prefix: str = Field(default="SN", pattern=r"^[A-Z0-9]{1,8}$")


class NumberingOut(BaseModel):
    doc_type: str
    description: str
    prefix: str
    padding: int
    yearly_reset: bool
    example: str


class NumberingUpdate(BaseModel):
    prefix: str = Field(min_length=1, max_length=16)


class DataDirCheck(BaseModel):
    path: str
    exists: bool
    writable: bool
    free_bytes: int | None
    ok: bool
    detail: str | None


class SetupStatus(BaseModel):
    needs_setup: bool
    data_dir: DataDirCheck
    # Default document prefixes, shown by the wizard; empty once setup is complete.
    numbering: list[NumberingOut] = []


class SetupAdmin(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{3,64}$")
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    admin: SetupAdmin
    prefixes: dict[str, str] = Field(default_factory=dict)


class FileRef(BaseModel):
    id: uuid.UUID
    sha256: str
