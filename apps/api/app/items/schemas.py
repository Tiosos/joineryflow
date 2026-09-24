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
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class StageDates(BaseModel):
    due_date: date | None
    done_date: date | None


class AvailabilityRollup(BaseModel):
    ready: int
    blocked: int


HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
VarBoq = Literal["BOQ", "VAR"]


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
    # Plan V1 Q420/Q422: related parts come back in the SAME list, directly
    # beneath their parent, collapsed by default.  The web nests on these two.
    # A related part has no stages at all (Q419), so `stages` is empty for it.
    row_type: str                   # 'joinery_item' | 'related_part'
    parent_item_id: int | None
    related_part_type_key: str | None
    # Q438: the cutlist this item belongs to — SHARED, so several rows carry
    # the same number.  None while the item has no cutlist (Q440).  Distinct
    # from `item_number`, which is the item's own Item ID (Q541).
    cutlist_id: int | None
    cutlist_no: int | None
    # Q417/Q567: the most recent ISSUED supplier order for this row
    # (`date_ordered IS NOT NULL`), which the Tracking grid shows in place of a
    # cutlist number on a related part.  None until an order is issued.
    issued_order_no: str | None
    issued_order_po_id: int | None
    # Q425: the O/BOOK sub-tab's columns — the latest order on this row in ANY
    # state, so a Draft raised a moment ago is visible. Distinct from
    # `issued_order_no`, which Q567 restricts to orders actually sent.
    order_po_id: int | None
    order_no: str | None
    order_status: str | None
    order_supplier: str | None
    order_due_date: date | None
    # Tracking 2.0 enrichment (#10)
    jid_code: str | None = None
    jid_color: str | None = None
    var_boq: VarBoq = "BOQ"
    contractor_id: int | None = None
    contractor_name: str | None = None
    total_amount: Decimal | None = None
    site_measure_notes: str | None = None
    site_measure_attachment_id: int | None = None
    # Existing items.* columns surfaced for legacy-parity grid (#10)
    floor_plan: str | None = None
    rls: str | None = None
    joiery_details: str | None = None
    painting_required: bool | None = None
    solid_surface_required: bool | None = None
    cutlist_printed: bool | None = None
    group_id: str | None = None
    item_code: str | None = None
    assembler: str | None = None
    lister: str | None = None
    hardware_line_count: int = 0


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
    area_id: int | None = None
    room_id: int | None = None
    stages: dict[str, StageDates]
    modules: list[ModuleOut]
    hardware_lines: list[HardwareLineOut]
    edit_log: list[EditLogRow]
    lock_warning: LockWarning | None
    # Tracking 2.0 enrichment (#10)
    jid_code: str | None = None
    jid_color: str | None = None
    var_boq: VarBoq = "BOQ"
    contractor_id: int | None = None
    contractor_name: str | None = None
    total_amount: Decimal | None = None
    site_measure_notes: str | None = None


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
    # Q454/Q455 — Area and Room as real entities (`0026`). Setting either also
    # writes the legacy `stage` / `rm_no` / `rm_desc` columns, which stay
    # populated until a later migration drops them (Q435), so the 25 read sites
    # that still use them keep working. Room is nested under Area (Q552), so a
    # room without an area is refused rather than silently unset.
    area_id: int | None = None
    room_id: int | None = None
    # Tracking 2.0 enrichment (#10)
    jid_code: str | None = None
    jid_color: HexColor | None = None
    var_boq: VarBoq | None = None
    contractor_id: int | None = None
    total_amount: Decimal | None = None
    site_measure_notes: str | None = None


class LockTransferIn(BaseModel):
    """Payload for POST /items/{id}/lock when transferring ownership."""
    owner_id: int


# ── T16 write input models ─────────────────────────────────────────────────────


StatusKey = Literal["CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"]


class PatchItemStatusIn(BaseModel):
    """Payload for PATCH /items/{id}/status.

    Valid values match status_options.status_key rows seeded by tests and
    migrations. The spec names are CLEAR | VOID | NOTE! | LIVE | APPROVED | HOLD.
    No transition graph is enforced (spec §6.2 v1).

    note is REQUIRED (matches item_status_log.note NOT NULL).
    """
    status: StatusKey
    note: str = Field(min_length=1)


class BulkItemStatusIn(BaseModel):
    """Payload for POST /items/bulk-status.  Bulk status change with shared note."""
    item_ids: list[int] = Field(min_length=1, max_length=500)
    status: StatusKey
    note: str = Field(min_length=1)


class BulkItemStatusOut(BaseModel):
    """Response from POST /items/bulk-status.

    not_found: ids that don't exist in the workspace.
    cross_workspace: ids that exist but belong to another workspace
      (returned distinct from not_found so the caller can show a clearer error).
    """
    updated: int
    not_found: list[int] = []
    cross_workspace: list[int] = []


class PatchLifecycleIn(BaseModel):
    """Payload for PATCH /items/{id}/lifecycle/{stage_key}.

    Both fields are optional; send only what needs changing.
    """
    due_date: date | None = None
    done_date: date | None = None


# ── Controlled Lock (B7 / Q509) ───────────────────────────────────────────────


class LockRequestOut(BaseModel):
    """A non-owner's held save on a locked item."""
    request_id: int
    item_id: int
    requested_by: int
    requested_by_name: str | None = None
    requested_changes: dict
    status: Literal["pending", "approved", "rejected"]
    created_at: datetime
    updated_at: datetime
    decided_by: int | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None


class LockRequestDecisionIn(BaseModel):
    """Payload for POST /lock-requests/{rid}/{approve,reject}.  Note is optional."""
    note: str | None = None
