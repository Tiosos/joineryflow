"""An approved order whose total is raised goes back for approval (migration 0055).

"Raised" = above what was approved (`approved_total`); for an order approved freely that a rise takes
over the limit, above its previous total. The editor becomes the requester, so someone else approves
the new figure, and the budget Commitment is topped up rather than doubled.
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
    buyer, wid, buyer_id = login("purchase_officer", prefix="ra")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    manager, manager_id = login_same_workspace(wid, "manager")
    cc = buyer.post("/cost-centers", json={"code": "GEN", "name": "General"}).json()["cost_center_id"]
    return {"vendor": vendor, "buyer": buyer, "buyer_id": buyer_id, "manager": manager,
            "manager_id": manager_id, "cc": cc}


def _approved(ws, total="3000.00", with_cc=False) -> dict:
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "o", "total_amount": total}).json()
    if with_cc:
        ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": ws["cc"]})
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["approved_total"] == total
    return r.json()


def _get(ws, po_id):
    return ws["buyer"].get(f"/orders/{po_id}").json()


def test_raising_the_total_of_an_approved_order_sends_it_back(ws):
    o = _approved(ws)
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"total_amount": "3200.00"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Pending"
    assert (body["approval_requested_by"], body["approval_decided_by"]) == (ws["buyer_id"], None)
    assert "3000" in body["approval_note"] and "3200" in body["approval_note"]
    events = _sql("SELECT string_agg(event, ',' ORDER BY id) FROM audit_log WHERE event = 'order.approval.reopened'")
    assert events == "order.approval.reopened"


def test_the_person_who_raised_it_cannot_approve_it_again(ws):
    o = _approved(ws)
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"total_amount": "3200.00"})
    r = ws["buyer"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "SELF_APPROVAL")
    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    assert (r.json()["status"], r.json()["approved_total"]) == ("Approved", "3200.00")


def test_a_fall_or_a_rise_within_what_was_approved_leaves_it_approved(ws):
    o = _approved(ws, "3000.00")
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"total_amount": "2500.00"}).json()["status"] == "Approved"
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"total_amount": "3000.00"}).json()["status"] == "Approved"


def test_raising_through_a_line_sends_it_back_and_the_commitment_is_topped_up(ws):
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "lines"}).json()
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": ws["cc"]})
    r = ws["buyer"].post(f"/orders/{o['po_id']}/lines", json={"item_description": "A", "quantity": "1", "unit_price": "3000"})
    assert r.status_code == 201, r.text
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200

    r = ws["buyer"].post(f"/orders/{o['po_id']}/lines", json={"item_description": "B", "quantity": "1", "unit_price": "500"})
    assert r.status_code == 201 and r.json()["status"] == "Pending" and r.json()["total_amount"] == "3500.00"
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200

    ledger = _sql("SELECT string_agg(transaction_type || ':' || amount, ',' ORDER BY transaction_id)"
                  " FROM budget_transactions WHERE po_id = :o", o=o["po_id"])
    assert ledger == "Commitment:3000.00,Commitment:500.00"   # topped up, not doubled


def test_a_free_approval_that_a_rise_takes_over_the_limit_needs_one_now(ws):
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "s", "total_amount": "1500.00"}).json()
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Approved"}).json()["status"] == "Approved"
    # still under the limit: nothing happens
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"total_amount": "1800.00"}).json()["status"] == "Approved"
    # over it: back for approval
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"total_amount": "2600.00"})
    assert (r.json()["status"], r.json()["needs_approval"]) == ("Pending", True)


def test_a_pending_order_stays_pending_and_keeps_its_requester(ws):
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "p", "total_amount": "2500.00"}).json()
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    r = ws["manager"].patch(f"/orders/{o['po_id']}", json={"total_amount": "9000.00"})
    assert (r.json()["status"], r.json()["approval_requested_by"]) == ("Pending", ws["buyer_id"])
