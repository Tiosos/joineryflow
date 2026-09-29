"""The caller's own notification inbox (Q521: in-app only).

`current_user` only, no RBAC matrix row — like `/search`, it shows a person
their own addressed items, never anyone else's. Mark-read is personal state
(like project favourites) and writes no audit row.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.rbac import current_user
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import NotificationListOut, ReadAllOut

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationListOut)
def list_notifications_route(
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000),
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    return q.list_notifications(
        db, user_id=user.id, workspace_id=user.workspace_id,
        unread_only=unread_only, limit=limit, offset=offset,
    )


@router.post("/notifications/read-all", response_model=ReadAllOut)
def read_all_route(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    n = q.mark_all_read(db, user_id=user.id, workspace_id=user.workspace_id)
    db.commit()
    return {"marked": n}


@router.post("/notifications/{nid}/read", status_code=204)
def read_one_route(
    nid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not q.mark_read(db, notification_id=nid, user_id=user.id,
                       workspace_id=user.workspace_id):
        raise HTTPException(404, "notification not found")
    db.commit()
    return None
