"""Pydantic v2 schemas for the catalog module."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CatalogTable = Literal[
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
    "edging_materials",
    "glass_materials",
]


class _EnrichmentFields(BaseModel):
    """Fields added to every catalog table by migration 0017."""
    synonyms: list[str] = Field(default_factory=list)
    default_supplier: str | None = Field(default=None, max_length=128)
    # The supplier link (`vendors`). Checked against the caller's workspace by
    # the route. Bulk import ignores it and matches `default_supplier` by name.
    default_supplier_id: int | None = None
    default_lead_time_days: int | None = Field(default=None, ge=0, le=999)
    # What Generate Orders and "add from catalog" start an order line's price from.
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=4)
    # The old system's product type (Glass, Supplies, Paint...): finer than the six tabs, kept as text.
    product_type: str | None = Field(default=None, max_length=64)


class CreateBoardIn(_EnrichmentFields):
    code: str = Field(min_length=1, max_length=32)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    colour: str | None = Field(default=None, max_length=128)
    substrate: str | None = Field(default=None, max_length=128)
    finish: str | None = Field(default=None, max_length=128)
    sided: str | None = Field(default=None, max_length=64)
    grain: str | None = Field(default=None, max_length=64)
    rating: str | None = Field(default=None, max_length=64)
    hmr: str | None = Field(default=None, max_length=64)
    product_website: str | None = Field(default=None, max_length=255)


class CreateGlassIn(_EnrichmentFields):
    """Glass (`0070`): the old Orders screen's glass fields. Sizes in mm; glass type and power point are free text."""
    sku: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=255)
    colour: str | None = Field(default=None, max_length=128)
    edge_finish: str | None = Field(default=None, max_length=128)
    glass_type: str | None = Field(default=None, max_length=128)
    power_point: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)
    length_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    width_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    thickness_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    shaped: bool = False


class CreateEdgingIn(_EnrichmentFields):
    """Edging (`0069`): the old Orders screen's edging fields. Roll length in metres, width and thickness in mm."""
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    colour: str | None = Field(default=None, max_length=128)
    edge_type: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)
    roll_length_m: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    edge_width_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    edge_thickness_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    glued: bool = False


class CreateHardwareIn(_EnrichmentFields):
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=128)
    hardware_type: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)


class CreateCustomMadeIn(_EnrichmentFields):
    internal_ref: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)


class CreateBenchtopIn(_EnrichmentFields):
    slab_id: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    colour: str | None = Field(default=None, max_length=128)
    underside: str | None = Field(default=None, max_length=128)
    edge_details: str | None = Field(default=None, max_length=128)
    laminate_supplier: str | None = Field(default=None, max_length=128)
    laminate_code: str | None = Field(default=None, max_length=64)
    finish: str | None = Field(default=None, max_length=128)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)
    bench_length_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    bench_width_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    thickness_mm: Decimal | None = Field(default=None, ge=0, max_digits=6, decimal_places=2)
    pieces: int | None = Field(default=None, ge=0, le=9999)
    joins: int | None = Field(default=None, ge=0, le=9999)
    cable_entry: int | None = Field(default=None, ge=0, le=9999)
    shaped: bool = False


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
    # The supplier link (`vendors`). Like `default_supplier` and
    # `default_lead_time_days`, an explicit null means "clear it" — the route
    # reads `model_fields_set`.
    default_supplier_id: int | None = None
    default_lead_time_days: int | None = Field(default=None, ge=0, le=999)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=4)
    product_type: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=64)


class PatchBoardIn(PatchBaseIn):
    code: str | None = Field(default=None, max_length=32)
    grain_locked: bool | None = None
    colour: str | None = Field(default=None, max_length=128)
    substrate: str | None = Field(default=None, max_length=128)
    finish: str | None = Field(default=None, max_length=128)
    sided: str | None = Field(default=None, max_length=64)
    grain: str | None = Field(default=None, max_length=64)
    rating: str | None = Field(default=None, max_length=64)
    hmr: str | None = Field(default=None, max_length=64)
    product_website: str | None = Field(default=None, max_length=255)


class PatchHardwareIn(PatchBaseIn):
    brand: str | None = Field(default=None, max_length=128)
    hardware_type: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)


class PatchGlassIn(PatchBaseIn):
    colour: str | None = Field(default=None, max_length=128)
    edge_finish: str | None = Field(default=None, max_length=128)
    glass_type: str | None = Field(default=None, max_length=128)
    power_point: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)
    length_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    width_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    thickness_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    shaped: bool | None = None         # NOT NULL column: an explicit null is dropped, never written


class PatchEdgingIn(PatchBaseIn):
    colour: str | None = Field(default=None, max_length=128)
    edge_type: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)
    roll_length_m: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    edge_width_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    edge_thickness_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    glued: bool | None = None          # NOT NULL column: an explicit null is dropped, never written


class PatchCustomMadeIn(PatchBaseIn):
    internal_ref: str | None = Field(default=None, max_length=64)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)


class PatchBenchtopIn(PatchBaseIn):
    slab_id: str | None = Field(default=None, max_length=64)
    grain_locked: bool | None = None
    colour: str | None = Field(default=None, max_length=128)
    underside: str | None = Field(default=None, max_length=128)
    edge_details: str | None = Field(default=None, max_length=128)
    laminate_supplier: str | None = Field(default=None, max_length=128)
    laminate_code: str | None = Field(default=None, max_length=64)
    finish: str | None = Field(default=None, max_length=128)
    um: str | None = Field(default=None, max_length=32)
    product_website: str | None = Field(default=None, max_length=255)
    bench_length_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    bench_width_mm: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    thickness_mm: Decimal | None = Field(default=None, ge=0, max_digits=6, decimal_places=2)
    pieces: int | None = Field(default=None, ge=0, le=9999)
    joins: int | None = Field(default=None, ge=0, le=9999)
    cable_entry: int | None = Field(default=None, ge=0, le=9999)
    shaped: bool | None = None         # NOT NULL column: an explicit null is dropped, never written


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


class BulkUnlinkedRow(BaseModel):
    """A created row that named a supplier no single supplier matches."""
    row_index: int
    default_supplier: str
    reason: str


class BulkImportOut(BaseModel):
    created: int
    errors: list[BulkRowError]
    # Created rows whose supplier name matched exactly one supplier.
    linked: int = 0
    # Created rows that named a supplier but were left unlinked.
    unlinked: list[BulkUnlinkedRow] = []


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
