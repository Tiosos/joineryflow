"""Schemas for item_document CRUD."""
from datetime import datetime

from pydantic import BaseModel, Field


class BindDocumentIn(BaseModel):
    file_blob_id: int
    label: str | None = Field(default=None, max_length=128)
    sort_order: int = 0


class PatchDocumentIn(BaseModel):
    label: str | None = Field(default=None, max_length=128)
    sort_order: int | None = None


class ItemDocumentOut(BaseModel):
    document_id: int
    item_id: int
    file_blob_id: int
    label: str | None
    sort_order: int
    uploaded_by: int | None
    uploaded_by_name: str | None = None
    uploaded_at: datetime
    # File metadata join
    original_filename: str | None = None
    byte_size: int | None = None
    mime_type: str | None = None
