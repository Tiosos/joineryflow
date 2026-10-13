"""Schemas for PO documents (migration 0059): the PO screen over groups of orders."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from ..schema_guards import no_null

_Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreatePoIn(BaseModel):
    order_ids: list[int] = Field(min_length=1, max_length=200)
    reference_no: str | None = Field(default=None, max_length=100)
    ordered_by_id: int | None = None
    date_required: date | None = None
    date_due: date | None = None
    memo: str | None = None
    deliver_to: str | None = None

    @field_validator("order_ids")
    @classmethod
    def _unique(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))


class PatchPoIn(BaseModel):
    """`date_ordered` is a NOT NULL column: an explicit null is a 422, not a 500."""
    reference_no: str | None = Field(default=None, max_length=100)
    ordered_by_id: int | None = None
    date_ordered: date | None = None
    date_required: date | None = None
    date_due: date | None = None
    memo: str | None = None
    deliver_to: str | None = None
    reject_null = no_null("date_ordered")


class PoOrdersIn(BaseModel):
    order_ids: list[int] = Field(min_length=1, max_length=200)

    @field_validator("order_ids")
    @classmethod
    def _unique(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))


class DeliveryIn(BaseModel):
    """The delivery charge, ex GST (the Delivery Fee order carries the GST like any order)."""
    amount: Decimal = Field(ge=0, max_digits=15, decimal_places=2)


class InvoiceIn(BaseModel):
    order_id: int
    invoice_number: _Text100
    invoiced_date: date | None = None
    qty: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=3)
    total_inc: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    notes: str | None = None
    delivery_doc: str | None = Field(default=None, max_length=100)


class PatchInvoiceIn(BaseModel):
    invoice_number: _Text100 | None = None
    invoiced_date: date | None = None
    qty: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=3)
    total_inc: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    notes: str | None = None
    delivery_doc: str | None = Field(default=None, max_length=100)
    reject_null = no_null("invoice_number")


class PoLineOut(BaseModel):
    line_no: int
    order_id: int
    po_number: str
    status: str
    description: str
    product_code: str | None
    quantity: Decimal | None
    unit_of_measure: str | None
    unit_cost: Decimal | None
    total_amount: Decimal | None
    gst_amount: Decimal | None
    grand_total: Decimal | None
    requester_name: str | None
    project_name: str | None
    location: str | None
    item_number: int | None
    arrived_date: date | None
    has_attachment: bool
    is_delivery: bool
    invoiced: bool


class PoInvoiceOut(BaseModel):
    invoice_id: int
    order_id: int
    line_no: int | None
    invoice_number: str
    invoiced_date: date | None
    qty: Decimal | None
    total_inc: Decimal | None
    notes: str | None
    delivery_doc: str | None
    description: str | None
    product_code: str | None


class PoTotalsOut(BaseModel):
    """Over the lines that are not Cancelled or Rejected."""
    total_ex: Decimal
    gst: Decimal
    total_inc: Decimal


class PoOut(BaseModel):
    po_document_id: int
    po_no: int
    status: str
    vendor_id: int
    vendor_name: str
    vendor_address: str | None
    reference_no: str | None
    ordered_by_id: int | None
    ordered_by_name: str | None
    date_ordered: date
    date_required: date | None
    date_due: date | None
    memo: str | None
    deliver_to: str | None
    delivery_order_id: int | None
    delivery_charge: Decimal | None
    created_at: datetime
    updated_at: datetime
    lines: list[PoLineOut]
    invoices: list[PoInvoiceOut]
    totals: PoTotalsOut


class PoSummaryOut(BaseModel):
    po_document_id: int
    po_no: int
    status: str
    vendor_id: int
    vendor_name: str
    reference_no: str | None
    date_ordered: date
    line_count: int
    created_at: datetime


class PoListOut(BaseModel):
    purchase_orders: list[PoSummaryOut]
