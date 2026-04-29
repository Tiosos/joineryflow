"""Pydantic schemas for /procurement-queue (Procurement Workbench v1, Task 13)."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

QueueStatus = Literal["OPEN", "IN_TRANSIT", "DELIVERED", "CANCELLED"]


class QueueRow(BaseModel):
    batch_id: int
    project_id: int
    project_code: str
    project_name: str
    supplier: str | None = None
    po_ref: str | None = None
    material_type: str
    material_id: int
    material_name: str | None = None
    qty_ordered: Decimal
    qty_received: Decimal
    eta_date: date | None = None
    status: QueueStatus


class QueueOut(BaseModel):
    rows: list[QueueRow]
