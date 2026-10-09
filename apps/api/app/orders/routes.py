"""Order routes — the commercial layer on the revived procurement namespace.

Gated `("orderbook", action)` — **Q432**, which confirmed the existing Orderbook
write holders are the right authority, so no matrix row changes.

These live at top-level paths (`/orders`, `/projects/{pid}/orders`,
`/items/{iid}/orders`) and are **separate from the untouched legacy
`/procurement/*` namespace**, which still serves its own 32 endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.rbac_engine import effective_actions
from ..auth.sessions import AuthUser
from ..catalog.queries import MaterialNotFound
from ..db import get_db
from . import queries as q
from .schemas import (
    CategoryOut,
    CostCentreIn,
    CostCentreListOut,
    CostCentreOut,
    PatchCostCentreIn,
    CreateOrderIn,
    CreateOrderLineIn,
    OrderDetailOut,
    OrderListOut,
    PatchOrderIn,
    PatchOrderLineIn,
)

router = APIRouter(tags=["orders"])


def _locked(e: q.OrderLocked) -> HTTPException:
    return HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status})


@router.get("/order-categories", response_model=list[CategoryOut])
def list_categories_route(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    """The category lookup `0031` introduced in place of the frozen CHECK."""
    return q.list_categories(db)


@router.get("/orders", response_model=OrderListOut)
def list_workspace_orders_route(
    status: str | None = None,
    supplier: str | None = None,
    search: str | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    """Backs the Orderbook page's Orders tab — every order in the workspace.

    Declared BEFORE `/orders/{po_id}` below so the literal path wins, the same
    ordering caveat `catalog/routes.py` carries for `/catalog/cv-mappings`.
    """
    return {
        "orders": q.list_orders_for_workspace(
            db,
            workspace_id=user.workspace_id,
            status=status,
            supplier=supplier,
            q=search,
        )
    }


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
    if code == "PROJECT_NOT_FOUND":
        raise HTTPException(404, {"code": "PROJECT_NOT_FOUND",
                                  "project_id": payload.project_id})
    if code == "UNKNOWN_CATEGORY":
        raise HTTPException(422, {"code": "UNKNOWN_CATEGORY",
                                  "category": payload.category})
    db.commit()
    return order


@router.patch("/orders/{po_id}", response_model=OrderDetailOut)
def patch_order_route(
    po_id: int,
    payload: PatchOrderIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    # Setting Approved / Rejected (or moving an order out of one) is the `orderbook:approve` holders'
    # call: purchase officer, manager, admin. Everyone with write access edits the rest.
    code, order = q.patch_order(
        db, po_id=po_id, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
        can_decide="approve" in effective_actions(db, user, "orderbook", None),
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "order not found")
    if code == "DECISION_FORBIDDEN":
        raise HTTPException(403, {"code": "DECISION_FORBIDDEN", **order})
    if code in ("REJECTION_NOTE_REQUIRED", "REJECTION_NOTE_NOT_APPLICABLE"):
        raise HTTPException(409, {"code": code})
    if code == "COST_CENTER_NOT_FOUND":
        raise HTTPException(404, {"code": "COST_CENTER_NOT_FOUND", **order})
    if code == "COST_CENTER_LOCKED":
        raise HTTPException(409, {"code": "COST_CENTER_LOCKED", **order})
    if code == "ORDER_LOCKED":
        raise HTTPException(409, {"code": "ORDER_LOCKED", **order})
    if code == "VENDOR_NOT_FOUND":
        raise HTTPException(404, {"code": "VENDOR_NOT_FOUND", **order})
    if code == "UNKNOWN_CATEGORY":
        raise HTTPException(422, {"code": "UNKNOWN_CATEGORY", **order})
    if code == "FIELD_CONFLICT":
        # `current_value` can be a Decimal (quantity/unit_cost/total_amount)
        # or a date (required_date/date_ordered/due_date) — HTTPException's
        # detail bypasses the response_model's Pydantic JSON encoding and
        # goes straight through Starlette's plain `json.dumps`, which 500s
        # on either type. jsonable_encoder is FastAPI's own fix for this.
        raise HTTPException(
            409, jsonable_encoder({"code": "FIELD_CONFLICT", "conflicts": order})
        )
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
    try:
        order = q.add_line(
            db, po_id=po_id, workspace_id=user.workspace_id,
            payload=payload, actor_id=user.id,
        )
    except q.OrderLocked as e:
        raise _locked(e)
    except MaterialNotFound as e:
        raise HTTPException(404, e.detail)
    if order is None:
        raise HTTPException(404, "order not found")
    db.commit()
    return order


@router.patch("/orders/{po_id}/lines/{line_id}", response_model=OrderDetailOut)
def patch_line_route(
    po_id: int,
    line_id: int,
    payload: PatchOrderLineIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    try:
        order = q.patch_line(
            db, po_id=po_id, line_id=line_id, workspace_id=user.workspace_id,
            payload=payload, actor_id=user.id,
        )
    except q.OrderLocked as e:
        raise _locked(e)
    if order is None:
        raise HTTPException(404, "order or line not found")
    db.commit()
    return order


@router.delete("/orders/{po_id}/lines/{line_id}", response_model=OrderDetailOut)
def remove_line_route(
    po_id: int,
    line_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    try:
        order = q.remove_line(
            db, po_id=po_id, line_id=line_id, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except q.OrderLocked as e:
        raise _locked(e)
    if order is None:
        raise HTTPException(404, "order or line not found")
    db.commit()
    return order


# ── Cost centres (the budget an Approved order commits against; optional on an order, Q563) ──

@router.get("/cost-centers", response_model=CostCentreListOut)
def list_cost_centres_route(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"cost_centers": q.list_cost_centres(db, workspace_id=user.workspace_id)}


@router.post("/cost-centers", response_model=CostCentreOut, status_code=201)
def create_cost_centre_route(
    payload: CostCentreIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    """A purchase officer's (or an admin's) to add, like the approval limit."""
    if user.auth_role not in ("purchase_officer", "admin"):
        raise HTTPException(403, {"code": "COST_CENTRE_FORBIDDEN"})
    row = q.create_cost_centre(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        code=payload.code, name=payload.name, budget_amount=payload.budget_amount)
    if row is None:
        raise HTTPException(409, {"code": "COST_CENTRE_EXISTS"})
    db.commit()
    return row


@router.patch("/cost-centers/{cost_center_id}", response_model=CostCentreOut)
def patch_cost_centre_route(
    cost_center_id: int,
    payload: PatchCostCentreIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    """Rename or (de)activate: the same people who add one. Orders that already use it are left as
    they are; an inactive one just cannot be chosen on an order again."""
    if user.auth_role not in ("purchase_officer", "admin"):
        raise HTTPException(403, {"code": "COST_CENTRE_FORBIDDEN"})
    code, row = q.patch_cost_centre(
        db, cost_center_id=cost_center_id, workspace_id=user.workspace_id,
        actor_id=user.id, changes=payload.model_dump(exclude_unset=True))
    if code == "NOT_FOUND":
        raise HTTPException(404, "cost centre not found")
    if code == "EXISTS":
        raise HTTPException(409, {"code": "COST_CENTRE_EXISTS"})
    db.commit()
    return row

