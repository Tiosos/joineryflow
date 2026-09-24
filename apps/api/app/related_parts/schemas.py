"""Pydantic schemas for related parts (Plan V1 Q416-Q424, Q447-Q453).

Three fields are **never** inputs:

* `num` — allocated from `joinery_number_seq` (Q541), like every other item.
* `group_id` — Q416/Q453 make it the **parent's** Item ID; it follows the
  parent on a reparent (Q452) and is never typed.
* `cutlist_id` — a related part has no cutlist (Q417); `0028` has a CHECK.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class RelatedPartTypeOut(BaseModel):
    type_key: str
    label: str


class RelatedPartOut(BaseModel):
    item_id: int
    item_number: int | None
    parent_item_id: int
    parent_item_number: int | None
    group_id: str | None
    related_part_type_key: str
    related_part_type_label: str | None
    description: str | None
    qty: int | None
    status: str | None          # Q450: its own, not the parent's
    project_id: int
    created_at: datetime
    updated_at: datetime


class RelatedPartListOut(BaseModel):
    parent_item_id: int
    related_parts: list[RelatedPartOut]


class CreateRelatedPartIn(BaseModel):
    related_part_type_key: str
    description: str | None = None
    qty: int | None = None
    status: str | None = None   # defaults to CLEAR, like a Joinery Item


class PatchRelatedPartIn(BaseModel):
    related_part_type_key: str | None = None
    description: str | None = None
    qty: int | None = None
    status: str | None = None


class ReparentIn(BaseModel):
    """Q452 — move a related part to a different Joinery Item."""
    new_parent_item_id: int
