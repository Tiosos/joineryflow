from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..projects.queries import get_project
from .queries import (
    claim_or_release_lock,
    create_item,
    decide_lock_request,
    delete_item,
    get_item_availability,
    get_item_detail,
    list_items_for_project,
    list_lock_requests,
    patch_item,
    patch_item_status,
    patch_lifecycle,
)
from .schemas import (
    AvailabilityOut,
    CreateItemIn,
    ItemOut,
    LockRequestDecisionIn,
    LockRequestOut,
    LockTransferIn,
    PatchItemIn,
    PatchItemStatusIn,
    PatchLifecycleIn,
    TrackingGridOut,
)

router = APIRouter(prefix="", tags=["items"])


@router.get("/projects/{pid}/items", response_model=TrackingGridOut)
def get_project_items(
    pid: int,
    status: str | None = None,
    stage: str | None = None,
    q: str | None = None,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    proj = get_project(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    items = list_items_for_project(
        db,
        workspace_id=user.workspace_id,
        project_id=pid,
        status=status,
        stage_key=stage,
        q=q,
    )
    return {"project_id": pid, "items": items}


@router.get("/items/{id}/availability", response_model=AvailabilityOut)
def get_availability(
    id: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    detail = get_item_availability(
        db, item_id=id, workspace_id=user.workspace_id
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="item not found")
    return detail


@router.get("/items/{id}", response_model=ItemOut)
def get_item(
    id: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    detail = get_item_detail(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="item not found")
    return detail


# ── Item write endpoints (T15) ─────────────────────────────────────────────────


@router.post(
    "/projects/{pid}/items",
    response_model=ItemOut,
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def post_item(
    pid: int,
    payload: CreateItemIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Create a new item inside a project.  Drafter-only gate."""
    iid = create_item(
        db,
        workspace_id=user.workspace_id,
        project_id=pid,
        payload=payload,
        actor_id=user.id,
    )
    if iid is None:
        raise HTTPException(status_code=404, detail="project not found")
    db.commit()
    detail = get_item_detail(
        db, item_id=iid, workspace_id=user.workspace_id, current_user_id=user.id
    )
    return detail


@router.patch(
    "/items/{id}",
    response_model=ItemOut,
    dependencies=[Depends(require_drafter())],
)
def patch_item_route(
    id: int,
    payload: PatchItemIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Partially update an item.  Drafter-only gate.  Controlled Lock applies.

    A non-owner's save on a locked item is **not** applied: it is held as a
    pending `item_lock_request` and answered with 409 (Q509).
    """
    result = patch_item(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    if result["outcome"] == "lock_request":
        req = result["request"]
        db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "LOCK_REQUEST_CREATED",
                "request_id": req["request_id"],
                "owner_id": req["cutlist_owner_id"],
                "fields": sorted(req["requested_changes"]),
            },
        )
    db.commit()
    detail = get_item_detail(
        db, item_id=id, workspace_id=user.workspace_id, current_user_id=user.id
    )
    return detail


@router.delete(
    "/items/{id}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def delete_item_route(
    id: int,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Delete an item.  Returns 409 if hardware lines have batch allocations."""
    result = delete_item(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        actor_id=user.id,
    )
    if result == "IN_USE":
        raise HTTPException(
            status_code=409,
            detail="item has allocated hardware; release allocations first",
        )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()


@router.post(
    "/items/{id}/lock",
    response_model=ItemOut,
    dependencies=[Depends(require_drafter())],
)
def lock_item(
    id: int,
    payload: LockTransferIn | None = None,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Claim lock (no body) or transfer lock to another user (body with owner_id)."""
    action = "transfer" if payload is not None else "claim"
    result = claim_or_release_lock(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        actor=user,
        action=action,
        owner_id=payload.owner_id if payload else None,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="item not found")
    if result == "FORBIDDEN":
        raise HTTPException(
            status_code=403,
            detail="only owner, manager, or admin can transfer lock",
        )
    db.commit()
    return get_item_detail(
        db, item_id=id, workspace_id=user.workspace_id, current_user_id=user.id
    )


# ── T16 lifecycle / status endpoints ──────────────────────────────────────────


@router.patch("/items/{id}/status", response_model=ItemOut)
def patch_status_route(
    id: int,
    payload: PatchItemStatusIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Update items.status.  Allowed for any role with tracking:write
    (admin, manager, editor, drafter — NOT purchase_officer or viewer).
    """
    ok = patch_item_status(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        status=payload.status,
        note=payload.note,
        actor_id=user.id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()
    return get_item_detail(
        db, item_id=id, workspace_id=user.workspace_id, current_user_id=user.id
    )


@router.patch("/items/{id}/lifecycle/{stage_key}", response_model=ItemOut)
def patch_lifecycle_route(
    id: int,
    stage_key: str,
    payload: PatchLifecycleIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """UPSERT due_date / done_date for a lifecycle stage on an item.
    Allowed for any role with tracking:write.
    Returns 400 for unknown stage_key, 404 if item not found.
    """
    result = patch_lifecycle(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        stage_key=stage_key,
        payload=payload,
        actor_id=user.id,
    )
    if result == "INVALID_STAGE_KEY":
        raise HTTPException(status_code=400, detail="unknown stage_key")
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()
    return get_item_detail(
        db, item_id=id, workspace_id=user.workspace_id, current_user_id=user.id
    )


@router.delete(
    "/items/{id}/lock",
    response_model=ItemOut,
    dependencies=[Depends(require_drafter())],
)
def release_lock(
    id: int,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Release a lock on an item.  cutlist_owner_id is NOT cleared (sticky)."""
    result = claim_or_release_lock(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        actor=user,
        action="release",
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()
    return get_item_detail(
        db, item_id=id, workspace_id=user.workspace_id, current_user_id=user.id
    )


# ── Controlled Lock requests (B7 / Q509) ──────────────────────────────────────


@router.get("/items/{id}/lock-requests", response_model=list[LockRequestOut])
def get_lock_requests(
    id: int,
    status: str | None = None,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    """Saves held against this item's lock, newest first.  `?status=pending` filters."""
    rows = list_lock_requests(
        db, item_id=id, workspace_id=user.workspace_id, status=status
    )
    if rows is None:
        raise HTTPException(status_code=404, detail="item not found")
    return rows


def _decide(
    db: Session, *, request_id: int, user: AuthUser, decision: str, note: str | None
):
    result = decide_lock_request(
        db,
        request_id=request_id,
        workspace_id=user.workspace_id,
        actor=user,
        decision=decision,
        note=note,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="lock request not found")
    if result == "FORBIDDEN":
        raise HTTPException(
            status_code=403,
            detail="only the lock owner, a manager, or an admin can decide",
        )
    if result == "ALREADY_DECIDED":
        raise HTTPException(
            status_code=409, detail={"code": "ALREADY_DECIDED"}
        )
    db.commit()
    return result


@router.post(
    "/lock-requests/{rid}/approve",
    response_model=LockRequestOut,
    dependencies=[Depends(require_drafter())],
)
def approve_lock_request(
    rid: int,
    payload: LockRequestDecisionIn | None = None,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Apply the held save.  The edit log credits the requester, the audit the approver."""
    return _decide(
        db,
        request_id=rid,
        user=user,
        decision="approved",
        note=payload.note if payload else None,
    )


@router.post(
    "/lock-requests/{rid}/reject",
    response_model=LockRequestOut,
    dependencies=[Depends(require_drafter())],
)
def reject_lock_request(
    rid: int,
    payload: LockRequestDecisionIn | None = None,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Discard the held save; the item is untouched."""
    return _decide(
        db,
        request_id=rid,
        user=user,
        decision="rejected",
        note=payload.note if payload else None,
    )
