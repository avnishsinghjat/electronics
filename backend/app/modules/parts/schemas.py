import uuid

from pydantic import BaseModel, ConfigDict, Field


class PartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mpn: str
    manufacturer: str | None
    description: str
    package: str | None
    value: str | None
    category: str
    unit: str
    msl_level: int | None
    min_stock: int | None
    is_sample: bool
    row_version: int


class PartCreate(BaseModel):
    mpn: str = Field(min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=1, max_length=300)
    package: str | None = Field(default=None, max_length=64)
    value: str | None = Field(default=None, max_length=64)
    category: str = Field(default="Other", max_length=32)
    unit: str = Field(default="pcs", max_length=16)
    msl_level: int | None = Field(default=None, ge=1, le=6)


class PartStockSettings(BaseModel):
    row_version: int
    min_stock: int | None = Field(default=None, ge=0, le=100_000_000)
    msl_level: int | None = Field(default=None, ge=1, le=6)
