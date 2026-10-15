"""Schemas for the order pop-up's tabs (migration 0064)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from ..schema_guards import no_null


class DeliveryOut(BaseModel):
    delivery_id: int
    qty: Decimal
    date_received: date
    signed_by: str | None
    notes: str | None
    has_docket: bool
    docket_mime: str | None
    created_at: datetime


class DeliveryLogOut(BaseModel):
    """`sum_received` and `remaining` are worked out here (`remaining` is None when the order has no qty)."""
    quantity: Decimal | None
    deliveries: list[DeliveryOut]
    sum_received: Decimal
    remaining: Decimal | None


class DeliveryIn(BaseModel):
    qty: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    date_received: date
    signed_by: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class PatchDeliveryIn(BaseModel):
    reject_null = no_null("qty", "date_received")
    qty: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    date_received: date | None = None
    signed_by: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class StockRowOut(BaseModel):
    po_id: int
    quantity: Decimal | None
    product_code: str | None
    project_name: str | None
    description: str
    total_amount: Decimal | None
    category: str


class StockOut(BaseModel):
    stock: list[StockRowOut]


class TrackingItemOut(BaseModel):
    item_id: int
    item_number: int
    description: str | None
    qty: int | None
    date_made: date | None


class TrackingOut(BaseModel):
    """The Tracking item this order is for (None when it is not linked to one), with the order's own number."""
    order_number: str
    description: str
    quantity: Decimal | None
    item: TrackingItemOut | None


class CutlistRowOut(BaseModel):
    cutlist_no: int
    created_at: datetime
    project_name: str
    item_description: str | None


class CutlistsOut(BaseModel):
    """Cutlists whose items use this order's product (the catalog row with the order's product code as SKU)."""
    product_found: bool
    cutlists: list[CutlistRowOut]
