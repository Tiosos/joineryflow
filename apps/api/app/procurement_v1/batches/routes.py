"""HTTP routes for /batches (Procurement Workbench v1).

CRUD + soft-cancel for procurement batches.

RBAC: all endpoints require `(orderbook, read|write)`. Workspace isolation
flows through `get_project` (which scopes via `pm_id -> app_user.workspace_id`)
and the workspace-filter join in queries.py. Mutating endpoints write
workspace-level audit rows.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.audit import write_audit
from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from ...projects.queries import get_project
from .queries import (
    batch_has_allocations,
    create_batch,
    get_batch,
    list_batches,
    patch_batch,
    soft_cancel_batch,
)
from .schemas import BatchListOut, BatchOut, CreateBatchIn, PatchBatchIn

router = APIRouter(prefix="", tags=["procurement-v1"])


@router.get("/batches", response_model=BatchListOut)
def get_batches(
    project_id: int | None = None,
    supplier: str | None = None,
    status: str | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    rows = list_batches(
        db,
        workspace_id=user.workspace_id,
        project_id=project_id,
        supplier=supplier,
        status=status,
    )
    return {"batches": rows}


@router.post("/batches", response_model=BatchOut, status_code=201)
def post_batch(
    payload: CreateBatchIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    proj = get_project(
        db,
        project_id=payload.project_id,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if proj is None:
        raise HTTPException(404, "Project not found")
    bid = create_batch(
        db,
        payload=payload.model_dump(exclude={"project_id"}),
        project_id=payload.project_id,
    )
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="batch.create",
        target=f"batch:{bid}",
    )
    db.commit()
    out = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(500, "Created batch not visible")
    return out


@router.get("/batches/{bid}", response_model=BatchOut)
def get_one(
    bid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    row = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(404, "Batch not found")
    return row


@router.patch("/batches/{bid}", response_model=BatchOut)
def patch_one(
    bid: int,
    payload: PatchBatchIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if get_batch(db, batch_id=bid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Batch not found")
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if fields:
        patch_batch(db, batch_id=bid, fields=fields)
        write_audit(
            db,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event="batch.update",
            target=f"batch:{bid}",
        )
        db.commit()
    return get_batch(db, batch_id=bid, workspace_id=user.workspace_id)


@router.delete("/batches/{bid}", status_code=204)
def cancel_one(
    bid: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    existing = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if existing is None:
        raise HTTPException(404, "Batch not found")
    if existing["cancelled_at"] is not None:
        raise HTTPException(409, "Batch already cancelled")
    if batch_has_allocations(db, batch_id=bid):
        raise HTTPException(409, "Remove allocations before cancelling this batch")
    soft_cancel_batch(db, batch_id=bid)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="batch.cancel",
        target=f"batch:{bid}",
    )
    db.commit()
    return None
