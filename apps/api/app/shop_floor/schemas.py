"""Pydantic v2 schemas for shop_floor (sub-project #8).

Wire format for the Foreman office board + station kiosk + assignment
lifecycle endpoints. Mirrors §7.1 of the shop-floor design spec, with
the per-item PAINTED ordering carried by `paint_after_assembly`.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ShopFloorStage = Literal["DOWN", "CNC", "EDGED", "PAINTED", "MADE"]
AssignmentStatus = Literal["assigned", "in_progress", "done", "cancelled"]


# --- Inputs ---------------------------------------------------------------

class AssignIn(BaseModel):
    stage_key: ShopFloorStage
    worker_id: int
    note: str | None = Field(default=None, max_length=500)


class PatchAssignmentIn(BaseModel):
    """Either reassign (worker_id) or update note. Reassign clears
    started_at and resets status to 'assigned'."""
    worker_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class CompleteIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class WorkerToggleIn(BaseModel):
    is_shop_worker: bool


# --- Outputs --------------------------------------------------------------

class AssignmentOut(BaseModel):
    assignment_id: int
    item_id: int
    stage_key: ShopFloorStage
    worker_id: int
    worker_name: str | None = None
    status: AssignmentStatus
    note: str | None = None
    assigned_by: int
    assigned_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cancelled_at: datetime | None = None


class WorkerOut(BaseModel):
    id: int
    full_name: str
    email: str
    is_shop_worker: bool


class BoardCard(BaseModel):
    item_id: int
    item_number: int
    code: str | None = None
    description: str | None = None
    painting_req: bool
    paint_after_assembly: bool
    next_stage_key: ShopFloorStage
    assignment: AssignmentOut | None = None  # null = unassigned


class BoardOut(BaseModel):
    project_id: int
    project_code: str
    columns: dict[str, list[BoardCard]]


class StationCard(BaseModel):
    assignment_id: int
    item_id: int
    item_number: int
    code: str | None = None
    description: str | None = None
    room_no: str | None = None
    room_desc: str | None = None
    project_code: str
    stage_key: ShopFloorStage
    status: AssignmentStatus
    assigned_at: datetime
    started_at: datetime | None = None
    note: str | None = None


class StationOut(BaseModel):
    worker_id: int
    worker_name: str
    cards: list[StationCard]


class RecentCompletionOut(BaseModel):
    log_id: int
    item_id: int
    item_number: int
    stage_key: ShopFloorStage
    completed_at: datetime
    note: str | None = None


class CompleteOut(BaseModel):
    log_id: int
    assignment_id: int
    lifecycle_advanced: bool
    next_stage_key: ShopFloorStage | None = None


class UndoOut(BaseModel):
    log_id: int
    assignment_id: int
    item_id: int
    stage_key: ShopFloorStage
