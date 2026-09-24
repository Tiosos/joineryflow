"""Schemas for item_query CRUD."""
from datetime import datetime

from pydantic import BaseModel, Field


class CreateQueryIn(BaseModel):
    question: str = Field(min_length=1)


class AnswerQueryIn(BaseModel):
    answer: str = Field(min_length=1)


class ItemQueryOut(BaseModel):
    query_id: int
    item_id: int
    asked_by: int | None
    asked_by_name: str | None = None
    asked_at: datetime
    question: str
    answered_by: int | None
    answered_by_name: str | None = None
    answered_at: datetime | None
    answer: str | None
