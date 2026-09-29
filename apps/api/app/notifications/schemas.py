"""Schemas for the in-app notification inbox (migration 0042, Q521)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NotificationOut(BaseModel):
    notification_id: int
    kind: Literal["mention", "reply"]
    created_at: datetime
    read_at: datetime | None
    actor_id: int | None
    actor_name: str | None = None
    comment_id: int
    excerpt: str
    object_type: Literal["project", "area", "room", "item"]
    object_id: int
    object_label: str | None = None
    # None for Area / Room: neither has a page of its own yet.
    url: str | None = None


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int


class ReadAllOut(BaseModel):
    marked: int
