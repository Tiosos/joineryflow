"""Schemas for the in-app notification inbox (migration 0042, Q521)."""
from datetime import date, datetime
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


class LockRequestWaitingOut(BaseModel):
    request_id: int
    item_id: int
    item_number: int | None = None
    project_code: str | None = None
    requested_by_name: str | None = None
    # The item fields the held save would change (the keys of `requested_changes`).
    fields: list[str]
    created_at: datetime
    url: str


class TaskOpenOut(BaseModel):
    task_id: int
    title: str
    status: str
    due_date: date | None
    target_label: str | None
    url: str


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
    # The caller's own tasks still to do (open + in progress), soonest due first, at most 20, and how
    # many in all. Derived on read like `orders_waiting` (no table, no read state): a task leaves when
    # it is done or cancelled. First, unfiltered page only; empty otherwise.
    tasks_open: list[TaskOpenOut] = []
    tasks_open_count: int = 0


class NotificationListWaitingOut(NotificationListOut):
    """A purchase officer's first page: also the orders still Pending, newest first (at most 20)
    and how many in all. Derived on read, so there is nothing to mark read: an order leaves when
    it is decided. Everyone else, and paged or unread-only calls, get `NotificationListOut`."""
    orders_waiting: list[OrderWaitingOut]
    orders_waiting_count: int


class NotificationListLockRequestsOut(NotificationListOut):
    """The first page of someone who may decide lock requests (the lock owner, a manager, an
    admin): also the held saves still pending on items they may decide, newest first (at most
    20) and how many in all. Derived on read like the purchase officer's orders: a request leaves
    when it is approved or rejected, so there is nothing to mark read."""
    lock_requests_waiting: list[LockRequestWaitingOut]
    lock_requests_waiting_count: int


class ReadAllOut(BaseModel):
    marked: int
