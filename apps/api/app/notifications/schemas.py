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
    object_type: Literal["project", "area", "room", "item", "module", "revision"]
    object_id: int
    object_label: str | None = None
    # Area / Room threads open on the project page's Areas & Rooms card.
    url: str | None = None


class OrderWaitingOut(BaseModel):
    po_id: int
    po_number: str
    description: str | None = None
    vendor_name: str | None = None
    requester_name: str | None = None
    created_at: datetime
    url: str


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int


class NotificationListWaitingOut(NotificationListOut):
    """A purchase officer's first page: also the orders still Pending, newest first (at most 20)
    and how many in all. Derived on read, so there is nothing to mark read: an order leaves when
    it is decided. Everyone else, and paged or unread-only calls, get `NotificationListOut`."""
    orders_waiting: list[OrderWaitingOut]
    orders_waiting_count: int


class ReadAllOut(BaseModel):
    marked: int
