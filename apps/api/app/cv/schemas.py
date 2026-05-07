"""Pydantic v2 schemas for the CV import wizard (sub-project #7b).

Mirrors the wire format described in spec §6.3 + §6.5.
"""
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
SimpleCatalogTable = Literal[
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
]

ResolutionKind = Literal["mapped", "synonym_match", "unknown"]
CommitAction = Literal["use_existing", "create_new", "skip"]


# --- Errors ------------------------------------------------------------------

class CvRowError(BaseModel):
    row_index: int
    code: str  # INVALID_NUMERIC | INVALID_DIMENSION | MISSING_REQUIRED
    field: str | None = None
    value: str | None = None
    message: str


# --- Resolution payload (Phase A output, per row) ----------------------------

class CvRowResolution(BaseModel):
    """Per-row resolution from the resolver. Discriminated by `kind`."""
    kind: ResolutionKind
    target_table: CatalogTable | None = None
    target_material_id: int | None = None
    target_description: str | None = None
    hint: str | None = None  # e.g. "multiple_synonym_matches" when kind='unknown'


class CvParsedPart(BaseModel):
    row_index: int
    part_name: str
    qty: int
    len_mm: int
    wid_mm: int
    thickness_mm: int | None = None
    cv_code: str
    edge: str | None = None
    colour: str | None = None
    notes: str | None = None
    resolution: CvRowResolution


class CvParsedModule(BaseModel):
    module_no: int
    parts: list[CvParsedPart]


class CvUnknownCode(BaseModel):
    cv_code: str
    occurrences: int
    suggested_table: CatalogTable | None = None


class CvPreviewSummary(BaseModel):
    row_count: int
    mapped: int
    synonym: int
    unknown: int
    invalid: int


class CvPreviewOut(BaseModel):
    run_id: int
    summary: CvPreviewSummary
    modules: list[CvParsedModule]
    unknown_codes: list[CvUnknownCode]
    errors: list[CvRowError]


# --- Commit ------------------------------------------------------------------

class CvUseExistingResolution(BaseModel):
    action: Literal["use_existing"] = "use_existing"
    cv_code: str
    target_table: CatalogTable
    target_material_id: int


class CvCreateNewResolution(BaseModel):
    """Inline catalog row creation. Equipment Hire is intentionally excluded —
    that table requires a project_id FK and is steered through /catalog instead."""
    action: Literal["create_new"] = "create_new"
    cv_code: str
    target_table: SimpleCatalogTable
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    default_supplier: str | None = Field(default=None, max_length=128)
    default_lead_time_days: int | None = Field(default=None, ge=0, le=999)


class CvSkipResolution(BaseModel):
    action: Literal["skip"] = "skip"
    cv_code: str


CvCommitResolution = (
    CvUseExistingResolution | CvCreateNewResolution | CvSkipResolution
)


class CvCommitIn(BaseModel):
    resolutions: list[CvCommitResolution] = Field(default_factory=list)
    replace: bool = False


class CvCommitOut(BaseModel):
    run_id: int
    modules_created: int
    parts_created: int
    mappings_created: int
    catalog_rows_created: int
    replaced_module_ids: list[int]


# --- Run history -------------------------------------------------------------

class CvImportRunOut(BaseModel):
    cv_import_run_id: int
    project_id: int
    item_id: int
    source_filename: str
    sha256: str
    row_count: int
    status: Literal["preview", "committed", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    created_by: int


class CvImportRunDetailOut(BaseModel):
    """Returned by GET /cv-imports/{run_id}: the run row plus the cached
    preview snapshot (when status=preview|committed and snapshot present)."""
    model_config = ConfigDict(extra="allow")
    run: CvImportRunOut
    preview: CvPreviewOut | None = None
