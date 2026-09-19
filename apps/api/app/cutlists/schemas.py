"""Pydantic schemas for the cutlist module.

`cutlist_no` is **never** an input. Q442 makes it system-allocated from
`joinery_number_seq`, so no create or patch payload carries it.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class CutlistItemRow(BaseModel):
    """An item linked to a cutlist, as the detail view lists them."""
    item_id: int
    item_number: int | None
    code: str | None
    description: str | None
    status: str | None
    room_no: str | None
    room_desc: str | None


class CutlistOut(BaseModel):
    cutlist_id: int
    project_id: int
    cutlist_no: int
    name: str | None
    item_count: int
    created_by: int | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class CutlistDetailOut(CutlistOut):
    items: list[CutlistItemRow]


class CutlistListOut(BaseModel):
    project_id: int
    cutlists: list[CutlistOut]


class CreateCutlistIn(BaseModel):
    """`cutlist_no` is deliberately absent — see the module docstring."""
    name: str | None = Field(default=None, max_length=255)


class PatchCutlistIn(BaseModel):
    name: str | None = Field(default=None, max_length=255)


class LinkItemIn(BaseModel):
    item_id: int
