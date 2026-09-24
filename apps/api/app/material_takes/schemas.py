from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

MaterialType = Literal["BOARD", "HARDWARE", "CUSTOM", "BENCHTOP", "APPLIANCE", "HIRE", "OTHER"]
Unit = Literal["sheet", "each", "m", "m2"]


class TakeLineOut(BaseModel):
    line_id: int
    material_type: MaterialType
    material_id: int | None
    description: str
    unit: Unit
    qty_generated: Decimal | None
    wastage_pct: Decimal
    qty: Decimal
    source: Literal["generated", "manual"]
    note: str | None


class TakeOut(BaseModel):
    take_id: int
    item_id: int
    version: int
    status: Literal["draft", "approved", "superseded"]
    generated_at: datetime
    approved_by: int | None
    approved_at: datetime | None
    created_by: int
    created_at: datetime
    notes: str | None
    lines: list[TakeLineOut]


class CurrentTakeOut(BaseModel):
    item_id: int
    draft: TakeOut | None
    approved: TakeOut | None
    outdated: bool  # live lines would now generate differently (Q583)


class TakeSummaryOut(BaseModel):
    take_id: int
    version: int
    status: str
    generated_at: datetime
    approved_by: int | None
    approved_at: datetime | None
    created_by: int
    created_at: datetime


class AddLineIn(BaseModel):
    material_type: MaterialType = "OTHER"
    material_id: int | None = None
    description: str = Field(min_length=1, max_length=300)
    unit: Unit
    qty: Decimal = Field(ge=0)
    wastage_pct: Decimal = Field(default=Decimal(0), ge=0)
    note: str | None = None


class PatchLineIn(BaseModel):
    material_type: MaterialType | None = None
    material_id: int | None = None
    description: str | None = Field(default=None, min_length=1, max_length=300)
    unit: Unit | None = None
    qty: Decimal | None = Field(default=None, ge=0)
    wastage_pct: Decimal | None = Field(default=None, ge=0)
    note: str | None = None


class ReviewIn(BaseModel):
    outcome: Literal["no_impact", "partial", "full"]
    note: str | None = None
