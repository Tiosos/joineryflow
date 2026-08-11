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


# --- Optimiser (sub-project #9 stub) -----------------------------------------

class OptimiseIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    material_sku: str = Field(min_length=1, max_length=128)
    # Optional since board_inventory (0025): when omitted, the sheet size is
    # taken from the largest in-stock sheet for `material_sku`. Supplying them
    # explicitly still wins, so ad-hoc stock the catalog doesn't know about can
    # be nested against.
    sheet_len_mm: float | None = Field(default=None, gt=0)
    sheet_wid_mm: float | None = Field(default=None, gt=0)
    kerf_mm: float = Field(default=3, ge=0)
    include_only_item_ids: list[int] | None = None
    strategy: Literal["maxrects", "naive"] = "maxrects"
    max_sheets: int = Field(default=20, ge=1, le=200)


class OptimiseSkip(BaseModel):
    label: str
    reason: str  # 'too_large' | 'no_room'
    part_id: int | None = None


class OptimiseSummary(BaseModel):
    total_parts: int
    placed: int
    skipped: int
    skipped_reasons: list[OptimiseSkip] = Field(default_factory=list)
    sheets_used: int
    utilization_pct: float  # mean across the sheets used
    sheet_utilization: list[float] = Field(default_factory=list)  # per-sheet
    # Sheet stock context (board_inventory, 0025). `sheets_available` is null
    # when the SKU has no stock recorded — that is "unknown", not "zero", so
    # the UI must not report a shortfall against it.
    sheet_len_mm: float | None = None
    sheet_wid_mm: float | None = None
    sheet_dims_from_stock: bool = False
    sheets_available: int | None = None
    sheet_shortfall: int = 0


# --- Board inventory (migration 0025) ----------------------------------------

class BoardInventoryIn(BaseModel):
    material_sku: str = Field(min_length=1, max_length=255)
    len_mm: int = Field(gt=0)
    wid_mm: int = Field(gt=0)
    qty_on_hand: int = Field(default=0, ge=0)
    location: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class BoardInventoryPatchIn(BaseModel):
    qty_on_hand: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class BoardInventoryOut(BaseModel):
    inventory_id: int
    material_id: int
    material_sku: str | None = None
    material_description: str | None = None
    grain_locked: bool = False
    len_mm: int
    wid_mm: int
    qty_on_hand: int
    location: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class OptimiseOut(BaseModel):
    """`proposal` is the identical shape accepted by
    POST /projects/{pid}/cut-plans — the user confirms then forwards it."""
    proposal: CutPlanIn
    summary: OptimiseSummary


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
