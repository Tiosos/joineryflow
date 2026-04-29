"""HTTP routes for /batches/{bid}/allocations and /allocations/{aid}
(Procurement Workbench v1).

CRUD over `batch_allocations`, with two business rules enforced at the route
layer:
  1. Cross-project guard: an item_hardware_line must belong to the same
     project as the batch.
  2. Capacity guard: the sum of qty_allocated against a batch may not exceed
     the batch's effective capacity (qty_received if positive, else
     qty_ordered).

RBAC: all endpoints require `(orderbook, read|write)`. Workspace isolation
flows through `get_batch` (workspace-scoped via projects.pm_id -> app_user)
and `get_allocation` (same join). Mutating endpoints write workspace-level
audit rows.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.audit import write_audit
from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from ..batches.queries import get_batch
from .queries import (
    batch_capacity,
    create_allocation,
    delete_allocation,
    get_allocation,
    line_belongs_to_batch_project,
    list_allocations_for_batch,
    patch_allocation,
)
from .schemas import (
    AllocationListOut,
    AllocationOut,
    CreateAllocationIn,
    PatchAllocationIn,
)

router = APIRouter(prefix="", tags=["procurement-v1"])


def _capacity(qty_received, qty_ordered) -> float:
    """Effective capacity: prefer qty_received when > 0, else qty_ordered."""
    qr = float(qty_received) if qty_received is not None else 0.0
    qo = float(qty_ordered) if qty_ordered is not None else 0.0
    return qr if qr > 0 else qo


@router.get("/batches/{bid}/allocations", response_model=AllocationListOut)
def list_for_batch(
    bid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    batch = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    rows = list_allocations_for_batch(db, batch_id=bid)
    qty_alloc_total = sum((float(r["qty_allocated"]) for r in rows), 0.0)
    qty_received = (
        float(batch["qty_received"]) if batch["qty_received"] is not None else 0.0
    )
    return {
        "allocations":         rows,
        "qty_received":        qty_received,
        "qty_allocated_total": qty_alloc_total,
        "qty_remaining":       qty_received - qty_alloc_total,
    }


@router.post(
    "/batches/{bid}/allocations",
    response_model=AllocationOut,
    status_code=201,
)
def create_for_batch(
    bid: int,
    payload: CreateAllocationIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    batch = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    if not line_belongs_to_batch_project(
        db, batch_id=bid, line_id=payload.item_hardware_line_id
    ):
        raise HTTPException(400, "Line does not belong to this batch's project")

    cur_alloc = (
        float(batch["qty_allocated"]) if batch["qty_allocated"] is not None else 0.0
    )
    new_total = cur_alloc + float(payload.qty_allocated)
    cap = _capacity(batch["qty_received"], batch["qty_ordered"])
    if new_total > cap:
        raise HTTPException(
            409, f"Allocation would exceed capacity ({new_total} > {cap})"
        )

    aid = create_allocation(
        db,
        batch_id=bid,
        line_id=payload.item_hardware_line_id,
        qty=float(payload.qty_allocated),
    )
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="allocation.create",
        target=f"allocation:{aid}",
    )
    db.commit()
    out = get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(500, "Created allocation not visible")
    return out


@router.patch("/allocations/{aid}", response_model=AllocationOut)
def patch_one(
    aid: int,
    payload: PatchAllocationIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    existing = get_allocation(
        db, allocation_id=aid, workspace_id=user.workspace_id
    )
    if existing is None:
        raise HTTPException(404, "Allocation not found")
    bid = existing["batch_id"]
    qty_received, qty_alloc_total, qty_ordered = batch_capacity(db, batch_id=bid)
    new_total = (
        float(qty_alloc_total)
        - float(existing["qty_allocated"])
        + float(payload.qty_allocated)
    )
    cap = _capacity(qty_received, qty_ordered)
    if new_total > cap:
        raise HTTPException(
            409, f"Allocation would exceed capacity ({new_total} > {cap})"
        )
    patch_allocation(db, allocation_id=aid, qty=float(payload.qty_allocated))
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="allocation.update",
        target=f"allocation:{aid}",
    )
    db.commit()
    return get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id)


@router.delete("/allocations/{aid}", status_code=204)
def delete_one(
    aid: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Allocation not found")
    delete_allocation(db, allocation_id=aid)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="allocation.delete",
        target=f"allocation:{aid}",
    )
    db.commit()
    return None
