"""Pydantic schemas for the items (tracking grid) module.

Column aliasing note (legacy FileMaker schema -> API contract):
  items.item_id   -> id
  items.num       -> item_number
  items.rm_no     -> room_no
  items.rm_desc   -> room_desc
  items.zone      -> zone  (varchar(16) in DB, exposed as str | None)
  items.stage     -> stage (site location, not lifecycle_stage)
  items.painting_req -> painting_required
  items.solid_surface_req -> solid_surface_required
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class StageDates(BaseModel):
    due_date: date | None
    done_date: date | None


class AvailabilityRollup(BaseModel):
    ready: int
    blocked: int


class TrackingItemRow(BaseModel):
    id: int
    item_number: int | None
    status: str | None
    stage: str | None          # site location (items.stage), not lifecycle stage
    zone: str | None           # varchar(16) in DB
    level: str | None
    room_no: str | None
    room_desc: str | None
    code: str | None
    description: str | None
    qty: int | None
    cutlist_owner_id: int | None
    cutlist_owner_name: str | None
    item_locked: bool
    stages: dict[str, StageDates]   # keyed by stage_key (REQ..INST)
    availability: AvailabilityRollup


class TrackingGridOut(BaseModel):
    project_id: int
    items: list[TrackingItemRow]


# ── Item detail schemas (GET /items/{id}) ──────────────────────────────────────


class PartOut(BaseModel):
    id: int
    module_id: int
    qty: int
    part_name: str | None
    len_mm: int | None
    wid_mm: int | None
    board_material: str | None   # resolved from board_materials.description via FK
    edge: str | None
    colour: str | None
    paint_instruction: str | None
    comment: str | None
    # parts table has no is_rev_c column — always False until a schema migration adds it
    is_rev_c: bool


class ModuleOut(BaseModel):
    id: int
    name: str | None
    parts: list[PartOut]


class HardwareLineOut(BaseModel):
    id: int
    catalog_id: int
    catalog_description: str | None
    catalog_supplier: str | None
    catalog_source_table: str | None  # material_type value from project_hardware_catalog
    qty: int
    note: str | None


class EditLogRow(BaseModel):
    log_id: int
    actor_id: int | None
    actor_name: str | None
    field: str
    old_value: str | None
    new_value: str | None
    ts: datetime


class LockWarning(BaseModel):
    owner_id: int
    owner_name: str
    last_edit_minutes_ago: int


# ── Availability schemas (GET /items/{id}/availability) ───────────────────────


class AvailabilityLine(BaseModel):
    line_id: int
    status: Literal["ready", "ordered", "none"]
    eta: date | None
    batch_id: int | None
    # Procurement Workbench v1 — additive per-line procurement metadata
    seq: int | None = None
    catalog_id: int | None = None
    material_type: Literal[
        "BOARD", "HARDWARE", "CUSTOM", "BENCHTOP", "APPLIANCE", "HIRE"
    ] | None = None
    material_id: int | None = None
    qty_needed: Decimal = Decimal("0")
    qty_received: Decimal = Decimal("0")
    qty_on_order: Decimal = Decimal("0")
    qty_allocated_to_line: Decimal = Decimal("0")
    earliest_eta: date | None = None


class AvailabilityOut(BaseModel):
    item_id: int
    lines: list[AvailabilityLine]


class ItemOut(BaseModel):
    id: int
    project_id: int
    item_number: int | None
    status: str | None
    stage: str | None
    zone: str | None          # legacy varchar(16), matches T10
    level: str | None
    room_no: str | None
    room_desc: str | None
    code: str | None
    description: str | None
    qty: int | None
    cutlist_owner_id: int | None
    item_locked: bool
    estimator_notes: str | None
    painting_required: bool | None    # DB col: painting_req
    solid_surface_required: bool | None  # DB col: solid_surface_req
    group_id: str | None
    stages: dict[str, StageDates]
    modules: list[ModuleOut]
    hardware_lines: list[HardwareLineOut]
    edit_log: list[EditLogRow]
    lock_warning: LockWarning | None


# ── Write input models (T15) ───────────────────────────────────────────────────


class CreateItemIn(BaseModel):
    """Payload for POST /projects/{pid}/items."""
    description: str | None = None
    qty: int | None = None
    stage: str | None = None
    code: str | None = None
    level: str | None = None
    room_no: str | None = None     # DB col: rm_no
    room_desc: str | None = None   # DB col: rm_desc
    zone: str | None = None        # varchar(16) in DB


class PatchItemIn(BaseModel):
    """Payload for PATCH /items/{id}.

    Status and lifecycle_stage are excluded — those go through T16 endpoints.
    status_symbol is a varchar FK to status_symbols; excluded here (no _id alias).
    """
    description: str | None = None
    qty: int | None = None
    stage: str | None = None
    code: str | None = None
    level: str | None = None
    room_no: str | None = None
    room_desc: str | None = None
    zone: str | None = None
    estimator_notes: str | None = None
    painting_required: bool | None = None    # DB col: painting_req
    solid_surface_required: bool | None = None  # DB col: solid_surface_req


class LockTransferIn(BaseModel):
    """Payload for POST /items/{id}/lock when transferring ownership."""
    owner_id: int


# ── T16 write input models ─────────────────────────────────────────────────────


class PatchItemStatusIn(BaseModel):
    """Payload for PATCH /items/{id}/status.

    Valid values match status_options.status_key rows seeded by tests and
    migrations. The spec names are CLEAR | VOID | NOTE! | LIVE | APPROVED | HOLD.
    No transition graph is enforced (spec §6.2 v1).
    """
    status: Literal["CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"]
    note: str | None = None


class PatchLifecycleIn(BaseModel):
    """Payload for PATCH /items/{id}/lifecycle/{stage_key}.

    Both fields are optional; send only what needs changing.
    """
    due_date: date | None = None
    done_date: date | None = None
