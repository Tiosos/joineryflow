"""Pydantic schemas for the parts module (modules + parts CRUD).

Schema drift notes vs. plan spec:
  - modules.module_no is NOT NULL UNIQUE(item_id, module_no) — required on create.
  - modules also has a `notes` column — exposed as optional on create/patch.
  - parts.board_material_id is an FK (bigint) to board_materials.material_id, NOT a text column.
    CreatePartIn / PatchPartIn accept board_material_id (int | None).
    PartOut.board_material (str | None) is the resolved description from the JOIN — that
    lives in items/schemas.py and is constructed by get_part().
  - parts.paint_instruction has a DB CHECK: NONE | DOUBLE_SIDE | SINGLE_SIDE | EDGE_ONLY.
  - parts.is_rev_c does NOT exist (no DB column per T11) — excluded from all input schemas.
    PartOut.is_rev_c is hardcoded False in the query layer.
"""
from typing import Literal

from pydantic import BaseModel


class CreateModuleIn(BaseModel):
    module_no: str
    name: str | None = None
    notes: str | None = None


class PatchModuleIn(BaseModel):
    name: str | None = None
    notes: str | None = None


_PaintInstruction = Literal["NONE", "DOUBLE_SIDE", "SINGLE_SIDE", "EDGE_ONLY"]


class CreatePartIn(BaseModel):
    qty: int = 1
    part_name: str | None = None
    len_mm: int | None = None
    wid_mm: int | None = None
    board_material_id: int | None = None   # FK to board_materials.material_id
    edge: str | None = None
    colour: str | None = None
    paint_instruction: _PaintInstruction | None = None
    comment: str | None = None
    # is_rev_c excluded — no DB column per T11


class PatchPartIn(BaseModel):
    qty: int | None = None
    part_name: str | None = None
    len_mm: int | None = None
    wid_mm: int | None = None
    board_material_id: int | None = None   # FK to board_materials.material_id
    edge: str | None = None
    colour: str | None = None
    paint_instruction: _PaintInstruction | None = None
    comment: str | None = None
