"""The order pop-up's tabs (migration 0064). Gated `("orderbook", action)` like the orders themselves.

Another workspace's order answers like a missing one (404). The Delivery log and the product image
refuse a frozen (Cancelled / Delivered) order, `409 ORDER_LOCKED`, like the order's other fields.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..files import uploads
from ..files.store import FileStore, get_default_store
from ..orders.queries import OrderLocked
from . import queries as q
from .schemas import (
    CutlistsOut, DeliveryIn, DeliveryLogOut, OrderCatalogItemsOut, PatchDeliveryIn, StockOut, TrackingOut,
)

router = APIRouter(tags=["order-tabs"])


def _store() -> FileStore:
    return get_default_store()


def _found(value, what: str = "order"):
    if value is None:
        raise HTTPException(404, f"{what} not found")
    return value


def _locked(e: OrderLocked) -> HTTPException:
    return HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status})


def _write(db: Session, fn, **kw):
    """Run a tab write, commit it, and turn a frozen order into 409."""
    try:
        out = fn(db, **kw)
    except OrderLocked as e:
        db.rollback()
        raise _locked(e) from e
    if out is None or out is False:
        db.rollback()
        raise HTTPException(404, "not found")
    db.commit()
    return out


# ── Delivery log ────────────────────────────────────────────────────────────────────────────────

@router.get("/orders/{po_id}/deliveries", response_model=DeliveryLogOut)
def list_deliveries(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return _found(q.delivery_log(db, po_id=po_id, workspace_id=user.workspace_id))


@router.post("/orders/{po_id}/deliveries", response_model=DeliveryLogOut, status_code=201)
def add_delivery(
    po_id: int,
    payload: DeliveryIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    return _write(db, q.add_delivery, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id, payload=payload)


@router.patch("/orders/{po_id}/deliveries/{delivery_id}", response_model=DeliveryLogOut)
def patch_delivery(
    po_id: int,
    delivery_id: int,
    payload: PatchDeliveryIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    return _write(db, q.patch_delivery, po_id=po_id, delivery_id=delivery_id, workspace_id=user.workspace_id,
                  actor_id=user.id, fields=payload.model_dump(exclude_unset=True))


@router.delete("/orders/{po_id}/deliveries/{delivery_id}", response_model=DeliveryLogOut)
def delete_delivery(
    po_id: int,
    delivery_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    return _write(db, q.delete_delivery, po_id=po_id, delivery_id=delivery_id,
                  workspace_id=user.workspace_id, actor_id=user.id)


@router.post("/orders/{po_id}/deliveries/{delivery_id}/docket", response_model=DeliveryLogOut, status_code=201)
async def upload_docket(
    po_id: int,
    delivery_id: int,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_store),
):
    stored = None
    try:
        stored = await uploads.store_upload(db, store, user=user, file=file, allowed=uploads.PDF_OR_IMAGE)
        return _write(db, q.set_docket, po_id=po_id, delivery_id=delivery_id, workspace_id=user.workspace_id,
                      actor_id=user.id, blob_id=stored.blob_id)
    except Exception:
        db.rollback()
        uploads.discard(db, store, stored)
        raise


@router.get("/orders/{po_id}/deliveries/{delivery_id}/docket")
def download_docket(
    po_id: int,
    delivery_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_store),
):
    blob = _found(q.docket_blob(db, po_id=po_id, delivery_id=delivery_id, workspace_id=user.workspace_id), "docket")
    return uploads.stream_blob(db, store, workspace_id=user.workspace_id, blob_id=blob)


@router.delete("/orders/{po_id}/deliveries/{delivery_id}/docket", response_model=DeliveryLogOut)
def delete_docket(
    po_id: int,
    delivery_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    return _write(db, q.set_docket, po_id=po_id, delivery_id=delivery_id, workspace_id=user.workspace_id,
                  actor_id=user.id, blob_id=None)


# ── read-only tabs ──────────────────────────────────────────────────────────────────────────────

@router.get("/orders/{po_id}/stock", response_model=StockOut)
def stock_tab(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"stock": _found(q.stock_orders(db, po_id=po_id, workspace_id=user.workspace_id))}


@router.get("/orders/{po_id}/tracking", response_model=TrackingOut)
def tracking_tab(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return _found(q.tracking(db, po_id=po_id, workspace_id=user.workspace_id))


@router.get("/orders/{po_id}/cutlists", response_model=CutlistsOut)
def cutlists_tab(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return _found(q.cutlists(db, po_id=po_id, workspace_id=user.workspace_id))


# ── catalog item: what the catalog says about the order's product code (read-only, nothing stored on the order) ──

@router.get("/orders/{po_id}/catalog-item", response_model=OrderCatalogItemsOut)
def catalog_item(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"items": _found(q.catalog_matches(db, po_id=po_id, workspace_id=user.workspace_id))}


@router.get("/orders/{po_id}/catalog-item/image")
def catalog_item_image(
    po_id: int,
    n: int = Query(0, ge=0, le=99),
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_store),
):
    """The picture of the order's n-th catalog match (as listed by `/catalog-item`), gated by `orderbook`, not `catalog`."""
    found, blob = q.catalog_match_image(db, po_id=po_id, workspace_id=user.workspace_id, n=n)
    _found(found or None)
    if blob is None:
        raise HTTPException(404, "image not found")
    return uploads.stream_blob(db, store, workspace_id=user.workspace_id, blob_id=blob)


# ── product image ───────────────────────────────────────────────────────────────────────────────

@router.put("/orders/{po_id}/image", status_code=204)
async def put_image(
    po_id: int,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_store),
):
    stored = None
    try:
        stored = await uploads.store_upload(db, store, user=user, file=file, allowed=uploads.IMAGE)
        _write(db, q.set_image, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id, blob_id=stored.blob_id)
    except Exception:
        db.rollback()
        uploads.discard(db, store, stored)
        raise


@router.get("/orders/{po_id}/image")
def get_image(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_store),
):
    order = _found(q.order_row(db, po_id=po_id, workspace_id=user.workspace_id))
    if order["image_blob"] is None:
        raise HTTPException(404, "image not found")
    return uploads.stream_blob(db, store, workspace_id=user.workspace_id, blob_id=order["image_blob"])


@router.delete("/orders/{po_id}/image", status_code=204)
def delete_image(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _write(db, q.set_image, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id, blob_id=None)
