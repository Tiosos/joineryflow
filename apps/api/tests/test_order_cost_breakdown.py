"""Material cost by order type: the Orderbook's Cost centre pop-up and Tracking > Info > Budget.

The Orderbook breakdown is open to anyone who can read it, over every order; a
project's budget is for managers and admins only (the budget is for project managers and above).
Cancelled and Rejected orders are not counted. Labour hours are null until payroll is connected.
"""
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login, login_same_workspace

_cleanup = truncate_fixture("purchase_orders", "vendors")


def _sql(sql: str, **p):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), p)
        val = out.scalar() if out.returns_rows else None
        s.commit()
        return val
    finally:
        s.close()


@pytest.fixture
def ws():
    admin, wid, uid = login("admin", prefix="cb")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('Acme', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    s = SessionLocal()
    try:
        pid = create_project(s, uid=uid)
        s.commit()
    finally:
        s.close()
    return {"wid": wid, "vendor": vendor, "pid": pid, "admin": admin,
            "manager": login_same_workspace(wid, "manager")[0],
            "drafter": login_same_workspace(wid, "drafter")[0],
            "buyer": login_same_workspace(wid, "purchase_officer")[0]}


def _order(c, ws, category, total, **extra):
    r = c.post("/orders", json={"vendor_id": ws["vendor"], "description": f"{category} order",
                                "category": category, "total_amount": total,
                                "project_id": ws["pid"], **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _by_label(body):
    return {g["label"]: g for g in body["groups"]}


def test_breakdown_groups_by_type_and_leaves_out_cancelled_and_rejected(ws):
    c = ws["buyer"]
    _order(c, ws, "Board", "100.00")
    _order(c, ws, "Board", "50.50")
    _order(c, ws, "Acoustic", "400.00")
    gone = _order(c, ws, "Benchtop", "999.00")
    nope = _order(c, ws, "Benchtop", "888.00")
    assert c.delete(f"/orders/{gone['po_id']}").status_code == 204
    assert c.patch(f"/orders/{nope['po_id']}",
                   json={"status": "Rejected", "rejection_note": "no"}).status_code == 200
    body = c.get("/orders/cost-breakdown").json()
    g = _by_label(body)
    assert set(g) == {"Board", "Acoustic panel"}
    assert g["Board"]["order_count"] == 2 and Decimal(g["Board"]["total"]) == Decimal("150.50")
    assert [o["total_amount"] for o in g["Board"]["orders"]] == ["100.00", "50.50"]
    assert Decimal(body["total"]) == Decimal("550.50")


def test_breakdown_is_workspace_scoped(ws):
    _order(ws["buyer"], ws, "Board", "10.00")
    other, _wid, _uid = login("admin", prefix="cb2")
    assert other.get("/orders/cost-breakdown").json() == {"groups": [], "total": "0"}


def test_project_budget_is_for_managers_and_admins_only(ws):
    _order(ws["buyer"], ws, "Board", "100.00")
    url = f"/projects/{ws['pid']}/budget"
    for who in ("manager", "admin"):
        r = ws[who].get(url)
        assert r.status_code == 200, r.text
        assert Decimal(r.json()["total"]) == Decimal("100.00")
        assert r.json()["labour_hours"] is None
    for who in ("drafter", "buyer"):
        r = ws[who].get(url)
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "BUDGET_FORBIDDEN"


def test_project_budget_counts_only_that_projects_orders(ws):
    _order(ws["buyer"], ws, "Board", "100.00")
    r = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "x",
                                          "category": "Board", "total_amount": "7.00"})
    assert r.status_code == 201
    assert Decimal(ws["manager"].get(f"/projects/{ws['pid']}/budget").json()["total"]) == Decimal("100.00")


def test_new_order_fields_round_trip(ws):
    c = ws["buyer"]
    o = _order(c, ws, "Acoustic", "2580.00", quantity="6", unit_cost="430.00",
               attributes={"board_length": 2800, "colour": "Navy"})
    assert o["category"] == "Acoustic" and o["requester_name"]
    assert o["grand_total"] == "2838.00" and o["gst_amount"] == "258.00"
    r = c.patch(f"/orders/{o['po_id']}", json={
        "arrived_date": "2026-03-01", "stock_tracked": True, "gst_included_in_price": True,
        "line_item_comments": "Front 10/10", "product_website": "https://example.test/p"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["arrived_date"], b["stock_tracked"], b["line_item_comments"]) == (
        "2026-03-01", True, "Front 10/10")
    assert b["gst_amount"] == "0.00" and b["grand_total"] == "2580.00"
    for field in ("stock_tracked", "gst_applicable", "gst_included_in_price"):
        assert c.patch(f"/orders/{o['po_id']}", json={field: None}).status_code == 422
