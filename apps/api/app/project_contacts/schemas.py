"""Pydantic schemas for project_contact CRUD."""
from typing import Literal

from pydantic import BaseModel, Field
from ..schema_guards import no_null

ContactKind = Literal["office", "site"]


class CreateContactIn(BaseModel):
    kind: ContactKind
    name: str = Field(min_length=1, max_length=128)
    position: str | None = None
    email: str | None = None
    mobile: str | None = None
    notes: str | None = None
    sort_order: int = 0


class PatchContactIn(BaseModel):
    # An explicit null on a NOT NULL column is a raw 500 (schema_guards.py).
    reject_null = no_null("kind", "name", "sort_order")
    kind: ContactKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    position: str | None = None
    email: str | None = None
    mobile: str | None = None
    notes: str | None = None
    sort_order: int | None = None
