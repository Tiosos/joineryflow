from pydantic import BaseModel


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
