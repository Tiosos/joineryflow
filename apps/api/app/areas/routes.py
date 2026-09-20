"""Area + Room routes.

Gated `("tracking", action)`: Areas and Rooms describe *where an item is*, which
is Tracking's own data, and the item fields they replace are edited under the
same gate. Creation additionally takes `require_drafter()`, matching every other
item-shaping mutation (#2/#3's drafter-narrow rule).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import AreaListOut, CreateAreaIn, CreateRoomIn

router = APIRouter(tags=["areas"])


@router.get("/projects/{pid}/areas", response_model=AreaListOut)
def list_areas_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    """The project's areas with their rooms nested (Q552)."""
    result = q.list_areas(db, project_id=pid, workspace_id=user.workspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return result


@router.post(
    "/projects/{pid}/areas",
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def create_area_route(
    pid: int,
    payload: CreateAreaIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    outcome, area = q.create_area(
        db, project_id=pid, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if outcome == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="project not found")
    if outcome == "DUPLICATE":
        # The name is taken in this project. Hand back the id so the caller can
        # select the existing area instead of failing the user's keystroke.
        raise HTTPException(
            status_code=409,
            detail={"code": "AREA_EXISTS", "area_id": area["area_id"]},
        )
    db.commit()
    return area


@router.post(
    "/areas/{aid}/rooms",
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def create_room_route(
    aid: int,
    payload: CreateRoomIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    outcome, room = q.create_room(
        db, area_id=aid, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if outcome == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="area not found")
    if outcome == "DUPLICATE":
        raise HTTPException(
            status_code=409,
            detail={"code": "ROOM_EXISTS", "room_id": room["room_id"]},
        )
    db.commit()
    return room
