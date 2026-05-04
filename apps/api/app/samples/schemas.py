"""Pydantic schemas for the samples (iSample) module."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SampleStatus = Literal["pending", "approved", "rejected"]
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CreateSampleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    room: str | None = Field(default=None, max_length=64)
    hex_swatch: str
    supplier: str | None = Field(default=None, max_length=128)
    photo_file_blob_id: int | None = None

    @field_validator("hex_swatch")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        if not HEX_RE.match(v):
            raise ValueError("hex_swatch must match ^#[0-9A-Fa-f]{6}$")
        return v


class PatchSampleIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    room: str | None = Field(default=None, max_length=64)
    hex_swatch: str | None = None
    supplier: str | None = Field(default=None, max_length=128)

    @field_validator("hex_swatch")
    @classmethod
    def validate_hex(cls, v: str | None) -> str | None:
        if v is not None and not HEX_RE.match(v):
            raise ValueError("hex_swatch must match ^#[0-9A-Fa-f]{6}$")
        return v


class RejectIn(BaseModel):
    review_note: str = Field(min_length=1, max_length=2000)


class ApproveIn(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


class BindPhotoIn(BaseModel):
    file_blob_id: int


class SampleOut(BaseModel):
    sample_id: int
    project_id: int
    project_code: str
    title: str
    room: str | None
    hex_swatch: str
    supplier: str | None
    status: SampleStatus
    review_note: str | None
    reviewed_by: int | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    photo_file_blob_id: int | None
    photo_filename: str | None
    archived_at: datetime | None
    archived_by: int | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class SampleListOut(BaseModel):
    samples: list[SampleOut]
    total: int
    counts: dict[str, int]   # {"pending": 6, "approved": 18, "rejected": 2}


class LedgerEntry(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    event: str
    sample_id: int
    payload: dict
    created_at: datetime


class LedgerOut(BaseModel):
    entries: list[LedgerEntry]
    total: int
    limit: int
    offset: int
