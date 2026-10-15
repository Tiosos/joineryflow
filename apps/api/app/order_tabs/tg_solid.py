"""TGSolid tab (migration 0065): the TG Solid production rows of an order.

One row per production run (production start, date made, made by, date ex factory, location, notes).
A record only: it does not move the Tracking item's stages. A closed (Cancelled / Delivered) order's
rows are read-only.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..orders.queries import OrderLocked
from ..sql_columns import require_columns
from . import queries as q

router = APIRouter(tags=["order-tabs"])

_COLS = "run_id, production_start, date_made, made_by, date_ex_factory, location, notes"


class RunIn(BaseModel):
    production_start: date | None = None
    date_made: date | None = None
    made_by: str | None = Field(default=None, max_length=100)
    date_ex_factory: date | None = None
    location: str | None = Field(default=None, max_length=50)
    notes: str | None = None


class RunOut(RunIn):
    run_id: int


class RunListOut(BaseModel):
    runs: list[RunOut]


_PATCHABLE = frozenset({"production_start", "date_made", "made_by", "date_ex_factory", "location", "notes"})


def list_runs(db: Session, *, po_id: int, workspace_id: int) -> list[dict] | None:
    if q.order_row(db, po_id=po_id, workspace_id=workspace_id) is None:
        return None
    rows = db.execute(text(f"SELECT {_COLS} FROM order_tg_run WHERE po_id = :o ORDER BY run_id"), {"o": po_id}).mappings().all()
    return [dict(r) for r in rows]


def _write(db: Session, po_id: int, workspace_id: int, fn) -> dict | None:
    try:
        if not q._lock(db, po_id, workspace_id):
            return None
        if fn() is False:
            return None
    except OrderLocked as e:
        db.rollback()
        raise HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status}) from e
    db.commit()
    return {"runs": list_runs(db, po_id=po_id, workspace_id=workspace_id)}


@router.get("/orders/{po_id}/tg-runs", response_model=RunListOut)
def list_route(po_id: int, user: AuthUser = Depends(require_permission("orderbook", "read")), db: Session = Depends(get_db)):
    runs = list_runs(db, po_id=po_id, workspace_id=user.workspace_id)
    if runs is None:
        raise HTTPException(404, "order not found")
    return {"runs": runs}


@router.post("/orders/{po_id}/tg-runs", response_model=RunListOut, status_code=201)
def add_route(po_id: int, payload: RunIn, user: AuthUser = Depends(require_permission("orderbook", "write")),
              db: Session = Depends(get_db)):
    def go():
        rid = db.execute(
            text("INSERT INTO order_tg_run (po_id, production_start, date_made, made_by, date_ex_factory, location, notes,"
                 " created_by) VALUES (:o, :ps, :dm, :mb, :de, :l, :n, :u) RETURNING run_id"),
            {"o": po_id, "ps": payload.production_start, "dm": payload.date_made, "mb": payload.made_by,
             "de": payload.date_ex_factory, "l": payload.location, "n": payload.notes, "u": user.id},
        ).scalar_one()
        write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="order.tg_run.add",
                    target=f"order:{po_id}", payload={"run_id": rid})
    out = _write(db, po_id, user.workspace_id, go)
    if out is None:
        db.rollback()
        raise HTTPException(404, "order not found")
    return out


@router.patch("/orders/{po_id}/tg-runs/{run_id}", response_model=RunListOut)
def patch_route(po_id: int, run_id: int, payload: RunIn, user: AuthUser = Depends(require_permission("orderbook", "write")),
                db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude_unset=True)

    def go():
        if not db.execute(text("SELECT 1 FROM order_tg_run WHERE run_id = :r AND po_id = :o"), {"r": run_id, "o": po_id}).first():
            return False
        if fields:
            require_columns(fields, _PATCHABLE)
            sets = ", ".join(f"{k} = :{k}" for k in fields)
            db.execute(text(f"UPDATE order_tg_run SET {sets}, updated_at = now() WHERE run_id = :r"), {**fields, "r": run_id})
            write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="order.tg_run.update",
                        target=f"order:{po_id}", payload={"run_id": run_id, "fields": sorted(fields)})
    out = _write(db, po_id, user.workspace_id, go)
    if out is None:
        db.rollback()
        raise HTTPException(404, "not found")
    return out


@router.delete("/orders/{po_id}/tg-runs/{run_id}", response_model=RunListOut)
def delete_route(po_id: int, run_id: int, user: AuthUser = Depends(require_permission("orderbook", "write")),
                 db: Session = Depends(get_db)):
    def go():
        if not db.execute(text("DELETE FROM order_tg_run WHERE run_id = :r AND po_id = :o RETURNING run_id"),
                          {"r": run_id, "o": po_id}).first():
            return False
        write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="order.tg_run.remove",
                    target=f"order:{po_id}", payload={"run_id": run_id})
    out = _write(db, po_id, user.workspace_id, go)
    if out is None:
        db.rollback()
        raise HTTPException(404, "not found")
    return out
