"""Pydantic schemas for project_contract + variations (Plan V1 §16-17, Q491)."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..schema_guards import no_null


class VariationOut(BaseModel):
    variation_id: int
    project_id: int
    description: str
    amount_delta: Decimal
    created_at: datetime
    created_by: int | None = None
    # Q608: a Draft is not in the contract value; a manager or admin approves or rejects it.
    status: Literal["Draft", "Approved", "Rejected"]
    decided_by: int | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None


class ContractOut(BaseModel):
    project_id: int
    original_value: Decimal
    current_value: Decimal
    created_at: datetime
    created_by: int | None = None
    variations: list[VariationOut] = []


class CreateVariationIn(BaseModel):
    description: str = Field(min_length=1)
    amount_delta: Decimal


class PatchVariationIn(BaseModel):
    """Edit a Draft. An explicit null on either field is a 422 (both columns are NOT NULL)."""
    reject_null = no_null("description", "amount_delta")
    description: str | None = Field(default=None, min_length=1)
    amount_delta: Decimal | None = None


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
