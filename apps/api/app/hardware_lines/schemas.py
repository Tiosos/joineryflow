from typing import Literal

from pydantic import BaseModel

_SOURCE_TABLE_LITERAL = Literal[
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
]


class HardwareCatalogRow(BaseModel):
    catalog_id: int
    source_table: str  # 'board_materials' | 'hardware_materials' | 'custom_made' | 'benchtop_materials' | 'appliances' | 'equipment_hire'
    source_id: int
    sku: str | None
    name: str
    supplier: str | None
    unit_cost: float | None
    qty: float


class HardwareCatalogOut(BaseModel):
    project_id: int
    rows: list[HardwareCatalogRow]


# ── Write input models (T18) ──────────────────────────────────────────────────


class AddCatalogIn(BaseModel):
    """Payload for POST /projects/{pid}/hardware_catalog."""

    source_table: _SOURCE_TABLE_LITERAL
    source_id: int


class CreateHardwareLineIn(BaseModel):
    """Payload for POST /items/{id}/hardware_lines."""

    catalog_id: int
    qty: int = 1
    note: str | None = None


class PatchHardwareLineIn(BaseModel):
    """Payload for PATCH /hardware_lines/{lid}."""

    qty: int | None = None
    note: str | None = None
