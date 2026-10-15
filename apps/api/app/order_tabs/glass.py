"""Glass C tab (migration 0065): the old Glass Calc price calculator.

A per-workspace price list (`glass_rate`): `glass` rates are per m2 and `process` rates per metre of
perimeter (`Lm`) or per each; an order keeps the size being costed and which rates are ticked
(`order_glass_calc`). The cost is worked out here on every read: qty x rate x (area in m2 for `m2`,
perimeter in metres for `Lm`, 1 for anything else), each line rounded to cents and the total rounded
from the unrounded sum (the old screen's total: $63.25 + $15.96 shows $79.22). Calculator only: the
total is shown, never written to the order.
"""
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..orders.queries import OrderLocked
from ..schema_guards import no_null
from ..sql_columns import require_columns
from . import queries as q

router = APIRouter(tags=["order-tabs"])

_SIZE = re.compile(r"(\d{2,5})\s*[xX×]\s*(\d{2,5})(?:\s*[xX×]\s*(\d{1,3}))?")
_RATE_COLS = "glass_rate_id, kind, name, rate, um, supplier_no, sort_order, is_active"


class RateOut(BaseModel):
    glass_rate_id: int
    kind: Literal["glass", "process"]
    name: str
    rate: Decimal
    um: str
    supplier_no: str | None
    sort_order: int
    is_active: bool


class RateListOut(BaseModel):
    rates: list[RateOut]


class RateIn(BaseModel):
    kind: Literal["glass", "process"]
    name: str = Field(min_length=1, max_length=150)
    rate: Decimal = Field(ge=0, max_digits=15, decimal_places=4)
    um: str = Field(min_length=1, max_length=10)
    supplier_no: str | None = Field(default=None, max_length=50)
    sort_order: int = 0


class PatchRateIn(BaseModel):
    reject_null = no_null("name", "rate", "um", "sort_order", "is_active")
    name: str | None = Field(default=None, min_length=1, max_length=150)
    rate: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=4)
    um: str | None = Field(default=None, min_length=1, max_length=10)
    supplier_no: str | None = Field(default=None, max_length=50)
    sort_order: int | None = None
    is_active: bool | None = None


class SelectionEntry(BaseModel):
    qty: Decimal = Field(default=Decimal(1), gt=0, max_digits=10, decimal_places=3)
    ticked: bool = False


class GlassCalcIn(BaseModel):
    length_mm: int | None = Field(default=None, gt=0, le=100000)
    width_mm: int | None = Field(default=None, gt=0, le=100000)
    thick_mm: int | None = Field(default=None, gt=0, le=1000)
    selection: dict[int, SelectionEntry] = {}


class CalcLineOut(BaseModel):
    glass_rate_id: int
    kind: Literal["glass", "process"]
    name: str
    rate: Decimal
    um: str
    supplier_no: str | None
    qty: Decimal
    ticked: bool
    cost: Decimal


class SuggestedSize(BaseModel):
    length_mm: int
    width_mm: int
    thick_mm: int | None


class GlassCalcOut(BaseModel):
    length_mm: int | None
    width_mm: int | None
    thick_mm: int | None
    area_m2: Decimal | None
    perimeter_m: Decimal | None
    lines: list[CalcLineOut]
    total: Decimal
    suggested_size: SuggestedSize | None


def suggested_size(description: str | None) -> dict | None:
    """The size an order's description starts with ("1471 x 1000 x 6 ..."), for the Copy Size button."""
    m = _SIZE.search(description or "")
    if not m:
        return None
    return {"length_mm": int(m.group(1)), "width_mm": int(m.group(2)), "thick_mm": int(m.group(3)) if m.group(3) else None}


def _cents(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), ROUND_HALF_UP)


def _factor(um: str, area: Decimal | None, perimeter: Decimal | None) -> Decimal:
    u = um.strip().lower()
    if u == "m2":
        return area or Decimal(0)
    if u == "lm":
        return perimeter or Decimal(0)
    return Decimal(1)


def list_rates(db: Session, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(f"SELECT {_RATE_COLS} FROM glass_rate WHERE workspace_id = :w ORDER BY kind, sort_order, lower(name)"),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_rate(db: Session, *, workspace_id: int, actor_id: int, payload: RateIn) -> dict | None:
    row = db.execute(
        text(
            "INSERT INTO glass_rate (workspace_id, kind, name, rate, um, supplier_no, sort_order)"
            " VALUES (:w, :k, :n, :r, :u, :s, :o) ON CONFLICT (workspace_id, kind, lower(name)) DO NOTHING"
            f" RETURNING {_RATE_COLS}"
        ),
        {"w": workspace_id, "k": payload.kind, "n": payload.name.strip(), "r": payload.rate, "u": payload.um.strip(),
         "s": payload.supplier_no, "o": payload.sort_order},
    ).mappings().first()
    if row is None:
        return None
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="glass_rate.create",
                target=str(row["glass_rate_id"]), payload={"name": row["name"], "kind": row["kind"]})
    return dict(row)


_RATE_PATCHABLE = frozenset({"name", "rate", "um", "supplier_no", "sort_order", "is_active"})


def patch_rate(db: Session, *, rate_id: int, workspace_id: int, actor_id: int, fields: dict) -> tuple[str, dict | None]:
    """'OK' | 'NOT_FOUND' | 'EXISTS'."""
    require_columns(fields, _RATE_PATCHABLE)
    cur = db.execute(
        text(f"SELECT {_RATE_COLS} FROM glass_rate WHERE glass_rate_id = :i AND workspace_id = :w FOR UPDATE"),
        {"i": rate_id, "w": workspace_id},
    ).mappings().first()
    if cur is None:
        return "NOT_FOUND", None
    fields = {k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items() if v != cur[k]}
    if not fields:
        return "OK", dict(cur)
    if "name" in fields and db.execute(
        text("SELECT 1 FROM glass_rate WHERE workspace_id = :w AND kind = :k AND lower(name) = lower(:n)"
             " AND glass_rate_id <> :i"),
        {"w": workspace_id, "k": cur["kind"], "n": fields["name"], "i": rate_id},
    ).first():
        return "EXISTS", None
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = db.execute(text(f"UPDATE glass_rate SET {sets} WHERE glass_rate_id = :i RETURNING {_RATE_COLS}"),
                     {**fields, "i": rate_id}).mappings().one()
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="glass_rate.update",
                target=str(rate_id), payload={"fields": sorted(fields)})
    return "OK", dict(row)


def calc(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    order = q.order_row(db, po_id=po_id, workspace_id=workspace_id)
    if order is None:
        return None
    saved = db.execute(
        text("SELECT length_mm, width_mm, thick_mm, selection FROM order_glass_calc WHERE po_id = :o"), {"o": po_id}
    ).mappings().first() or {"length_mm": None, "width_mm": None, "thick_mm": None, "selection": {}}
    length, width = saved["length_mm"], saved["width_mm"]
    area = Decimal(length) * Decimal(width) / Decimal(1_000_000) if length and width else None
    perimeter = Decimal(2 * (length + width)) / Decimal(1000) if length and width else None
    sel = saved["selection"] or {}
    lines, exact_total = [], Decimal(0)
    for r in list_rates(db, workspace_id=workspace_id):
        entry = sel.get(str(r["glass_rate_id"]), {})
        if not r["is_active"] and not entry.get("ticked"):
            continue
        qty = Decimal(str(entry.get("qty", 1)))
        ticked = bool(entry.get("ticked"))
        exact = qty * r["rate"] * _factor(r["um"], area, perimeter) if ticked else Decimal(0)
        exact_total += exact
        lines.append({**{k: r[k] for k in ("glass_rate_id", "kind", "name", "rate", "um", "supplier_no")},
                      "qty": qty, "ticked": ticked, "cost": _cents(exact)})
    return {
        "length_mm": length, "width_mm": width, "thick_mm": saved["thick_mm"],
        "area_m2": None if area is None else area.quantize(Decimal("0.0001")),
        "perimeter_m": None if perimeter is None else perimeter.quantize(Decimal("0.0001")),
        "lines": lines, "total": _cents(exact_total), "suggested_size": suggested_size(order["description"]),
    }


def save_calc(db: Session, *, po_id: int, workspace_id: int, actor_id: int, payload: GlassCalcIn) -> str:
    """'OK' | 'NOT_FOUND' | 'RATE_NOT_FOUND'. Raises `OrderLocked` for a frozen order."""
    if not q._lock(db, po_id, workspace_id):
        return "NOT_FOUND"
    known = {int(i) for i in db.execute(text("SELECT glass_rate_id FROM glass_rate WHERE workspace_id = :w"),
                                        {"w": workspace_id}).scalars()}
    if any(rid not in known for rid in payload.selection):
        return "RATE_NOT_FOUND"
    selection = {str(rid): {"qty": str(e.qty), "ticked": e.ticked} for rid, e in payload.selection.items()}
    db.execute(
        text(
            "INSERT INTO order_glass_calc (po_id, length_mm, width_mm, thick_mm, selection)"
            " VALUES (:o, :l, :w, :t, CAST(:s AS jsonb)) ON CONFLICT (po_id) DO UPDATE SET"
            " length_mm = EXCLUDED.length_mm, width_mm = EXCLUDED.width_mm, thick_mm = EXCLUDED.thick_mm,"
            " selection = EXCLUDED.selection, updated_at = now()"
        ),
        {"o": po_id, "l": payload.length_mm, "w": payload.width_mm, "t": payload.thick_mm, "s": json.dumps(selection)},
    )
    return "OK"


# ── routes ──────────────────────────────────────────────────────────────────────────────────────

def _keeper(user: AuthUser) -> None:
    if user.auth_role not in ("purchase_officer", "admin"):
        raise HTTPException(403, {"code": "GLASS_RATE_FORBIDDEN"})


@router.get("/glass-rates", response_model=RateListOut)
def list_rates_route(
    user: AuthUser = Depends(require_permission("orderbook", "read")), db: Session = Depends(get_db),
):
    return {"rates": list_rates(db, workspace_id=user.workspace_id)}


@router.post("/glass-rates", response_model=RateOut, status_code=201)
def create_rate_route(
    payload: RateIn, user: AuthUser = Depends(require_permission("orderbook", "write")), db: Session = Depends(get_db),
):
    _keeper(user)
    row = create_rate(db, workspace_id=user.workspace_id, actor_id=user.id, payload=payload)
    if row is None:
        raise HTTPException(409, {"code": "GLASS_RATE_EXISTS"})
    db.commit()
    return row


@router.patch("/glass-rates/{rate_id}", response_model=RateOut)
def patch_rate_route(
    rate_id: int, payload: PatchRateIn, user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _keeper(user)
    code, row = patch_rate(db, rate_id=rate_id, workspace_id=user.workspace_id, actor_id=user.id,
                           fields=payload.model_dump(exclude_unset=True))
    if code == "NOT_FOUND":
        raise HTTPException(404, "rate not found")
    if code == "EXISTS":
        raise HTTPException(409, {"code": "GLASS_RATE_EXISTS"})
    db.commit()
    return row


@router.get("/orders/{po_id}/glass-calc", response_model=GlassCalcOut)
def get_calc_route(
    po_id: int, user: AuthUser = Depends(require_permission("orderbook", "read")), db: Session = Depends(get_db),
):
    out = calc(db, po_id=po_id, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(404, "order not found")
    return out


@router.put("/orders/{po_id}/glass-calc", response_model=GlassCalcOut)
def put_calc_route(
    po_id: int, payload: GlassCalcIn, user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    try:
        code = save_calc(db, po_id=po_id, workspace_id=user.workspace_id, actor_id=user.id, payload=payload)
    except OrderLocked as e:
        db.rollback()
        raise HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status}) from e
    if code == "NOT_FOUND":
        db.rollback()
        raise HTTPException(404, "order not found")
    if code == "RATE_NOT_FOUND":
        db.rollback()
        raise HTTPException(404, {"code": "RATE_NOT_FOUND"})
    db.commit()
    return calc(db, po_id=po_id, workspace_id=user.workspace_id)
