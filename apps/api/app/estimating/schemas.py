"""Pydantic v2 schemas for the estimating module — sub-project #9a.

Wire format for customer registry, estimate + revision lifecycle, line
breakdown CRUD, workspace labour rates, and Convert-to-Project.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ----------------------------------------------------------------------------
# Type literals — kept in sync with the SQL CHECK constraints in 0021
# ----------------------------------------------------------------------------

EstimateStatus = Literal[
    "draft", "sent", "accepted", "rejected", "expired", "withdrawn"
]
PartMaterialType = Literal["BOARD", "CUSTOM", "BENCHTOP"]
HardwareMaterialType = Literal["HARDWARE", "APPLIANCE"]
StageKey = Literal[
    "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED",
    "MADE", "DEL", "INST",
]
PaintInstruction = Literal["NONE", "DOUBLE_SIDE", "SINGLE_SIDE", "EDGE_ONLY"]


# ----------------------------------------------------------------------------
# Customer
# ----------------------------------------------------------------------------

class CreateCustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: str | None = None
    abn: str | None = Field(default=None, max_length=32)
    notes: str | None = None


class PatchCustomerIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: str | None = None
    abn: str | None = Field(default=None, max_length=32)
    notes: str | None = None


class CustomerOut(BaseModel):
    customer_id: int
    name: str
    email: str | None = None
    phone: str | None = None
    billing_address: str | None = None
    abn: str | None = None
    notes: str | None = None
    archived_at: datetime | None = None
    created_at: datetime


# ----------------------------------------------------------------------------
# Estimate header
# ----------------------------------------------------------------------------

class CreateEstimateIn(BaseModel):
    customer_id: int
    title: str = Field(min_length=1, max_length=255)
    site_address: str | None = None
    estimate_no: str | None = Field(default=None, max_length=64)


class PatchEstimateIn(BaseModel):
    customer_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    site_address: str | None = None


class EstimateSummaryOut(BaseModel):
    estimate_id: int
    estimate_no: str
    title: str
    site_address: str | None = None
    customer_id: int
    customer_name: str
    current_revision_id: int | None = None
    current_rev_no: int | None = None
    current_status: EstimateStatus | None = None
    current_total_inc_gst: Decimal | None = None
    converted_project_id: int | None = None
    created_at: datetime
    updated_at: datetime


class EstimateListOut(BaseModel):
    estimates: list[EstimateSummaryOut]


# ----------------------------------------------------------------------------
# Estimate revision
# ----------------------------------------------------------------------------

class PatchRevisionIn(BaseModel):
    markup_pct: Decimal | None = Field(default=None, ge=0)
    gst_pct: Decimal | None = Field(default=None, ge=0)
    terms_text: str | None = None
    expires_at: date | None = None


class RejectIn(BaseModel):
    lost_reason: str = Field(min_length=1)


class ExpireIn(BaseModel):
    lost_reason: str | None = None


class WithdrawIn(BaseModel):
    lost_reason: str | None = None


class LinePartOut(BaseModel):
    part_id: int
    material_type: PartMaterialType
    material_id: int | None = None
    sku_snapshot: str | None = None
    description_snapshot: str | None = None
    supplier_snapshot: str | None = None
    qty: Decimal
    len_mm: int | None = None
    wid_mm: int | None = None
    cost_per_unit_snapshot: Decimal
    cost_extended: Decimal
    paint_instruction: PaintInstruction
    comment: str | None = None


class LineHardwareOut(BaseModel):
    hw_id: int
    material_type: HardwareMaterialType
    material_id: int | None = None
    sku_snapshot: str | None = None
    description_snapshot: str | None = None
    supplier_snapshot: str | None = None
    qty: Decimal
    cost_per_unit_snapshot: Decimal
    cost_extended: Decimal
    comment: str | None = None


class LineLabourOut(BaseModel):
    labour_id: int
    stage_key: StageKey
    hours: Decimal
    rate_snapshot: Decimal
    cost_extended: Decimal


class LineOut(BaseModel):
    line_id: int
    seq: int
    description: str
    qty: Decimal
    unit: str
    has_breakdown: bool
    material_cost: Decimal
    labour_cost: Decimal
    total_cost: Decimal
    unit_sell_override: Decimal | None = None
    unit_sell: Decimal
    total_sell: Decimal
    notes: str | None = None
    parts: list[LinePartOut] = []
    hardware: list[LineHardwareOut] = []
    labour: list[LineLabourOut] = []


class RevisionDetailOut(BaseModel):
    revision_id: int
    estimate_id: int
    rev_no: int
    status: EstimateStatus
    markup_pct: Decimal
    gst_pct: Decimal
    terms_text: str | None = None
    workspace_stage_rates_snapshot: dict | None = None
    subtotal_cost: Decimal
    subtotal_sell: Decimal
    total_inc_gst: Decimal
    gst_amount: Decimal
    sent_at: datetime | None = None
    locked_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    expires_at: date | None = None
    lost_reason: str | None = None
    converted_project_id: int | None = None
    created_at: datetime
    lines: list[LineOut] = []


class EstimateDetailOut(BaseModel):
    estimate_id: int
    estimate_no: str
    title: str
    site_address: str | None = None
    customer: CustomerOut
    current_revision_id: int | None = None
    revisions: list[RevisionDetailOut] = []
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------------
# Lines + breakdown — draft-only mutations
# ----------------------------------------------------------------------------

class CreateLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    qty: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str = Field(default="EA", max_length=16)
    notes: str | None = None


class PatchLineIn(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=255)
    qty: Decimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=16)
    unit_sell_override: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    clear_unit_sell_override: bool = False


class ReorderLinesIn(BaseModel):
    ordered_line_ids: list[int]


class AddPartIn(BaseModel):
    material_type: PartMaterialType
    material_id: int
    qty: Decimal = Field(default=Decimal("1"), gt=0)
    len_mm: int | None = None
    wid_mm: int | None = None
    paint_instruction: PaintInstruction = "NONE"
    comment: str | None = None


class AddHardwareIn(BaseModel):
    material_type: HardwareMaterialType
    material_id: int
    qty: Decimal = Field(default=Decimal("1"), gt=0)
    comment: str | None = None


class PatchPartIn(BaseModel):
    qty: Decimal | None = Field(default=None, gt=0)
    len_mm: int | None = Field(default=None, ge=0)
    wid_mm: int | None = Field(default=None, ge=0)
    paint_instruction: PaintInstruction | None = None
    comment: str | None = None


class PatchHardwareIn(BaseModel):
    qty: Decimal | None = Field(default=None, gt=0)
    comment: str | None = None


class UpsertLabourIn(BaseModel):
    stage_key: StageKey
    hours: Decimal = Field(ge=0)


# ----------------------------------------------------------------------------
# Workspace labour rates (admin-only IT surface)
# ----------------------------------------------------------------------------

class LabourRateOut(BaseModel):
    stage_key: StageKey
    hourly_rate: Decimal
    effective_from: date
    updated_at: datetime


class LabourRateRow(BaseModel):
    stage_key: StageKey
    hourly_rate: Decimal = Field(ge=0)


class PatchLabourRatesIn(BaseModel):
    rates: list[LabourRateRow] = Field(min_length=1)


# ----------------------------------------------------------------------------
# Convert-to-Project
# ----------------------------------------------------------------------------

class ConvertResultOut(BaseModel):
    project_id: int
    project_code: str
    items_created: int
    parts_created: int
    hardware_lines_created: int
    project_hardware_catalog_added: int
