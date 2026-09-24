from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    item_id: int
    num: int | None
    description: str | None
    take_version: int
    qty: Decimal


class SummaryLineOut(BaseModel):
    line_id: int
    material_type: str
    material_id: int | None
    description: str
    unit: str
    qty_consolidated: Decimal
    qty_confirmed: Decimal | None
    note: str | None
    stale: bool
    nest_sheets: int | None       # boards only: sheets in the latest CutPlan (Q582)
    qty_on_order: Decimal | None  # read-only, from the batch rollup (Q585)
    qty_received: Decimal | None
    sources: list[SourceOut]


class SummaryOut(BaseModel):
    summary_id: int
    project_id: int
    status: str
    confirmed_by: int | None
    confirmed_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    lines: list[SummaryLineOut]


class MissingTakeOut(BaseModel):
    item_id: int
    num: int | None
    description: str | None


class CurrentSummaryOut(BaseModel):
    summary: SummaryOut | None
    missing_takes: list[MissingTakeOut]


class SummaryListOut(BaseModel):
    summary_id: int
    status: str
    confirmed_by: int | None
    confirmed_at: datetime | None
    created_by: int
    created_at: datetime


class PatchSummaryLineIn(BaseModel):
    qty_confirmed: Decimal | None = Field(default=None, ge=0)
    note: str | None = None
