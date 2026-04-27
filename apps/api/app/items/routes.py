from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..projects.queries import get_project
from .queries import (
    claim_or_release_lock,
    create_item,
    delete_item,
    get_item_availability,
    get_item_detail,
    list_items_for_project,
    patch_item,
)
from .schemas import (
    AvailabilityOut,
    CreateItemIn,
    ItemOut,
    LockTransferIn,
    PatchItemIn,
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
    """Partially update an item.  Drafter-only gate.  Soft-lock semantics apply."""
    result = patch_item(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
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
