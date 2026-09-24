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


class CutlistPartRow(BaseModel):
    """A part on the cutlist, naming the item it belongs to.

    `plan_v1.md` §1218 (Q569): the cutlist details show the parts themselves.
    Flat across the cutlist rather than nested per item, because several items
    share one cutlist (Q410) and the whole sheet is cut together.
    """
    part_id: int
    item_id: int
    item_number: int | None
    module_name: str | None
    part_name: str | None
    qty: int | None
    len_mm: int | None
    wid_mm: int | None
    board_material: str | None
    edge: str | None
    colour: str | None
    paint_instruction: str | None
    comment: str | None


class CutlistHardwareRow(BaseModel):
    """A hardware line on the cutlist, resolved through project_hardware_catalog."""
    line_id: int
    item_id: int
    item_number: int | None
    catalog_description: str | None
    catalog_supplier: str | None
    catalog_source_table: str | None
    qty: int | None
    note: str | None


class CutlistDetailOut(CutlistOut):
    items: list[CutlistItemRow]
    parts: list[CutlistPartRow]
    hardware: list[CutlistHardwareRow]


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
