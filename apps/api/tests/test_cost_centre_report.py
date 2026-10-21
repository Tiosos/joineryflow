"""GET /cost-centers/report: the budget across every cost centre, for managers and admins.

One row per cost centre (the ledger's committed / spent / remaining and how many live orders it
holds), the totals, and an "Unallocated" line for the orders that have no cost centre (which the
ledger cannot see). Cancelled and Rejected orders are not counted. Another workspace's data is never
in it.
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace

_cleanup = truncate_fixture("budget_transactions", "cost_centers")


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
    buyer, wid, _ = login("purchase_officer", prefix="cr")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    manager, _ = login_same_workspace(wid, "manager")
    return {"wid": wid, "vendor": vendor, "buyer": buyer, "manager": manager}


def _cc(c, code, budget):
    r = c.post("/cost-centers", json={"code": code, "name": f"Name {code}", "budget_amount": budget})
    assert r.status_code == 201, r.text
    return r.json()["cost_center_id"]


def _order(ws, total, cost_center=None, status=None):
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "o",
                                          "total_amount": total}).json()
    if cost_center is not None:
        assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cost_center}).status_code == 200
    if status:
        assert ws["manager"].patch(f"/orders/{o['po_id']}", json={"status": status}).status_code == 200, status
    return o["po_id"]


def test_the_report_sums_the_ledger_per_cost_centre_and_in_total(ws):
    a, b = _cc(ws["buyer"], "AAA", "10000"), _cc(ws["buyer"], "BBB", "5000")
    _order(ws, "2500.00", a, "Approved")               # committed 2500
    _order(ws, "1000.00", a, "Delivered")              # spent 1000 (Approved first would also commit)
    _order(ws, "400.00", b)                            # Pending: on B but not in the ledger
    r = ws["manager"].get("/cost-centers/report")
    assert r.status_code == 200, r.text
    body = r.json()
    rows = {x["code"]: x for x in body["rows"]}
    assert [x["code"] for x in body["rows"]] == ["AAA", "BBB"]
    assert (rows["AAA"]["budget_amount"], rows["AAA"]["committed"], rows["AAA"]["spent"],
            rows["AAA"]["remaining"], rows["AAA"]["order_count"]) == ("10000.00", "2500.00", "1000.00", "6500.00", 2)
    assert (rows["BBB"]["committed"], rows["BBB"]["spent"], rows["BBB"]["remaining"],
            rows["BBB"]["order_count"]) == ("0.00", "0.00", "5000.00", 1)
    assert rows["AAA"]["fiscal_year"] and rows["AAA"]["is_active"] is True
    assert body["totals"] == {"budget_amount": "15000.00", "committed": "2500.00", "spent": "1000.00",
                              "remaining": "11500.00", "order_count": 3}


def test_unallocated_counts_live_orders_with_no_cost_centre_only(ws):
    a = _cc(ws["buyer"], "AAA", "100")
    _order(ws, "700.00")                                # no cost centre: unallocated
    _order(ws, "50.00")                                 # and another
    cancelled = _order(ws, "9999.00")
    assert ws["buyer"].delete(f"/orders/{cancelled}").status_code == 204          # not counted
    _order(ws, "300.00", a)                             # on a cost centre: not unallocated
    body = ws["manager"].get("/cost-centers/report").json()
    assert body["unallocated"] == {"order_count": 2, "total_amount": "750.00"}
    assert body["totals"]["order_count"] == 1           # the totals are the cost centres' own


def test_a_cancelled_or_rejected_order_is_not_counted_on_its_cost_centre(ws):
    a = _cc(ws["buyer"], "AAA", "100")
    keep = _order(ws, "10.00", a)
    gone = _order(ws, "20.00", a)
    rejected = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "r",
                                                 "total_amount": "30.00"}).json()["po_id"]
    ws["buyer"].patch(f"/orders/{rejected}", json={"cost_center_id": a})
    assert ws["manager"].patch(f"/orders/{rejected}", json={"status": "Rejected",
                                                              "rejection_note": "no"}).status_code == 200
    ws["buyer"].delete(f"/orders/{gone}")
    row = ws["manager"].get("/cost-centers/report").json()["rows"][0]
    assert row["order_count"] == 1
    assert ws["manager"].get(f"/orders/{keep}").json()["cost_center_id"] == a      # the one that stays


def test_an_inactive_cost_centre_is_still_listed_and_flagged(ws):
    a = _cc(ws["buyer"], "AAA", "100")
    assert ws["buyer"].patch(f"/cost-centers/{a}", json={"is_active": False}).status_code == 200
    rows = ws["manager"].get("/cost-centers/report").json()["rows"]
    assert [(x["code"], x["is_active"]) for x in rows] == [("AAA", False)]


def test_only_managers_and_admins_may_read_it(ws):
    _cc(ws["buyer"], "AAA", "100")
    for role in ("purchase_officer", "drafter", "editor", "estimator", "viewer"):
        c, _ = login_same_workspace(ws["wid"], role)
        r = c.get("/cost-centers/report")
        assert (r.status_code, r.json()["detail"]) == (403, {"code": "BUDGET_FORBIDDEN"}), role
    admin, _ = login_same_workspace(ws["wid"], "admin")
    assert admin.get("/cost-centers/report").status_code == 200


def test_another_workspace_never_appears_in_the_report(ws):
    _cc(ws["buyer"], "AAA", "100")
    _order(ws, "123.00")
    other_manager, _, _ = login("manager", prefix="cr2")
    body = other_manager.get("/cost-centers/report").json()
    assert body["rows"] == [] and body["unallocated"] == {"order_count": 0, "total_amount": "0.00"}
    assert body["totals"]["budget_amount"] == "0.00"


def test_an_empty_workspace_reports_zeros(ws):
    body = ws["manager"].get("/cost-centers/report").json()
    assert body == {"rows": [], "unallocated": {"order_count": 0, "total_amount": "0.00"},
                    "totals": {"budget_amount": "0.00", "committed": "0.00", "spent": "0.00",
                               "remaining": "0.00", "order_count": 0}}
