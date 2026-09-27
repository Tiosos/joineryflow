"""Pydantic schemas for project_contract + variations (Plan V1 §16-17, Q491)."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class VariationOut(BaseModel):
    variation_id: int
    project_id: int
    description: str
    amount_delta: Decimal
    created_at: datetime
    created_by: int | None = None


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


class ActualCostsOut(BaseModel):
    project_id: int
    materials_actual: Decimal
    labour_actual: Decimal
    total_actual: Decimal
    labour_by_item: dict[int, Decimal] = {}
