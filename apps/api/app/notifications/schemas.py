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
    object_type: Literal["project", "area", "room", "item", "module", "revision", "task"]
    object_id: int
    object_label: str | None = None
    # Area / Room threads open on the project page's Areas & Rooms card.
    url: str | None = None


class AttentionItemOut(BaseModel):
    """One thing waiting for the caller (Q613). Derived on read: no row, no read state."""
    kind: Literal["lock_request", "variation", "order", "task"]
    key: str                      # "<kind>:<id>", unique within the list
    title: str
    detail: str | None = None
    url: str
    created_at: datetime | None = None


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
    # What is waiting for the caller, every list they qualify for in `KINDS` order, at most 20 of
    # each newest first, with each kind's true total and the grand total. First, unfiltered page
    # only; empty otherwise. See notifications/attention.py.
    attention: list[AttentionItemOut] = []
    attention_totals: dict[str, int] = {}
    attention_count: int = 0


class ReadAllOut(BaseModel):
    marked: int
