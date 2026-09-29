"""Pydantic schemas for the orders module.

`po_number` is never an input — Q564 allocates it from `po_number_seq` inside
the INSERT. `cutlist_no` is never an input either: Q428 sources it from the
parent Joinery Item's cutlist, and Q430/Q431 keep it in step automatically, so
accepting one from a caller would let it drift.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


# The values `purchase_orders_status_check` / `purchase_orders_priority_check`
# allow (migration 0002). Hand-kept copies: `test_the_accepted_statuses_are_
# exactly_the_databases` / `..._priorities_...` fail if a migration changes one
# and not the other. Without them an unknown value reached the SQL and came back
# as a raw 500. (`category` is *not* here: it is a lookup table IT can extend
# without a migration, Q557, so it is checked against the table instead.)
OrderStatus = Literal[
    "Draft", "Pending", "Approved", "Rejected", "Delivered",
    "Cancelled", "Hold", "Quote", "Next",
]
OrderPriority = Literal["High", "Medium", "Low", "Next", "Hold", "Quote"]


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
    # §L Q511/Q512 — field-level optimistic concurrency.
    field_versions: dict[str, int] = {}


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
    priority: OrderPriority = "Medium"
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
    """`vendor_id`, `description`, `category`, `status` and `priority` are typed
    nullable only so the field can be *omitted* (like `PatchOrderLineIn`'s
    `NOT NULL` columns); an explicit `null` is refused, as a clean 422, by the
    validator below. Three of them are `NOT NULL` columns, where a null was a raw
    500. `status` and `priority` are the dangerous pair: their columns are
    nullable and NULL satisfies the CHECK, so an explicit `null` was *written* —
    and because the route commits before FastAPI validates the response, the NULL
    persisted and then every read of the order, including the workspace-wide
    `GET /orders` behind the Orderbook page, 500'd on `OrderOut.status: str` /
    `priority: str`. `status` / `priority` values are checked as `Literal`s
    against the DB CHECKs; `category` and `vendor_id` reference rows, so
    `patch_order` checks them against the database."""
    vendor_id: int | None = None
    description: str | None = None
    category: str | None = None
    status: OrderStatus | None = None
    priority: OrderPriority | None = None
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
    # §L Q511/Q512 — optional expected versions, read from a prior GET's
    # `field_versions`. A named field whose version has moved on is a 409
    # FIELD_CONFLICT rather than a silent overwrite; omitting it (or a field)
    # keeps last-write-wins for that field.
    expected_versions: dict[str, int] | None = None

    # Runs only for a field the caller supplied (defaults are not validated),
    # so it rejects an explicit `null` and leaves an omitted field alone —
    # and, unlike a model-level validator, the 422 names the field.
    @field_validator("vendor_id", "description", "category", "status", "priority")
    @classmethod
    def _no_null(cls, v, info: ValidationInfo):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class CreateOrderLineIn(BaseModel):
    item_description: str
    quantity: Decimal
    unit_price: Decimal
    sku: str | None = None
    unit: str | None = None
    material_table: str | None = None
    material_id: int | None = None
    attributes: dict = Field(default_factory=dict)


class PatchOrderLineIn(BaseModel):
    """`material_table` / `material_id` are provenance (which catalog row a
    generated line came from, if any) and `line_number` is immutable — none
    are patchable here. No `expected_versions`: field-level optimistic
    concurrency (§L Q511/Q512) is scoped to the three named surfaces
    (items, cutlist, the *order header*) and lines were never one of them.

    `item_description` / `quantity` / `unit_price` are `NOT NULL` columns on
    `po_line_items` (`CreateOrderLineIn` requires them for the same reason)
    — typed nullable only so the field can be *omitted* (unlike `sku` /
    `unit`, which the column allows to genuinely become NULL); the validator
    below rejects an explicit `null` for the three before it ever reaches
    `patch_line()`'s UPDATE, which would otherwise 500 on the column's own
    constraint instead of a clean 422."""
    item_description: str | None = None
    sku: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None

    @model_validator(mode="after")
    def _no_null_for_not_null_columns(self) -> "PatchOrderLineIn":
        for field in ("item_description", "quantity", "unit_price"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class CategoryOut(BaseModel):
    category_key: str
    label: str
