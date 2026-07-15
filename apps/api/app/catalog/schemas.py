"""Pydantic v2 schemas for the catalog module."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CatalogTable = Literal[
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
]


class _EnrichmentFields(BaseModel):
    """Fields added to every catalog table by migration 0017."""
    synonyms: list[str] = Field(default_factory=list)
    default_supplier: str | None = Field(default=None, max_length=128)
    default_lead_time_days: int | None = Field(default=None, ge=0, le=999)


class CreateBoardIn(_EnrichmentFields):
    code: str = Field(min_length=1, max_length=32)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateHardwareIn(_EnrichmentFields):
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateCustomMadeIn(_EnrichmentFields):
    internal_ref: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateBenchtopIn(_EnrichmentFields):
    slab_id: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateApplianceIn(_EnrichmentFields):
    model_number: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateEquipmentHireIn(_EnrichmentFields):
    contract_ref: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    project_id: int


class PatchBaseIn(BaseModel):
    """All fields optional on PATCH. `synonyms` is nullable here (unlike on
    Create where it defaults to `[]`) so `model_dump(exclude_none=True)` does
    not silently zero the existing array when the client omits it."""
    synonyms: list[str] | None = None
    default_supplier: str | None = Field(default=None, max_length=128)
    default_lead_time_days: int | None = Field(default=None, ge=0, le=999)
    description: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=64)


class PatchBoardIn(PatchBaseIn):
    code: str | None = Field(default=None, max_length=32)
    grain_locked: bool | None = None


class PatchHardwareIn(PatchBaseIn):
    pass


class PatchCustomMadeIn(PatchBaseIn):
    internal_ref: str | None = Field(default=None, max_length=64)


class PatchBenchtopIn(PatchBaseIn):
    slab_id: str | None = Field(default=None, max_length=64)
    grain_locked: bool | None = None


class PatchApplianceIn(PatchBaseIn):
    model_number: str | None = Field(default=None, max_length=64)


class PatchEquipmentHireIn(PatchBaseIn):
    contract_ref: str | None = Field(default=None, max_length=64)
    project_id: int | None = None


class CatalogRowOut(BaseModel):
    """Permissive: routes return dict-of-mappings; this just labels it."""
    model_config = ConfigDict(extra="allow")
    type: str
    archived_at: datetime | None = None


class CatalogListOut(BaseModel):
    type: str
    rows: list[CatalogRowOut]


class BulkRowError(BaseModel):
    row_index: int
    error: str


class BulkImportIn(BaseModel):
    """Generic bulk-import body: a list of dicts shaped like CreateXIn for the
    target table. Validation is per-row inside the route; we keep this Any-shaped
    so the same schema serves all 6 tables."""
    rows: list[dict] = Field(min_length=1, max_length=1000)


class BulkImportOut(BaseModel):
    created: int
    errors: list[BulkRowError]


class CreateCvMappingIn(BaseModel):
    cv_code: str = Field(min_length=1, max_length=255)
    target_material_table: CatalogTable
    target_material_id: int
    notes: str | None = Field(default=None, max_length=2000)


class PatchCvMappingIn(BaseModel):
    cv_code: str | None = Field(default=None, max_length=255)
    target_material_table: CatalogTable | None = None
    target_material_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CvMappingOut(BaseModel):
    cv_material_mapping_id: int
    workspace_id: int
    cv_code: str
    target_material_table: CatalogTable
    target_material_id: int
    target_description: str | None = None
    notes: str | None = None
    created_by: int
    created_at: datetime
    updated_at: datetime


class CvMappingListOut(BaseModel):
    rows: list[CvMappingOut]
    total: int
