"""Pydantic schemas for /batches endpoints (Procurement Workbench v1)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

MaterialType = Literal["BOARD", "HARDWARE", "CUSTOM", "BENCHTOP", "APPLIANCE", "HIRE"]
BatchStatus = Literal["OPEN", "IN_TRANSIT", "DELIVERED", "CANCELLED"]


class BatchOut(BaseModel):
    batch_id: int
    project_id: int
    material_type: MaterialType
    material_id: int
    supplier: str | None = None
    po_ref: str | None = None
    qty_ordered: Decimal
    qty_received: Decimal
    cost_per_unit: Decimal | None = None
    ordered_date: date | None = None
    eta_date: date | None = None
    received_date: date | None = None
    cancelled_at: datetime | None = None
    notes: str | None = None
    status: BatchStatus
    qty_allocated: Decimal


class BatchListOut(BaseModel):
    batches: list[BatchOut]


class CreateBatchIn(BaseModel):
    project_id: int
    material_type: MaterialType
    material_id: int
    supplier: str | None = None
    po_ref: str | None = None
    qty_ordered: Decimal = Field(ge=0)
    qty_received: Decimal = Field(default=Decimal("0"), ge=0)
    cost_per_unit: Decimal | None = None
    ordered_date: date | None = None
    eta_date: date | None = None
    received_date: date | None = None
    notes: str | None = None


class PatchBatchIn(BaseModel):
    supplier: str | None = None
    po_ref: str | None = None
    qty_ordered: Decimal | None = None
    qty_received: Decimal | None = None
    cost_per_unit: Decimal | None = None
    ordered_date: date | None = None
    eta_date: date | None = None
    received_date: date | None = None
    notes: str | None = None
