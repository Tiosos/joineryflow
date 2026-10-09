"""An order that is cancelled or delivered gives its budget Commitment back (orders/budget.py).

The ledger is `budget_transactions`; `v_budget_utilisation` sums Commitment, Expenditure and Release
(a Release is negative). Cancelled: release the outstanding Commitment. Delivered: post the order's
total as an Expenditure and release the Commitment. Both need a cost centre; an order has none
until someone picks one (Q563).
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


def _ledger(po_id: int) -> list[tuple[str, str]]:
    s = SessionLocal()
    try:
        rows = s.execute(
            text("SELECT transaction_type, amount::text FROM budget_transactions"
                 " WHERE po_id = :o ORDER BY transaction_id"), {"o": po_id}).all()
        return [(t, a) for t, a in rows]
    finally:
        s.close()


@pytest.fixture
def ws():
    buyer, wid, _uid = login("purchase_officer", prefix="bd")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    manager, _ = login_same_workspace(wid, "manager")
    cc = buyer.post("/cost-centers", json={"code": "GEN", "name": "General", "budget_amount": "9000"}).json()
    return {"wid": wid, "vendor": vendor, "buyer": buyer, "manager": manager, "cc": cc["cost_center_id"]}


def _approved_order(ws, total="2500.00", cost_centre=True) -> int:
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "o", "total_amount": total}).json()
    if cost_centre:
        ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": ws["cc"]})
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200
    return o["po_id"]


def test_cancelling_releases_the_commitment(ws):
    po = _approved_order(ws)
    assert ws["buyer"].delete(f"/orders/{po}").status_code == 204
    assert _ledger(po) == [("Commitment", "2500.00"), ("Release", "-2500.00")]
    assert ws["buyer"].delete(f"/orders/{po}").status_code == 409  # already cancelled
    assert len(_ledger(po)) == 2, "a second cancel posts nothing"


def test_a_status_change_to_cancelled_releases_it_too(ws):
    po = _approved_order(ws)
    assert ws["buyer"].patch(f"/orders/{po}", json={"status": "Cancelled"}).status_code == 200
    assert _ledger(po) == [("Commitment", "2500.00"), ("Release", "-2500.00")]


def test_delivery_turns_the_commitment_into_an_expenditure(ws):
    po = _approved_order(ws)
    assert ws["buyer"].patch(f"/orders/{po}", json={"status": "Delivered"}).status_code == 200
    assert _ledger(po) == [("Commitment", "2500.00"), ("Expenditure", "2500.00"), ("Release", "-2500.00")]
    # the view counts it once
    used = _sql("SELECT total_committed::text FROM v_budget_utilisation WHERE cost_center_id = :c", c=ws["cc"])
    assert used == "2500.00"


def test_delivering_again_after_a_reopen_does_not_double_count(ws):
    po = _approved_order(ws)
    ws["buyer"].patch(f"/orders/{po}", json={"status": "Delivered"})
    ws["buyer"].patch(f"/orders/{po}", json={"status": "Hold"})
    ws["buyer"].patch(f"/orders/{po}", json={"status": "Delivered"})
    assert [t for t, _ in _ledger(po)] == ["Commitment", "Expenditure", "Release"]


def test_the_expenditure_is_the_total_at_delivery(ws):
    po = _approved_order(ws, "2500.00")
    ws["buyer"].patch(f"/orders/{po}", json={"total_amount": "2300.00"})
    ws["buyer"].patch(f"/orders/{po}", json={"status": "Delivered"})
    # what was committed is released; what was spent is the delivered total
    assert _ledger(po) == [("Commitment", "2500.00"), ("Expenditure", "2300.00"), ("Release", "-2500.00")]


def test_an_order_with_a_cost_centre_but_no_approval_gets_only_the_expenditure(ws):
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "small", "total_amount": "300.00"}).json()
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": ws["cc"]})
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Delivered"})
    assert _ledger(o["po_id"]) == [("Expenditure", "300.00")]


def test_nothing_is_posted_without_a_cost_centre_or_a_commitment(ws):
    po = _approved_order(ws, cost_centre=False)
    ws["buyer"].patch(f"/orders/{po}", json={"status": "Delivered"})
    assert _ledger(po) == []
    o = ws["buyer"].post("/orders", json={"vendor_id": ws["vendor"], "description": "x", "total_amount": "10"}).json()
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": ws["cc"]})
    ws["buyer"].delete(f"/orders/{o['po_id']}")  # cancelled with nothing committed
    assert _ledger(o["po_id"]) == []
