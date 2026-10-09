"""Cost centres, in very small scale: list + create, and one optional field on an order.

An approval's budget Commitment is posted against the order's cost centre (migration 0054 /
docs/sub-projects/06-orders-procurement.md); an order needs none (Q563).
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
    buyer, wid, buyer_id = login("purchase_officer", prefix="cc")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    manager, _ = login_same_workspace(wid, "manager")
    return {"wid": wid, "vendor": vendor, "buyer": buyer, "manager": manager}


def _order(c, ws, total="2500.00"):
    r = c.post("/orders", json={"vendor_id": ws["vendor"], "description": "o", "total_amount": total})
    assert r.status_code == 201, r.text
    return r.json()


def _make(c, code="GEN", name="General", budget="1000"):
    r = c.post("/cost-centers", json={"code": code, "name": name, "budget_amount": budget})
    assert r.status_code == 201, r.text
    return r.json()


def test_a_purchase_officer_adds_cost_centres_and_everyone_with_read_lists_them(ws):
    cc = _make(ws["buyer"])
    assert (cc["code"], cc["name"]) == ("GEN", "General")
    assert [c["code"] for c in ws["manager"].get("/cost-centers").json()["cost_centers"]] == ["GEN"]
    r = ws["manager"].post("/cost-centers", json={"code": "X", "name": "X"})
    assert (r.status_code, r.json()["detail"]["code"]) == (403, "COST_CENTRE_FORBIDDEN")


def test_a_code_is_unique_per_workspace_and_the_list_is_per_workspace(ws):
    _make(ws["buyer"])
    r = ws["buyer"].post("/cost-centers", json={"code": "GEN", "name": "Again"})
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "COST_CENTRE_EXISTS")
    other, _wid, _uid = login("purchase_officer", prefix="cc2")
    assert other.get("/cost-centers").json()["cost_centers"] == []
    assert _make(other)["code"] == "GEN"  # the same code in another workspace is fine


def test_an_order_takes_an_optional_cost_centre(ws):
    cc = _make(ws["buyer"])
    o = _order(ws["buyer"], ws)
    assert o["cost_center_id"] is None
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    assert r.status_code == 200, r.text
    assert (r.json()["cost_center_code"], r.json()["cost_center_name"]) == ("GEN", "General")
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": None})
    assert r.status_code == 200 and r.json()["cost_center_id"] is None


def test_another_workspaces_or_an_inactive_cost_centre_is_not_found(ws):
    other, _wid, _uid = login("purchase_officer", prefix="cc3")
    theirs = _make(other)
    o = _order(ws["buyer"], ws)
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": theirs["cost_center_id"]})
    assert (r.status_code, r.json()["detail"]["code"]) == (404, "COST_CENTER_NOT_FOUND")
    mine = _make(ws["buyer"], code="OLD")
    _sql("UPDATE cost_centers SET is_active = false WHERE cost_center_id = :c", c=mine["cost_center_id"])
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": mine["cost_center_id"]})
    assert r.status_code == 404


def test_approving_commits_against_the_chosen_cost_centre_and_then_it_cannot_move(ws):
    cc = _make(ws["buyer"])
    other_cc = _make(ws["buyer"], code="SPARE")
    o = _order(ws["buyer"], ws, "2500.00")
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200
    committed = _sql("SELECT count(*) || ':' || sum(amount) || ':' || min(cost_center_id) FROM budget_transactions"
                     " WHERE po_id = :o AND transaction_type = 'Commitment'", o=o["po_id"])
    assert committed == f"1:2500.00:{cc['cost_center_id']}"

    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": other_cc["cost_center_id"]})
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "COST_CENTER_LOCKED")
    # setting it to what it already is is not a move
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]}).status_code == 200
