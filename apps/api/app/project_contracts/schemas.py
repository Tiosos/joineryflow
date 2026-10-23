"""Pydantic schemas for project_contract + variations (Plan V1 §16-17, Q491)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..schema_guards import no_null


class VariationItemOut(BaseModel):
    item_id: int
    num: int
    description: str | None = None


class VariationOut(BaseModel):
    variation_id: int
    project_id: int
    description: str
    amount_delta: Decimal       # the selling-price impact (Q612)
    created_at: datetime
    created_by: int | None = None
    created_by_name: str | None = None
    # Q611
    number: int
    reason: str | None = None
    requester: str | None = None
    requested_on: date | None = None
    cost_impact: Decimal | None = None
    time_impact_days: int | None = None
    # Q608: a Draft is not in the contract value; a manager or admin approves or rejects it.
    status: Literal["Draft", "Approved", "Rejected", "Voided"]
    decided_by: int | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    # Q610: a voided variation keeps its row and approval but stops counting.
    voided_by: int | None = None
    voided_by_name: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    # Q609: the Joinery Items it touches; empty = a project-level variation.
    items: list[VariationItemOut] = []


class ContractOut(BaseModel):
    project_id: int
    original_value: Decimal
    current_value: Decimal
    created_at: datetime
    created_by: int | None = None
    variations: list[VariationOut] = []


def _reason(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("reason cannot be blank")
    return v


class CreateVariationIn(BaseModel):
    description: str = Field(min_length=1)
    amount_delta: Decimal                                   # the selling-price impact
    reason: str = Field(min_length=1)
    requester: str | None = Field(default=None, max_length=255)
    requested_on: date | None = None                        # omitted = today
    cost_impact: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    time_impact_days: int | None = Field(default=None, ge=-36500, le=36500)
    item_ids: list[int] = []

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, v: str) -> str:
        return _reason(v)


class PatchVariationIn(BaseModel):
    """Edit a Draft. An explicit null on a NOT NULL field is a 422; the optional ones (requester, date, cost, time) clear."""
    reject_null = no_null("description", "amount_delta", "item_ids", "reason")
    description: str | None = Field(default=None, min_length=1)
    amount_delta: Decimal | None = None
    reason: str | None = Field(default=None, min_length=1)
    requester: str | None = Field(default=None, max_length=255)          # null clears
    requested_on: date | None = None
    cost_impact: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    time_impact_days: int | None = Field(default=None, ge=-36500, le=36500)
    item_ids: list[int] | None = None       # replaces the links; [] unlinks all; omitted leaves them

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, v: str | None) -> str | None:
        return v if v is None else _reason(v)


class VoidVariationIn(BaseModel):
    reason: str | None = None


class DecideVariationIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


class ActualCostsOut(BaseModel):
    project_id: int
    materials_actual: Decimal
    labour_actual: Decimal | None
    total_actual: Decimal | None
    unresolved_labour_completions: int = 0
    labour_by_item: dict[int, Decimal | None] = {}
