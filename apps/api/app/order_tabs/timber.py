"""Timber tab (migration 0065): the Timberwood Panels custom pressing order form.

The fields are kept on the order (`order_timber_form`, one row); Create renders the sheet as a PDF from
the saved fields and keeps it, like the PO Authorisation Form. The user emails it by hand. CLEAR in the
screen is a save of empty fields. A closed (Cancelled / Delivered) order's form is read-only.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..files import uploads
from ..files.store import FileStore, get_default_store
from ..orders.queries import OrderLocked
from ..printing.engine import render_template_to_pdf
from . import queries as q

router = APIRouter(tags=["order-tabs"])

_COLS = ("face", "back", "substrate", "face_by_tg", "back_by_tg", "substrate_by_tg",
         "finished_description", "deliver_to", "special_instructions")


class TimberIn(BaseModel):
    face: str | None = Field(default=None, max_length=200)
    back: str | None = Field(default=None, max_length=200)
    substrate: str | None = Field(default=None, max_length=200)
    face_by_tg: bool = False
    back_by_tg: bool = False
    substrate_by_tg: bool = False
    finished_description: str | None = None
    deliver_to: str | None = None
    special_instructions: str | None = None


class TimberOut(TimberIn):
    has_form: bool
    form_created_at: datetime | None


def get_form(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    if q.order_row(db, po_id=po_id, workspace_id=workspace_id) is None:
        return None
    row = db.execute(
        text(f"SELECT {', '.join(_COLS)}, (form_blob IS NOT NULL) AS has_form, form_created_at"
             " FROM order_timber_form WHERE po_id = :o"),
        {"o": po_id},
    ).mappings().first()
    if row is None:
        return {**TimberIn().model_dump(), "has_form": False, "form_created_at": None}
    return dict(row)


def save_form(db: Session, *, po_id: int, workspace_id: int, actor_id: int, payload: TimberIn) -> bool:
    if not q._lock(db, po_id, workspace_id):
        return False
    values = payload.model_dump()
    db.execute(
        text(
            f"INSERT INTO order_timber_form (po_id, {', '.join(_COLS)})"
            f" VALUES (:po, {', '.join(':' + c for c in _COLS)})"
            " ON CONFLICT (po_id) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLS) + ", updated_at = now()"
        ),
        {"po": po_id, **values},
    )
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="order.timber.save", target=f"order:{po_id}", payload={})
    return True


def form_blob(db: Session, *, po_id: int, workspace_id: int) -> int | None:
    if q.order_row(db, po_id=po_id, workspace_id=workspace_id) is None:
        return None
    return db.execute(text("SELECT form_blob FROM order_timber_form WHERE po_id = :o"), {"o": po_id}).scalar()


@router.get("/orders/{po_id}/timber", response_model=TimberOut)
def get_route(
    po_id: int, user: AuthUser = Depends(require_permission("orderbook", "read")), db: Session = Depends(get_db),
):
    out = get_form(db, po_id=po_id, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(404, "order not found")
    return out


@router.put("/orders/{po_id}/timber", response_model=TimberOut)
def put_route(
    po_id: int, payload: TimberIn, user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    try:
        ok = save_form(db, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id, payload=payload)
    except OrderLocked as e:
        db.rollback()
        raise HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status}) from e
    if not ok:
        db.rollback()
        raise HTTPException(404, "order not found")
    db.commit()
    return get_form(db, po_id=po_id, workspace_id=user.workspace_id)


@router.post("/orders/{po_id}/timber/form", response_model=TimberOut, status_code=201)
def create_form_route(
    po_id: int, user: AuthUser = Depends(require_permission("orderbook", "write")), db: Session = Depends(get_db),
    store: FileStore = Depends(get_default_store),
):
    """Create: render the sheet from the saved fields and keep that PDF on the order."""
    order = q.order_row(db, po_id=po_id, workspace_id=user.workspace_id)
    if order is None:
        raise HTTPException(404, "order not found")
    vendor = db.execute(text("SELECT v.name FROM purchase_orders po JOIN vendors v ON v.vendor_id = po.vendor_id"
                             " WHERE po.po_id = :o"), {"o": po_id}).scalar()
    fields = get_form(db, po_id=po_id, workspace_id=user.workspace_id)
    pdf = render_template_to_pdf("order_timber_form.html", {
        "order": order, "vendor_name": vendor, "f": fields, "today": datetime.now().strftime("%d/%m/%Y"),
    })
    stored = None
    try:
        if not save_form(db, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id,
                         payload=TimberIn(**{k: fields[k] for k in _COLS})):
            raise HTTPException(404, "order not found")
        stored = uploads.store_bytes(db, store, user=user, payload=pdf,
                                     name=f"order-{order['po_number']}-timberwood-form.pdf", mime="application/pdf")
        db.execute(text("UPDATE order_timber_form SET form_blob = :b, form_created_at = now() WHERE po_id = :o"),
                   {"b": stored.blob_id, "o": po_id})
        write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="order.timber.form",
                    target=f"order:{po_id}", payload={})
        db.commit()
    except OrderLocked as e:
        db.rollback()
        raise HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status}) from e
    except Exception:
        db.rollback()
        uploads.discard(db, store, stored)
        raise
    return get_form(db, po_id=po_id, workspace_id=user.workspace_id)


@router.get("/orders/{po_id}/timber/form")
def download_form_route(
    po_id: int, user: AuthUser = Depends(require_permission("orderbook", "read")), db: Session = Depends(get_db),
    store: FileStore = Depends(get_default_store),
):
    blob = form_blob(db, po_id=po_id, workspace_id=user.workspace_id)
    if blob is None:
        raise HTTPException(404, "form not found")
    return uploads.stream_blob(db, store, workspace_id=user.workspace_id, blob_id=blob)
