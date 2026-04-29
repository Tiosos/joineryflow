"""Pydantic schemas for the project material rollup endpoint."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

MaterialType = Literal["BOARD", "HARDWARE", "CUSTOM", "BENCHTOP", "APPLIANCE", "HIRE"]
MaterialStatus = Literal["OK", "SHORT", "OVERDUE"]


class MaterialRow(BaseModel):
    material_type: MaterialType
    material_id: int
    name: str
    sku: str | None = None
    qty_demand: Decimal
    qty_on_order: Decimal
    qty_received: Decimal
    qty_allocated: Decimal
    shortfall: Decimal
    earliest_eta: date | None = None
    status: MaterialStatus


class ProjectMaterialsOut(BaseModel):
    project_id: int
    rows: list[MaterialRow]
