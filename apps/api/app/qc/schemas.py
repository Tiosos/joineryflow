"""Schemas for the QC module: defects, checklist, rework (Q515-517)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateDefectIn(BaseModel):
    stage_key: str | None = None
    description: str = Field(min_length=1)


class PatchDefectIn(BaseModel):
    stage_key: str | None = None
    description: str | None = Field(default=None, min_length=1)


class ResolveDefectIn(BaseModel):
    resolved_note: str | None = None


class DefectOut(BaseModel):
    defect_id: int
    item_id: int
    stage_key: str | None
    description: str
    status: str
    resolved_note: str | None
    resolved_by: int | None
    resolved_by_name: str | None = None
    resolved_at: datetime | None
    created_by: int
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateChecklistItemIn(BaseModel):
    label: str = Field(min_length=1)
    sort_order: int = 0


class PatchChecklistItemIn(BaseModel):
    label: str | None = Field(default=None, min_length=1)
    is_checked: bool | None = None
    sort_order: int | None = None


class ChecklistItemOut(BaseModel):
    checklist_item_id: int
    item_id: int
    label: str
    is_checked: bool
    checked_by: int | None
    checked_by_name: str | None = None
    checked_at: datetime | None
    sort_order: int
    created_by: int
    created_at: datetime


class CreateReworkIn(BaseModel):
    kind: str = Field(pattern="^(internal|full)$")
    cause: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    responsibility: str | None = None
    cost: Decimal | None = None


class PatchReworkIn(BaseModel):
    cause: str | None = Field(default=None, min_length=1)
    scope: str | None = Field(default=None, min_length=1)
    responsibility: str | None = None
    cost: Decimal | None = None


class CloseReworkIn(BaseModel):
    closed_note: str | None = None


class ReworkOut(BaseModel):
    rework_id: int
    item_id: int
    kind: str
    cause: str
    scope: str
    responsibility: str | None
    cost: Decimal | None
    status: str
    closed_note: str | None
    closed_by: int | None
    closed_by_name: str | None = None
    closed_at: datetime | None
    created_by: int
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime


# ---- QC Dashboard (Plan V1 §4.2) — read-only aggregation -------------------

class DashboardStageCount(BaseModel):
    stage_key: str | None       # None = a defect raised without a stage
    label: str
    open: int


class DashboardDefectProject(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    open: int
    oldest_open_at: datetime
    by_stage: list[DashboardStageCount]


class DashboardReworkProject(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    internal: int
    full: int
    cost_total: Decimal         # sum of the costs that were recorded
    cost_missing: int           # open rework with no cost yet — total under-counts by these
    oldest_open_at: datetime


class DashboardItem(BaseModel):
    item_id: int
    num: int
    item_code: str | None
    description: str | None
    project_id: int
    project_code: str
    open_defects: int
    open_rework: int
    oldest_open_at: datetime


class DashboardScope(BaseModel):
    items_in_scope: int
    # Open records on items whose cutlist has not started, has finished, or does
    # not exist: kept out of every number below, but never hidden.
    open_defects_out_of_scope: int
    open_rework_out_of_scope: int


class QcDashboardOut(BaseModel):
    scope: DashboardScope
    defects_open: int
    defects_by_stage: list[DashboardStageCount]
    defects_by_project: list[DashboardDefectProject]
    rework_open: int
    rework_cost_total: Decimal
    rework_cost_missing: int
    rework_by_project: list[DashboardReworkProject]
    items: list[DashboardItem]
