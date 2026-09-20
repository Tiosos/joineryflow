"""Area + Room schemas.

`0026` made both real entities (Plan V1 **Q454/Q455**), **project-scoped**
(Q457) and with Room **nested under Area** (Q552) — the composite FK
`items (area_id, room_id) → room (area_id, room_id)` is what stops an item's
room drifting out of its area, so the two are always set together.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class RoomOut(BaseModel):
    room_id: int
    area_id: int
    rm_no: str
    rm_desc: str | None
    sort_order: int
    item_count: int


class AreaOut(BaseModel):
    area_id: int
    project_id: int
    name: str
    sort_order: int
    created_at: datetime
    item_count: int
    rooms: list[RoomOut]


class AreaListOut(BaseModel):
    project_id: int
    areas: list[AreaOut]


class CreateAreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    sort_order: int = 0


class CreateRoomIn(BaseModel):
    rm_no: str = Field(min_length=1, max_length=16)
    rm_desc: str | None = Field(default=None, max_length=128)
    sort_order: int = 0
