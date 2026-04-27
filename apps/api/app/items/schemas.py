"""Pydantic schemas for the items (tracking grid) module.

Column aliasing note (legacy FileMaker schema -> API contract):
  items.item_id   -> id
  items.num       -> item_number
  items.rm_no     -> room_no
  items.rm_desc   -> room_desc
  items.zone      -> zone  (varchar(16) in DB, exposed as str | None)
  items.stage     -> stage (site location, not lifecycle_stage)
"""
from datetime import date

from pydantic import BaseModel


class StageDates(BaseModel):
    due_date: date | None
    done_date: date | None


class AvailabilityRollup(BaseModel):
    ready: int
    blocked: int


class TrackingItemRow(BaseModel):
    id: int
    item_number: int | None
    status: str | None
    stage: str | None          # site location (items.stage), not lifecycle stage
    zone: str | None           # varchar(16) in DB
    level: str | None
    room_no: str | None
    room_desc: str | None
    code: str | None
    description: str | None
    qty: int | None
    cutlist_owner_id: int | None
    cutlist_owner_name: str | None
    item_locked: bool
    stages: dict[str, StageDates]   # keyed by stage_key (REQ..INST)
    availability: AvailabilityRollup


class TrackingGridOut(BaseModel):
    project_id: int
    items: list[TrackingItemRow]
