"""Pydantic schemas for the orders module.

`po_number` is never an input — Q564 allocates it from `po_number_seq` inside
the INSERT. `cutlist_no` is never an input either: Q428 sources it from the
parent Joinery Item's cutlist, and Q430/Q431 keep it in step automatically, so
accepting one from a caller would let it drift.
"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OrderLineOut(BaseModel):
    line_id: int
    line_number: int
    item_description: str
    sku: str | None
    quantity: Decimal
    unit: str | None
    unit_price: Decimal
    line_total: Decimal | None
    material_table: str | None
    material_id: int | None
    attributes: dict


class OrderOut(BaseModel):
    po_id: int
    po_number: str
    order_number: str | None
    supplier_ref_no: str | None
    status: str
    priority: str

    vendor_id: int
    vendor_name: str | None

    project_id: int | None
    project_name: str | None
    location: str | None

    # Q417/Q428: for a related part this is the PARENT's cutlist number. The
    # related part never holds one itself.
    item_id: int | None
    item_number: int | None
    cutlist_no: str | None

    category: str
    description: str
    product_code: str | None
    product_description: str | None

    quantity: Decimal | None
    unit_of_measure: str | None
    unit_cost: Decimal | None
    total_amount: Decimal | None
    currency: str | None

    required_date: date | None
    date_ordered: date | None
    due_date: date | None

    notes: str | None
    internal_comments: str | None
    attributes: dict

    created_at: datetime
    updated_at: datetime


class OrderDetailOut(OrderOut):
    lines: list[OrderLineOut]


class OrderListOut(BaseModel):
    orders: list[OrderOut]


class CreateOrderIn(BaseModel):
    """`po_number` and `cutlist_no` are deliberately absent — see the module
    docstring. `item_id` is what drives Q427's prefill."""
    vendor_id: int
    description: str
    category: str = "Other"

    item_id: int | None = None
    project_id: int | None = None
    # Free-text fallbacks; both are prefilled from the item when one is given.
    project_name: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)

    order_number: str | None = Field(default=None, max_length=50)
    supplier_ref_no: str | None = Field(default=None, max_length=100)
    priority: str = "Medium"
    product_code: str | None = Field(default=None, max_length=100)
    product_description: str | None = None

    quantity: Decimal | None = None
    unit_of_measure: str | None = Field(default=None, max_length=50)
    unit_cost: Decimal | None = None
    total_amount: Decimal | None = None

    required_date: date | None = None
    notes: str | None = None
    internal_comments: str | None = None
    attributes: dict = Field(default_factory=dict)


class PatchOrderIn(BaseModel):
    vendor_id: int | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    priority: str | None = None
    order_number: str | None = None
    supplier_ref_no: str | None = None
    location: str | None = None
    product_code: str | None = None
    product_description: str | None = None
    quantity: Decimal | None = None
    unit_of_measure: str | None = None
    unit_cost: Decimal | None = None
    total_amount: Decimal | None = None
    required_date: date | None = None
    date_ordered: date | None = None
    due_date: date | None = None
    notes: str | None = None
    internal_comments: str | None = None
    attributes: dict | None = None


class CreateOrderLineIn(BaseModel):
    item_description: str
    quantity: Decimal
    unit_price: Decimal
    sku: str | None = None
    unit: str | None = None
    material_table: str | None = None
    material_id: int | None = None
    attributes: dict = Field(default_factory=dict)


class CategoryOut(BaseModel):
    category_key: str
    label: str
