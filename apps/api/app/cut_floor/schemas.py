"""Pydantic v2 schemas for cut_floor routes (sub-project #7c).

Wire formats for CutPlan + CutSchedule. Mirrors §4.3 / §4.4 of the
cabinet-vision design spec.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

CutScheduleStatus = Literal["planned", "running", "done", "cancelled"]


# --- CutPlan input -----------------------------------------------------------

class PartSlotIn(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)
    label: str | None = Field(default=None, max_length=128)
    part_id: int | None = None


class CutSheetIn(BaseModel):
    sheet_no: int = Field(ge=1)
    material_sku: str = Field(min_length=1, max_length=128)
    slots: list[PartSlotIn] = Field(default_factory=list)


class CutPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    notes: str | None = None
    sheets: list[CutSheetIn] = Field(default_factory=list)


# --- CutPlan output ----------------------------------------------------------

class PartSlotOut(BaseModel):
    id: int
    x: float
    y: float
    w: float
    h: float
    label: str | None = None
    part_id: int | None = None
    is_foreign: bool = False


class CutSheetOut(BaseModel):
    id: int
    sheet_no: int
    material_sku: str
    slots: list[PartSlotOut] = Field(default_factory=list)


class CutPlanSummary(BaseModel):
    id: int
    name: str
    project_id: int
    notes: str | None = None
    created_by: int | None = None
    created_at: datetime
    sheet_count: int = 0
    slot_count: int = 0


class CutPlanOut(BaseModel):
    id: int
    name: str
    project_id: int
    notes: str | None = None
    created_by: int | None = None
    created_at: datetime
    sheets: list[CutSheetOut] = Field(default_factory=list)


class ItemCutPlanOut(BaseModel):
    """Returned by GET /items/{iid}/cut-plan. `plan` is null when the
    item's project has no cut plans."""
    plan: CutPlanSummary | None = None
    sheets: list[CutSheetOut] = Field(default_factory=list)


# --- CutSchedule -------------------------------------------------------------

class CutScheduleIn(BaseModel):
    cut_plan_id: int
    scheduled_for: date
    assigned_to: int | None = None


class CutSchedulePatchIn(BaseModel):
    scheduled_for: date | None = None
    assigned_to: int | None = None
    status: CutScheduleStatus | None = None
    priority: int | None = None


class ReorderIn(BaseModel):
    scheduled_for: date
    ordered_ids: list[int] = Field(min_length=1)


class CutScheduleOut(BaseModel):
    id: int
    cut_plan_id: int
    cut_plan_name: str | None = None
    project_id: int | None = None
    scheduled_for: date | None = None
    status: CutScheduleStatus
    priority: int
    assigned_to: int | None = None
    assigned_to_full_name: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None
