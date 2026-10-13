"""PO documents: `/purchase-orders` (migration 0059). Gated `("orderbook", action)` like orders.

Reads need `orderbook:read`, every write `orderbook:write`; another workspace's PO answers like a
missing one (404). Cancelling a PO also cancels its Delivery Fee order, which needs `orderbook:approve`
when that order was already decided (`403 DECISION_FORBIDDEN`, nothing written).
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.rbac_engine import effective_actions
from ..auth.sessions import AuthUser
from ..db import get_db
from . import documents
from . import queries as q
from .schemas import (
    CreatePoIn, DeliveryIn, InvoiceIn, PatchInvoiceIn, PatchPoIn, PoListOut, PoOrdersIn, PoOut,
    PoStaffListOut,
)

router = APIRouter(tags=["purchase-orders"])

_NOT_FOUND = {"NOT_FOUND", "ORDER_NOT_FOUND", "USER_NOT_FOUND", "INVOICE_NOT_FOUND", "ORDER_NOT_ON_PO"}
_CONFLICT = {
    "PO_CANCELLED", "ORDER_ALREADY_ON_PO", "ORDER_NOT_OPEN", "SUPPLIER_MISMATCH", "IS_DELIVERY_ORDER",
    "ORDER_HAS_INVOICES", "NO_DELIVERY", "ORDER_LOCKED", "ORDER_ON_PO",
}


def _fail(code: str, data: dict | None) -> None:
    """Raise the HTTP error for a refusal code (`data` rides in the detail)."""
    detail = {"code": code, **jsonable_encoder(data or {})}
    if code == "NOT_FOUND":
        raise HTTPException(404, "purchase order not found")
    if code in _NOT_FOUND:
        raise HTTPException(404, detail)
    if code == "DECISION_FORBIDDEN":
        raise HTTPException(403, detail)
    if code in _CONFLICT:
        raise HTTPException(409, detail)
    raise HTTPException(409, detail)


def _result(db: Session, code: str, data: dict | None):
    if code != "OK":
        db.rollback()
        _fail(code, data)
    db.commit()
    return data


def _can_decide(db: Session, user: AuthUser) -> bool:
    return "approve" in effective_actions(db, user, "orderbook", None)


@router.get("/purchase-orders/staff", response_model=PoStaffListOut)
def staff_route(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"staff": q.list_staff(db, workspace_id=user.workspace_id)}


@router.get("/purchase-orders", response_model=PoListOut)
def list_route(
    vendor_id: int | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"purchase_orders": q.list_documents(db, workspace_id=user.workspace_id, vendor_id=vendor_id)}


@router.post("/purchase-orders", response_model=PoOut, status_code=201)
def create_route(
    payload: CreatePoIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.create_document(db, workspace_id=user.workspace_id, actor_id=user.id, payload=payload)
    return _result(db, code, data)


@router.get("/purchase-orders/{doc_id}", response_model=PoOut)
def get_route(
    doc_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    doc = q.get_document(db, doc_id=doc_id, workspace_id=user.workspace_id)
    if doc is None:
        raise HTTPException(404, "purchase order not found")
    return doc


@router.patch("/purchase-orders/{doc_id}", response_model=PoOut)
def patch_route(
    doc_id: int,
    payload: PatchPoIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.patch_document(db, doc_id=doc_id, workspace_id=user.workspace_id,
                                  actor_id=user.id, payload=payload)
    return _result(db, code, data)


@router.post("/purchase-orders/{doc_id}/orders", response_model=PoOut)
def add_orders_route(
    doc_id: int,
    payload: PoOrdersIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.add_orders(db, doc_id=doc_id, workspace_id=user.workspace_id,
                              actor_id=user.id, order_ids=payload.order_ids)
    return _result(db, code, data)


@router.delete("/purchase-orders/{doc_id}/orders/{order_id}", response_model=PoOut)
def remove_order_route(
    doc_id: int,
    order_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.remove_order(db, doc_id=doc_id, workspace_id=user.workspace_id,
                                actor_id=user.id, order_id=order_id)
    return _result(db, code, data)


@router.post("/purchase-orders/{doc_id}/cancel", response_model=PoOut)
def cancel_route(
    doc_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.cancel_document(db, doc_id=doc_id, workspace_id=user.workspace_id,
                                   actor_id=user.id, can_decide=_can_decide(db, user))
    return _result(db, code, data)


@router.put("/purchase-orders/{doc_id}/delivery", response_model=PoOut)
def set_delivery_route(
    doc_id: int,
    payload: DeliveryIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.set_delivery(db, doc_id=doc_id, workspace_id=user.workspace_id,
                                actor_id=user.id, amount=payload.amount)
    return _result(db, code, data)


@router.delete("/purchase-orders/{doc_id}/delivery", response_model=PoOut)
def remove_delivery_route(
    doc_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.remove_delivery(db, doc_id=doc_id, workspace_id=user.workspace_id,
                                   actor_id=user.id, can_decide=_can_decide(db, user))
    return _result(db, code, data)


@router.post("/purchase-orders/{doc_id}/invoices", response_model=PoOut, status_code=201)
def add_invoice_route(
    doc_id: int,
    payload: InvoiceIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.add_invoice(db, doc_id=doc_id, workspace_id=user.workspace_id,
                               actor_id=user.id, payload=payload)
    return _result(db, code, data)


@router.patch("/purchase-orders/{doc_id}/invoices/{invoice_id}", response_model=PoOut)
def patch_invoice_route(
    doc_id: int,
    invoice_id: int,
    payload: PatchInvoiceIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.patch_invoice(db, doc_id=doc_id, invoice_id=invoice_id,
                                 workspace_id=user.workspace_id, actor_id=user.id, payload=payload)
    return _result(db, code, data)


@router.delete("/purchase-orders/{doc_id}/invoices/{invoice_id}", response_model=PoOut)
def delete_invoice_route(
    doc_id: int,
    invoice_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, data = q.delete_invoice(db, doc_id=doc_id, invoice_id=invoice_id,
                                  workspace_id=user.workspace_id, actor_id=user.id)
    return _result(db, code, data)


def _doc_or_404(db: Session, doc_id: int, user: AuthUser) -> dict:
    doc = q.get_document(db, doc_id=doc_id, workspace_id=user.workspace_id)
    if doc is None:
        raise HTTPException(404, "purchase order not found")
    return doc


@router.get("/purchase-orders/{doc_id}/pdf")
def pdf_route(
    doc_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    doc = _doc_or_404(db, doc_id, user)
    return Response(documents.po_pdf(doc), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="PO-{doc["po_no"]}.pdf"'})


@router.get("/purchase-orders/{doc_id}/authorisation-form")
def authorisation_route(
    doc_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    doc = _doc_or_404(db, doc_id, user)
    return Response(documents.authorisation_pdf(doc), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="PO-{doc["po_no"]}-authorisation.pdf"'})


@router.get("/purchase-orders/{doc_id}/excel")
def excel_route(
    doc_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    doc = _doc_or_404(db, doc_id, user)
    return Response(
        documents.po_xlsx(doc),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="PO-{doc["po_no"]}.xlsx"'},
    )
