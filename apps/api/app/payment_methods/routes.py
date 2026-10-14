"""`/payment-methods`: read by the Orderbook's people, kept by a purchase officer or admin (like cost centres)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import PatchPaymentMethodIn, PaymentMethodIn, PaymentMethodListOut, PaymentMethodOut

router = APIRouter(tags=["payment-methods"])


def _keeper(user: AuthUser) -> None:
    if user.auth_role not in ("purchase_officer", "admin"):
        raise HTTPException(403, {"code": "PAYMENT_METHOD_FORBIDDEN"})


@router.get("/payment-methods", response_model=PaymentMethodListOut)
def list_route(
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"payment_methods": q.list_methods(db, workspace_id=user.workspace_id)}


@router.post("/payment-methods", response_model=PaymentMethodOut, status_code=201)
def create_route(
    payload: PaymentMethodIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _keeper(user)
    row = q.create_method(db, workspace_id=user.workspace_id, actor_id=user.id, name=payload.name)
    if row is None:
        raise HTTPException(409, {"code": "PAYMENT_METHOD_EXISTS"})
    db.commit()
    return row


@router.patch("/payment-methods/{payment_method_id}", response_model=PaymentMethodOut)
def patch_route(
    payment_method_id: int,
    payload: PatchPaymentMethodIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _keeper(user)
    code, row = q.patch_method(
        db, payment_method_id=payment_method_id, workspace_id=user.workspace_id, actor_id=user.id,
        changes=payload.model_dump(exclude_unset=True))
    if code == "NOT_FOUND":
        raise HTTPException(404, "payment method not found")
    if code == "EXISTS":
        raise HTTPException(409, {"code": "PAYMENT_METHOD_EXISTS"})
    db.commit()
    return row
