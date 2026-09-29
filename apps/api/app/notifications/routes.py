"""The caller's own notification inbox (Q521: in-app only).

`current_user` only, no RBAC matrix row — like `/search`, it shows a person
their own addressed items, never anyone else's. But an excerpt is comment text,
so it is only shown while the recipient can still read where it came from:
each notification is shown only while the recipient can read every module its
thread links into (`comments.queries.READ_MODULES`): without `tracking:read` the
project / area / room / item threads are left out, without `list:read` the item
and module threads (their link opens the item editor), without `shop_dwgs:read`
the revision threads. Their notifications are hidden, not deleted — they
reappear if access is restored.

Marking read is audited (`notification.read`, `notification.read_all`), once per
real change, so CLAUDE.md's "every authenticated mutation is audited" holds.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import current_user
from ..auth.rbac_engine import has_permission_db
from ..auth.sessions import AuthUser
from ..db import get_db
from ..comments.queries import READ_MODULES
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
    readable = {m: has_permission_db(db, user, m, "read")
                for m in {m for ms in READ_MODULES.values() for m in ms}}
    types = [t for t, ms in READ_MODULES.items() if all(readable[m] for m in ms)]
    return q.list_notifications(
        db, user_id=user.id, workspace_id=user.workspace_id,
        unread_only=unread_only, limit=limit, offset=offset, types=types,
    )


@router.post("/notifications/read-all", response_model=ReadAllOut)
def read_all_route(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    n = q.mark_all_read(db, user_id=user.id, workspace_id=user.workspace_id)
    if n:
        write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
                    event="notification.read_all", payload={"marked": n})
    db.commit()
    return {"marked": n}


@router.post("/notifications/{nid}/read", status_code=204)
def read_one_route(
    nid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = q.mark_read(db, notification_id=nid, user_id=user.id,
                         workspace_id=user.workspace_id)
    if result == "NOT_FOUND":
        raise HTTPException(404, "notification not found")
    if result == "OK":
        write_audit(db, workspace_id=user.workspace_id, actor_id=user.id,
                    event="notification.read", target=f"notification:{nid}")
    db.commit()
    return None
