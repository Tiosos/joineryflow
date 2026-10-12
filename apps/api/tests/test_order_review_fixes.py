"""Fixes from the October 2026 code review of the Orderbook changes.

1. `DELETE /orders/{id}` (cancel) moved an Approved or Rejected order without the `orderbook:approve`
   grant that a status PATCH needs, so a drafter could release a commitment by cancelling.
2. `PatchOrderIn` lacked the length limits `CreateOrderIn` has, so a long value reached a bounded
   varchar column as a raw 500.
3. `PatchSupplierIn` took any status string (the database allows four) and had no length limits.
5. A cost centre code or name of only spaces passed `min_length=1` and was stored empty.
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace

_cleanup = truncate_fixture("budget_transactions", "cost_centers", "purchase_orders", "vendors")


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
    buyer, wid, _uid = login("purchase_officer", prefix="rv")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    drafter, _ = login_same_workspace(wid, "drafter")
    return {"wid": wid, "vendor": vendor, "buyer": buyer, "drafter": drafter}


def _order(c, ws):
    r = c.post("/orders", json={"vendor_id": ws["vendor"], "description": "o", "total_amount": "100.00"})
    assert r.status_code == 201, r.text
    return r.json()["po_id"]


def _code(r):
    return r.json()["detail"]["code"]


# ── 1. cancelling is a status change, so the decision rule applies ──

def test_a_drafter_cannot_cancel_an_approved_order(ws):
    po = _order(ws["buyer"], ws)
    assert ws["buyer"].patch(f"/orders/{po}", json={"status": "Approved"}).status_code == 200
    r = ws["drafter"].delete(f"/orders/{po}")
    assert (r.status_code, _code(r)) == (403, "DECISION_FORBIDDEN")
    assert ws["buyer"].get(f"/orders/{po}").json()["status"] == "Approved"


def test_a_drafter_cannot_cancel_a_rejected_order(ws):
    po = _order(ws["buyer"], ws)
    assert ws["buyer"].patch(f"/orders/{po}", json={"status": "Rejected", "rejection_note": "no"}).status_code == 200
    r = ws["drafter"].delete(f"/orders/{po}")
    assert (r.status_code, _code(r)) == (403, "DECISION_FORBIDDEN")
    assert ws["buyer"].get(f"/orders/{po}").json()["status"] == "Rejected"


def test_a_drafter_can_still_cancel_an_undecided_order(ws):
    po = _order(ws["buyer"], ws)                                  # Pending
    assert ws["drafter"].delete(f"/orders/{po}").status_code == 204
    assert ws["buyer"].get(f"/orders/{po}").json()["status"] == "Cancelled"


def test_a_decider_cancelling_a_rejected_order_clears_its_rejection_note(ws):
    po = _order(ws["buyer"], ws)
    assert ws["buyer"].patch(f"/orders/{po}", json={"status": "Rejected", "rejection_note": "no"}).status_code == 200
    assert ws["buyer"].delete(f"/orders/{po}").status_code == 204
    o = ws["buyer"].get(f"/orders/{po}").json()
    assert (o["status"], o["rejection_note"]) == ("Cancelled", None)


# ── 2. the order patch takes the same limits as create ──

@pytest.mark.parametrize("field,limit", [
    ("order_number", 50), ("supplier_ref_no", 100), ("product_code", 100),
    ("unit_of_measure", 50), ("location", 255), ("product_website", 500),
])
def test_order_patch_refuses_a_value_longer_than_its_column(ws, field, limit):
    po = _order(ws["buyer"], ws)
    r = ws["buyer"].patch(f"/orders/{po}", json={field: "x" * (limit + 1)})
    assert r.status_code == 422 and field in r.text
    assert ws["buyer"].patch(f"/orders/{po}", json={field: "x" * limit}).status_code == 200


# ── 3. the supplier patch is as strict as create ──

def test_supplier_patch_refuses_an_unknown_status_and_takes_the_four_real_ones(ws):
    for bad in ("Archived", "active", ""):
        r = ws["buyer"].patch(f"/suppliers/{ws['vendor']}", json={"status": bad})
        assert r.status_code == 422 and "status" in r.text, bad
    for good in ("Under Review", "Blacklisted", "Inactive", "Active"):
        assert ws["buyer"].patch(f"/suppliers/{ws['vendor']}", json={"status": good}).status_code == 200


@pytest.mark.parametrize("field,limit", [
    ("contact_name", 255), ("contact_phone", 50), ("tax_id", 100), ("payment_terms", 100),
])
def test_supplier_patch_refuses_a_value_longer_than_its_column(ws, field, limit):
    r = ws["buyer"].patch(f"/suppliers/{ws['vendor']}", json={field: "x" * (limit + 1)})
    assert r.status_code == 422 and field in r.text
    assert ws["buyer"].patch(f"/suppliers/{ws['vendor']}", json={field: "x" * limit}).status_code == 200


# ── 5. a cost centre needs a real code and name ──

def test_cost_centre_refuses_a_blank_code_or_name_and_trims_the_rest(ws):
    c = ws["buyer"]
    assert c.post("/cost-centers", json={"code": "   ", "name": "x"}).status_code == 422
    assert c.post("/cost-centers", json={"code": "OK", "name": "   "}).status_code == 422
    made = c.post("/cost-centers", json={"code": " T1 ", "name": "  Trimmed  "})
    assert made.status_code == 201
    assert (made.json()["code"], made.json()["name"]) == ("T1", "Trimmed")
    cid = made.json()["cost_center_id"]
    assert c.patch(f"/cost-centers/{cid}", json={"code": "  "}).status_code == 422
    assert c.patch(f"/cost-centers/{cid}", json={"name": " "}).status_code == 422
    assert c.patch(f"/cost-centers/{cid}", json={"name": " Renamed "}).json()["name"] == "Renamed"
