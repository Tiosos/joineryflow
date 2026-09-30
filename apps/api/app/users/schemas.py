from typing import Literal

from pydantic import BaseModel, Field
from ..schema_guards import no_null


class UserOut(BaseModel):
    id: int
    # Plain str, not EmailStr — same reasoning as auth/schemas.py: format is
    # enforced upstream, and this is an *output* echo of a stored value, not
    # input validation. EmailStr response-validates on read, which 500s for
    # any real `*.hartwood.test` seeded user once email-validator enforces
    # RFC 2606 reserved-TLD rejection (`.test` is one) — a real bug, not a
    # theoretical one: `GET /users` and `PATCH /users/{uid}` both use this
    # model and both broke against the dev seed.
    email: str
    full_name: str
    auth_role: str
    jtbd_role: str | None = None
    is_active: bool
    is_shop_worker: bool = False


class UserPatch(BaseModel):
    # An explicit null on a NOT NULL column is a raw 500 (schema_guards.py).
    reject_null = no_null("full_name", "is_active")
    full_name: str | None = None
    auth_role: str | None = None
    jtbd_role: str | None = None
    is_active: bool | None = None


class UserShopWorkerPatch(BaseModel):
    is_shop_worker: bool


# ── Team status (legacy/home.html parity) ─────────────────────────────────────

WorkStatus = Literal["IN", "ON_SITE", "SHOP", "WFH", "OFF"]


class TeamMemberOut(BaseModel):
    id: int
    full_name: str
    auth_role: str
    jtbd_role: str | None = None
    work_status: WorkStatus | None = None
    location_label: str | None = None
    is_self: bool = False


class TeamOut(BaseModel):
    members: list[TeamMemberOut]


class MyStatusPatch(BaseModel):
    work_status: WorkStatus | None = None
    location_label: str | None = Field(default=None, max_length=128)
