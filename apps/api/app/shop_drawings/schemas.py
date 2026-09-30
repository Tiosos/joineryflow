from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RevisionStatus = Literal["draft", "pending", "approved", "rejected"]
DrawingType = Literal["IFA", "IFC"]

# Register queues (Tg Register sidebar), derived from the latest revision's
# status + the drawing's submitted_at / archived_at — nothing is stored.
#   being_drawn      latest revision is a draft
#   internal_review  latest revision is pending
#   update_required  latest revision was rejected
#   completed        latest revision is approved
#   awaiting_submission  approved and not yet submitted to the builder
#   submitted        submitted_at is set
#   archive          archived
Queue = Literal[
    "all", "being_drawn", "internal_review", "update_required",
    "completed", "awaiting_submission", "submitted", "archive",
]
QUEUES: tuple[str, ...] = (
    "being_drawn", "internal_review", "update_required",
    "completed", "awaiting_submission", "submitted", "archive",
)

_TEXT_FIELDS = ("level", "joinery_id", "zone", "room_no")


class _RegisterFields(BaseModel):
    """Register columns shared by create and patch. An omitted field is
    untouched on patch; text fields are stripped and '' reads as cleared."""
    type: DrawingType | None = None
    level: str | None = Field(default=None, max_length=64)
    joinery_id: str | None = Field(default=None, max_length=64)
    zone: str | None = Field(default=None, max_length=64)
    room_no: str | None = Field(default=None, max_length=64)
    assigned_to: int | None = None
    due_date: date | None = None

    @field_validator("level", "joinery_id", "zone", "room_no", mode="before")
    @classmethod
    def _strip(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class CreateDrawingIn(_RegisterFields):
    title: str = Field(min_length=1, max_length=200)
    room: str | None = None
    file_blob_id: int
    submit_immediately: bool = False  # if True, rev 1 lands in 'pending'


class PatchDrawingIn(_RegisterFields):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    room: str | None = None
    submitted_at: date | None = None

    @field_validator("title", "type")
    @classmethod
    def _not_null(cls, v, info):
        # title and type are NOT NULL columns: an explicit null is a 422, not
        # a raw IntegrityError. (An omitted field never reaches a validator.)
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


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
    drawing_no: str | None
    type: DrawingType
    level: str | None
    joinery_id: str | None
    zone: str | None
    room_no: str | None
    assigned_to: int | None
    assigned_to_name: str | None
    due_date: date | None
    submitted_at: date | None
    queue: str  # the one status queue this drawing sits in (never 'archive'/'all')
    comment_count: int = 0


class DrawingListOut(BaseModel):
    drawings: list[DrawingCardOut]
    total: int
    awaiting_review: int  # count of drawings whose latest revision is 'pending'
    distinct_rooms: int
    queues: dict[str, int] = {}  # per-queue counts for the whole project


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
    drawing_no: str | None
    type: DrawingType
    level: str | None
    joinery_id: str | None
    zone: str | None
    room_no: str | None
    assigned_to: int | None
    assigned_to_name: str | None
    due_date: date | None
    submitted_at: date | None
    revisions: list[RevisionOut]


class HistoryEventOut(BaseModel):
    event: str
    actor_name: str | None
    created_at: datetime
    payload: dict


class DrawingHistoryOut(BaseModel):
    events: list[HistoryEventOut]
