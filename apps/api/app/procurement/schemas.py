"""Pydantic v2 schemas for the procurement module.

Ported from legacy/procurement_api.py. Names preserved 1:1.
"""
from datetime import date, time
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ── Enums ─────────────────────────────────────────────────────────────────────
class POStatus(str, Enum):
    draft = "Draft"
    pending = "Pending"
    approved = "Approved"
    rejected = "Rejected"
    delivered = "Delivered"
    cancelled = "Cancelled"
    hold = "Hold"
    quote = "Quote"
    next_ = "Next"


class POPriority(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"
    next_ = "Next"
    hold = "Hold"
    quote = "Quote"


class POCategory(str, Enum):
    it = "IT"
    office = "Office"
    logistics = "Logistics"
    facilities = "Facilities"
    services = "Services"
    other = "Other"


class VendorStatus(str, Enum):
    active = "Active"
    inactive = "Inactive"
    under_review = "Under Review"
    blacklisted = "Blacklisted"


class MovementType(str, Enum):
    incoming = "IN"
    outgoing = "OUT"
    adjustment = "ADJUSTMENT"
    returned = "RETURN"


class AttachmentType(str, Enum):
    file = "File"
    pdf = "PDF"
    image = "Image"


# ── Schemas ───────────────────────────────────────────────────────────────────
class LineItemCreate(BaseModel):
    line_number: int
    item_description: str
    sku: Optional[str] = None
    quantity: float
    unit: Optional[str] = None
    unit_price: float
    tax_rate: float = 10.0

    @field_validator("quantity", "unit_price")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


class POCreate(BaseModel):
    vendor_id: int
    requester_id: int
    cost_center_id: int

    description: str
    category: POCategory
    priority: POPriority = POPriority.medium

    order_number: Optional[str] = None
    cutlist_no: Optional[str] = None
    supplier_ref_no: Optional[str] = None
    order_type: Optional[str] = None

    project_name: Optional[str] = None
    location: Optional[str] = None

    required_date: Optional[date] = None
    requested_date: Optional[date] = None
    requested_time: Optional[time] = None
    date_ordered: Optional[date] = None
    due_date: Optional[date] = None
    arrived_date: Optional[date] = None

    product_code: Optional[str] = None
    product_website: Optional[str] = None
    product_description: Optional[str] = None
    product_image_path: Optional[str] = None
    stock_tracked: bool = False

    quantity: float = 1.0
    unit_of_measure: Optional[str] = None
    unit_cost: Optional[float] = None
    gst_applicable: bool = True
    gst_included_in_price: bool = False
    currency: str = "AUD"

    notes: Optional[str] = None
    line_item_comments: Optional[str] = None
    internal_comments: Optional[str] = None

    line_items: List[LineItemCreate] = []


class POUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[POCategory] = None
    priority: Optional[POPriority] = None
    status: Optional[POStatus] = None

    order_number: Optional[str] = None
    cutlist_no: Optional[str] = None
    supplier_ref_no: Optional[str] = None
    order_type: Optional[str] = None

    project_name: Optional[str] = None
    location: Optional[str] = None

    required_date: Optional[date] = None
    date_ordered: Optional[date] = None
    due_date: Optional[date] = None
    arrived_date: Optional[date] = None

    product_code: Optional[str] = None
    product_website: Optional[str] = None
    product_description: Optional[str] = None
    stock_tracked: Optional[bool] = None

    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    unit_cost: Optional[float] = None
    gst_applicable: Optional[bool] = None
    gst_included_in_price: Optional[bool] = None

    notes: Optional[str] = None
    line_item_comments: Optional[str] = None
    internal_comments: Optional[str] = None
    changelog: Optional[str] = None


class VendorCreate(BaseModel):
    name: str
    category: POCategory
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    payment_terms: Optional[str] = None


class ApprovalDecision(BaseModel):
    approver_id: int
    decision: str
    comments: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("Decision must be 'approve' or 'reject'")
        return v


class InventoryMovementCreate(BaseModel):
    item_id: int
    po_id: Optional[int] = None
    movement_type: MovementType
    quantity: float
    unit_cost: Optional[float] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[int] = None
