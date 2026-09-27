"""Pydantic schemas for the RBAC-engine admin API (Q466-473)."""
from pydantic import BaseModel, Field


class GrantIn(BaseModel):
    module: str
    action: str


class GroupOut(BaseModel):
    group_id: int
    name: str
    is_system: bool
    grants: list[GrantIn]


class CreateGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class SetGrantsIn(BaseModel):
    grants: list[GrantIn]


class MembershipOut(BaseModel):
    membership_id: int
    user_id: int
    user_full_name: str
    group_id: int
    group_name: str
    project_id: int | None = None
    project_code: str | None = None


class CreateMembershipIn(BaseModel):
    user_id: int
    # None means workspace-wide (Q466's default); a real id scopes the
    # membership's grants to that one project.
    project_id: int | None = None
