"""Schemas for project_lift_access upsert."""
from pydantic import BaseModel


class UpsertLiftAccessIn(BaseModel):
    notes: str | None = None
    sketch_file_blob_id: int | None = None
