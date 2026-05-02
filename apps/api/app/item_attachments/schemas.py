"""Pydantic schemas for the item attachment subsystem."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AttachmentKind = Literal["cv_drawing", "floor_plan", "site_measure"]


class AttachmentSlotOut(BaseModel):
    """One of the three slots; populated or empty."""
    kind: AttachmentKind
    file_blob_id: int | None = None
    original_filename: str | None = None
    byte_size: int | None = None
    uploaded_by: int | None = None
    uploaded_by_name: str | None = None
    uploaded_at: datetime | None = None


class AttachmentsBundleOut(BaseModel):
    """Always exactly 3 slots in canonical order: cv_drawing, floor_plan, site_measure."""
    item_id: int
    slots: list[AttachmentSlotOut]


class BindAttachmentIn(BaseModel):
    file_blob_id: int
