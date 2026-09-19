"""Pydantic schemas for suppliers.

**`vendors` IS the supplier entity** (Q506 + Q556) — there is no separate
`supplier` table, and this module is its only surface since Q565 retired the
legacy `/procurement/vendors*` endpoints.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class SupplierOut(BaseModel):
    vendor_id: int
    name: str
    category: str
    status: str
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    address: str | None
    rating: Decimal | None
    tax_id: str | None
    payment_terms: str | None
    # How many catalog rows point here, across the six tables (Q506's repoint).
    linked_material_count: int = 0
    created_at: datetime
    updated_at: datetime


class SupplierListOut(BaseModel):
    suppliers: list[SupplierOut]


class CreateSupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # `0031` replaced the frozen CHECK with the `order_category` lookup, so a
    # joinery category (Board, Hardware, …) is legal here now.
    category: str = "Other"
    contact_name: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=100)
    payment_terms: str | None = Field(default=None, max_length=100)


class PatchSupplierIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = None
    status: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    address: str | None = None
    rating: Decimal | None = Field(default=None, ge=0, le=5)
    tax_id: str | None = None
    payment_terms: str | None = None


class LinkMaterialIn(BaseModel):
    """Point a catalog row's supplier at this vendor (Q506).

    `material_table` is one of the six; `0029` added `supplier_id` and
    `default_supplier_id` to every one of them, beside the retained free text.
    """
    material_table: str
    material_id: int
    field: str = "supplier_id"   # or 'default_supplier_id'
