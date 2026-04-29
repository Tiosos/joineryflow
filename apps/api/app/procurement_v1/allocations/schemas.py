"""Pydantic schemas for /batches/{bid}/allocations endpoints (Procurement Workbench v1)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allocation_id: int
    batch_id: int
    item_hardware_line_id: int
    qty_allocated: Decimal
    created_at: datetime
    item_code: str | None = None
    item_description: str | None = None


class AllocationListOut(BaseModel):
    allocations: list[AllocationOut]
    qty_received: Decimal
    qty_allocated_total: Decimal
    qty_remaining: Decimal


class CreateAllocationIn(BaseModel):
    item_hardware_line_id: int
    qty_allocated: Decimal = Field(gt=0)


class PatchAllocationIn(BaseModel):
    qty_allocated: Decimal = Field(gt=0)
