"""Shop Drawings routes — CRUD + workflow.

Permissions:
  - Create / patch / upload revision / submit / withdraw: shop_dwgs:write
    (drafter / manager / admin per the matrix).
  - Approve / reject / archive: shop_dwgs:approve (manager / admin / drafter).
    Plus the not-uploader rule on approve/reject is enforced in-handler.
  - Read: shop_dwgs:read (all roles except IT-management-only).

The "one in flight per drawing" invariant is enforced by the partial unique
index uniq_drawing_inflight; the handler turns the IntegrityError into a 409.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CreateDrawingIn,
    CreateRevisionIn,
    DrawingDetailOut,
    DrawingListOut,
    PatchDrawingIn,
    RejectIn,
)

router = APIRouter(tags=["shop_drawings"])


@router.get("/projects/{pid}/shop-drawings", response_model=DrawingListOut)
def list_drawings(
    pid: int,
    subtab: str = Query("current", pattern="^(current|in_review|archive)$"),
    room: str | None = None,
    reviewer_id: int | None = None,
    q_search: str | None = Query(None, alias="q"),
    user: AuthUser = Depends(require_permission("shop_dwgs", "read")),
    db: Session = Depends(get_db),
):
    if not q._ensure_project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id):
        raise HTTPException(status_code=404, detail="project not found")
    rows = q.list_drawings_by_subtab(
        db, project_id=pid, subtab=subtab, room=room,
        reviewer_id=reviewer_id, q=q_search,
    )
    summary = q.list_summary(db, project_id=pid)
    return DrawingListOut(
        drawings=rows,
        total=summary.get("total", 0),
        awaiting_review=summary.get("awaiting_review", 0),
        distinct_rooms=summary.get("distinct_rooms", 0),
    )


@router.get("/shop-drawings/{did}", response_model=DrawingDetailOut)
def get_drawing(
    did: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "read")),
    db: Session = Depends(get_db),
):
    row = q.get_drawing_with_revisions(db, drawing_id=did, workspace_id=user.workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing not found")
    return row


@router.post("/projects/{pid}/shop-drawings", response_model=DrawingDetailOut, status_code=201)
def create_drawing_route(
    pid: int,
    body: CreateDrawingIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    try:
        new_id = q.create_drawing(
            db, workspace_id=user.workspace_id, project_id=pid,
            payload=body, actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return q.get_drawing_with_revisions(db, drawing_id=new_id, workspace_id=user.workspace_id)


@router.patch("/shop-drawings/{did}", response_model=DrawingDetailOut)
def patch_drawing_route(
    did: int,
    body: PatchDrawingIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    try:
        row = q.patch_drawing(
            db, drawing_id=did, workspace_id=user.workspace_id,
            payload=body, actor_id=user.id, actor_role=user.auth_role,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="drawing not found")
    db.commit()
    return row


@router.post("/shop-drawings/{did}/archive", status_code=204)
def archive_drawing_route(
    did: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "approve")),
    db: Session = Depends(get_db),
):
    try:
        ok = q.archive_drawing(db, drawing_id=did, workspace_id=user.workspace_id, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="drawing not found")
    db.commit()
    return Response(status_code=204)


@router.post("/shop-drawings/{did}/revisions", response_model=DrawingDetailOut, status_code=201)
def add_revision_route(
    did: int,
    body: CreateRevisionIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    try:
        q.add_revision(
            db, drawing_id=did, workspace_id=user.workspace_id,
            file_blob_id=body.file_blob_id, actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc))
    except IntegrityError as exc:
        db.rollback()
        if "uniq_drawing_inflight" in str(exc.orig):
            raise HTTPException(
                status_code=409,
                detail="this drawing already has an in-flight revision; withdraw or wait for review",
            )
        raise
    db.commit()
    return q.get_drawing_with_revisions(db, drawing_id=did, workspace_id=user.workspace_id)


def _transition(
    did: int, rid: int, action: str, db: Session, user: AuthUser,
    review_note: str | None = None,
):
    """Shared transition handler. Approve/reject have the not-uploader rule."""
    rev = db.execute(
        text("SELECT uploaded_by FROM shop_drawing_revision WHERE revision_id = :r AND drawing_id = :d"),
        {"r": rid, "d": did},
    ).first()
    if not rev:
        raise HTTPException(status_code=404, detail="revision not found")
    if action in ("approve", "reject") and rev[0] == user.id:
        raise HTTPException(status_code=403, detail="reviewer cannot be the uploader")
    if action in ("submit", "withdraw") and rev[0] != user.id:
        raise HTTPException(status_code=403, detail="only the uploader can submit/withdraw a revision")

    try:
        result = q.transition_revision(
            db, drawing_id=did, revision_id=rid,
            workspace_id=user.workspace_id, actor_id=user.id,
            action=action, review_note=review_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="revision not found")
    db.commit()
    return result


@router.post("/shop-drawings/{did}/revisions/{rid}/submit")
def submit_revision_route(
    did: int, rid: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "submit", db, user)


@router.post("/shop-drawings/{did}/revisions/{rid}/withdraw")
def withdraw_revision_route(
    did: int, rid: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "withdraw", db, user)


@router.post("/shop-drawings/{did}/revisions/{rid}/approve")
def approve_revision_route(
    did: int, rid: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "approve")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "approve", db, user)


@router.post("/shop-drawings/{did}/revisions/{rid}/reject")
def reject_revision_route(
    did: int, rid: int,
    body: RejectIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "approve")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "reject", db, user, review_note=body.review_note)
