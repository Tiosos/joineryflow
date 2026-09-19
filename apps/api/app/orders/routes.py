"""Order routes — the commercial layer on the revived procurement namespace.

Gated `("orderbook", action)` — **Q432**, which confirmed the existing Orderbook
write holders are the right authority, so no matrix row changes.

These live at top-level paths (`/orders`, `/projects/{pid}/orders`,
`/items/{iid}/orders`) and are **separate from the untouched legacy
`/procurement/*` namespace**, which still serves its own 32 endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CategoryOut,
    CreateOrderIn,
    CreateOrderLineIn,
    OrderDetailOut,
    OrderListOut,
    PatchOrderIn,
)

router = APIRouter(tags=["orders"])


@router.get("/order-categories", response_model=list[CategoryOut])
def list_categories_route(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    """The category lookup `0031` introduced in place of the frozen CHECK."""
    return q.list_categories(db)


@router.get("/projects/{pid}/orders", response_model=OrderListOut)
def list_project_orders_route(
    pid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_orders_for_project(db, project_id=pid, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(404, "project not found")
    return {"orders": rows}


@router.get("/items/{iid}/orders", response_model=OrderListOut)
def list_item_orders_route(
    iid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    """Backs Tracking's O/BOOK subtab for one row (Q425)."""
    rows = q.list_orders_for_item(db, item_id=iid, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(404, "item not found")
    return {"orders": rows}


@router.get("/orders/{po_id}", response_model=OrderDetailOut)
def get_order_route(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    order = q.get_order(db, po_id=po_id, workspace_id=user.workspace_id)
    if order is None:
        raise HTTPException(404, "order not found")
    return order


@router.post("/orders", response_model=OrderDetailOut, status_code=201)
def create_order_route(
    payload: CreateOrderIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    """Create Order (Q425). Passing `item_id` prefills PROJECT / LOCATION /
    CUTLIST NO. from that row — for a related part, from its parent (Q428) —
    and leaves the cutlist blank when there is not one yet (Q429)."""
    code, order = q.create_order(
        db, workspace_id=user.workspace_id, payload=payload, actor_id=user.id
    )
    if code == "VENDOR_NOT_FOUND":
        raise HTTPException(404, {"code": "VENDOR_NOT_FOUND",
                                  "vendor_id": payload.vendor_id})
    if code == "ITEM_NOT_FOUND":
        raise HTTPException(404, {"code": "ITEM_NOT_FOUND",
                                  "item_id": payload.item_id})
    db.commit()
    return order


@router.patch("/orders/{po_id}", response_model=OrderDetailOut)
def patch_order_route(
    po_id: int,
    payload: PatchOrderIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    order = q.patch_order(
        db, po_id=po_id, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if order is None:
        raise HTTPException(404, "order not found")
    db.commit()
    return order


@router.delete("/orders/{po_id}", status_code=204)
def cancel_order_route(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    """Soft-cancel, matching #4's batch semantics — a second cancel is a 409."""
    code = q.cancel_order(
        db, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "order not found")
    if code == "ALREADY_CANCELLED":
        raise HTTPException(409, {"code": "ALREADY_CANCELLED"})
    db.commit()
    return None


@router.post("/orders/{po_id}/lines", response_model=OrderDetailOut, status_code=201)
def add_line_route(
    po_id: int,
    payload: CreateOrderLineIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    order = q.add_line(
        db, po_id=po_id, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if order is None:
        raise HTTPException(404, "order not found")
    db.commit()
    return order
