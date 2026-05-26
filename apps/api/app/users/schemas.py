from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    auth_role: str
    jtbd_role: str | None = None
    is_active: bool
    is_shop_worker: bool = False


class UserPatch(BaseModel):
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
