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
    """`gst` and `total_inc` are the server's: GST is 10% of Ex while `gst_auto`, else the typed `gst`;
    Inc is Ex + GST (0063)."""
    order_id: int
    invoice_number: _Text100
    invoiced_date: date | None = None
    qty: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=3)
    payment_method_id: int | None = None
    total_ex: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    gst: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    gst_auto: bool = True
    notes: str | None = None


class PatchInvoiceIn(BaseModel):
    invoice_number: _Text100 | None = None
    invoiced_date: date | None = None
    qty: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=3)
    payment_method_id: int | None = None
    total_ex: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    gst: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    gst_auto: bool | None = None
    notes: str | None = None
    reject_null = no_null("invoice_number", "gst_auto")


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
    payment_method_id: int | None
    payment_method_name: str | None
    total_ex: Decimal | None
    gst: Decimal | None
    gst_auto: bool
    total_inc: Decimal | None
    notes: str | None
    delivery_doc_mime: str | None
    invoice_doc_mime: str | None
    non_delivery_mime: str | None
    created_at: datetime
    updated_at: datetime
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


class PoStaffOut(BaseModel):
    id: int
    full_name: str
    email: str
    has_photo: bool


class PoStaffListOut(BaseModel):
    staff: list[PoStaffOut]



class AuthorisationIn(BaseModel):
    """The Authorisation Form Details window. A deposit % OR an amount, never both."""
    payment_method_id: int | None = None
    deposit_pct: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    amount_required: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    date_required: date | None = None
    on_behalf_of_id: int | None = None


class AuthorisationOut(BaseModel):
    po_document_id: int
    purchase_order_amount: Decimal
    payment_method_id: int | None
    payment_method_name: str | None
    deposit_pct: Decimal | None
    amount_required: Decimal | None
    date_required: date | None
    on_behalf_of_id: int | None
    on_behalf_of_name: str | None
    form_created_at: datetime | None
    signed_mime: str | None
    updated_at: datetime | None
