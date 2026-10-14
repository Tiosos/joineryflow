"""Builders shared by the PO tests: a workspace with a purchase officer, a viewer and two suppliers."""
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login, login_same_workspace


def _sql(sql: str, **p):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), p)
        val = out.scalar() if out.returns_rows else None
        s.commit()
        return val
    finally:
        s.close()


def make_ws() -> dict:
    buyer, wid, _ = login("purchase_officer", prefix="pd")
    v1 = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('Laminex', 'Board', :w)"
              " RETURNING vendor_id", w=wid)
    v2 = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('Other', 'Board', :w)"
              " RETURNING vendor_id", w=wid)
    viewer, _ = login_same_workspace(wid, "viewer")
    return {"wid": wid, "buyer": buyer, "viewer": viewer, "v1": v1, "v2": v2}


def _order(ws, vendor="v1", total="100.00", **extra):
    body = {"vendor_id": ws[vendor], "description": "Board", "quantity": 1, "unit_cost": total,
            "total_amount": total, **extra}
    r = ws["buyer"].post("/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()["po_id"]


def _po(ws, *order_ids, **body):
    r = ws["buyer"].post("/purchase-orders", json={"order_ids": list(order_ids), **body})
    assert r.status_code == 201, r.text
    return r.json()


def _code(r):
    return r.json()["detail"]["code"]
