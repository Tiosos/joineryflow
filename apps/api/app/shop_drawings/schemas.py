from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RevisionStatus = Literal["draft", "pending", "approved", "rejected"]


class CreateDrawingIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    room: str | None = None
    file_blob_id: int
    submit_immediately: bool = False  # if True, rev 1 lands in 'pending'


class PatchDrawingIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    room: str | None = None


class CreateRevisionIn(BaseModel):
    file_blob_id: int


class RejectIn(BaseModel):
    review_note: str = Field(min_length=1, max_length=2000)


class RevisionOut(BaseModel):
    revision_id: int
    rev_no: int
    status: RevisionStatus
    file_blob_id: int
    file_mime: str
    uploaded_by: int
    uploaded_by_name: str | None
    uploaded_at: datetime
    reviewed_by: int | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_note: str | None


class DrawingCardOut(BaseModel):
    """Shape returned by the list endpoint — flat, optimized for the card grid."""
    drawing_id: int
    project_id: int
    project_code: str
    title: str
    room: str | None
    archived_at: datetime | None
    current_revision_id: int | None
    # latest revision metadata (may be the same as current, or newer in_review)
    latest_rev_no: int
    latest_status: RevisionStatus
    latest_uploaded_at: datetime
    latest_uploaded_by_name: str | None
    latest_reviewed_at: datetime | None
    latest_reviewed_by_name: str | None
    latest_file_blob_id: int


class DrawingListOut(BaseModel):
    drawings: list[DrawingCardOut]
    total: int
    awaiting_review: int  # count of drawings whose latest revision is 'pending'
    distinct_rooms: int


class DrawingDetailOut(BaseModel):
    drawing_id: int
    project_id: int
    project_code: str
    title: str
    room: str | None
    current_revision_id: int | None
    archived_at: datetime | None
    archived_by: int | None
    created_by: int
    created_at: datetime
    revisions: list[RevisionOut]
