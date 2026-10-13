"""Orders waiting for a decision show in the purchase officer's notification list.

The customer's choices: only the purchase officer role is told (not every holder of
`orderbook:approve`); an order counts while it is `Pending` (new, or moved back to Pending); it
drops out once decided or cancelled. Nothing is stored, so there is nothing to mark read.
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace

_cleanup = truncate_fixture("budget_transactions", "cost_centers", "purchase_orders", "vendors")


def _vendor(wid: int) -> int:
    s = SessionLocal()
    try:
        v = s.execute(text("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                           " RETURNING vendor_id"), {"w": wid}).scalar()
        s.commit()
        return v
    finally:
        s.close()


@pytest.fixture
def ws():
    buyer, wid, uid = login("purchase_officer", prefix="ow")
    vendor = _vendor(wid)
    drafter, _ = login_same_workspace(wid, "drafter")
    manager, _ = login_same_workspace(wid, "manager")
    return {"wid": wid, "uid": uid, "vendor": vendor, "buyer": buyer, "drafter": drafter,
            "manager": manager}


def _order(c, ws, desc="waiting order"):
    r = c.post("/orders", json={"vendor_id": ws["vendor"], "description": desc, "total_amount": "10.00"})
    assert r.status_code == 201, r.text
    return r.json()


def _waiting(c):
    r = c.get("/notifications")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_new_order_is_waiting_for_the_purchase_officer_only(ws):
    o = _order(ws["drafter"], ws)
    body = _waiting(ws["buyer"])
    assert body["orders_waiting_count"] == 1
    row = body["orders_waiting"][0]
    assert (row["po_id"], row["po_number"]) == (o["po_id"], o["po_number"])
    assert row["url"].startswith("/orderbook?order=PO-")
    # a manager and a drafter can decide / raise, but the list is the purchase officer's
    for other in ("manager", "drafter"):
        body = _waiting(ws[other])
        assert "orders_waiting" not in body and "orders_waiting_count" not in body


@pytest.mark.parametrize("decision", [
    {"status": "Approved"},
    {"status": "Rejected", "rejection_note": "no"},
    {"status": "Cancelled"},
])
def test_a_decided_or_cancelled_order_leaves_the_list(ws, decision):
    o = _order(ws["drafter"], ws)
    assert _waiting(ws["buyer"])["orders_waiting_count"] == 1
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json=decision).status_code == 200
    body = _waiting(ws["buyer"])
    assert (body["orders_waiting_count"], body["orders_waiting"]) == (0, [])


def test_an_order_moved_back_to_pending_comes_back(ws):
    o = _order(ws["drafter"], ws)
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Approved"})
    assert _waiting(ws["buyer"])["orders_waiting_count"] == 0
    assert ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Pending"}).status_code == 200
    assert _waiting(ws["buyer"])["orders_waiting_count"] == 1


def test_a_draft_order_is_not_waiting(ws):
    o = _order(ws["drafter"], ws)
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Draft"})
    assert _waiting(ws["buyer"])["orders_waiting_count"] == 0


def test_the_list_is_newest_first_capped_at_twenty_and_counts_them_all(ws):
    ids = [_order(ws["drafter"], ws, f"o{i}")["po_id"] for i in range(22)]
    body = _waiting(ws["buyer"])
    assert body["orders_waiting_count"] == 22
    assert [r["po_id"] for r in body["orders_waiting"]] == ids[::-1][:20]


def test_another_workspaces_pending_orders_are_not_counted(ws):
    _order(ws["drafter"], ws)
    other, owid, _ = login("purchase_officer", prefix="ox")
    assert _waiting(other)["orders_waiting_count"] == 0
    assert owid != ws["wid"]


# ── the list is only worked out for the calls that use it ──

def test_paged_and_unread_only_calls_carry_no_waiting_orders(ws):
    _order(ws["drafter"], ws)
    assert _waiting(ws["buyer"])["orders_waiting_count"] == 1
    for params in ({"unread_only": True}, {"offset": 1}):
        body = ws["buyer"].get("/notifications", params=params).json()
        assert "orders_waiting" not in body and "orders_waiting_count" not in body


# ── the officer must still be able to read the Orderbook ──

def _only_grants(ws, grants):
    """Make the purchase officer DB-governed with only `grants` (module, action); returns group id."""
    s = SessionLocal()
    try:
        gid = s.execute(text("INSERT INTO permission_group(workspace_id, name, is_system)"
                             " VALUES (:w, 'only-ow', false) RETURNING group_id"),
                        {"w": ws["wid"]}).scalar()
        for module, action in grants:
            s.execute(text("INSERT INTO group_module_grant(group_id, module, action)"
                           " VALUES (:g, :m, :a)"), {"g": gid, "m": module, "a": action})
        s.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                       " VALUES (:u, :g, NULL)"), {"u": ws["uid"], "g": gid})
        s.commit()
        return gid
    finally:
        s.close()


def test_an_officer_who_cannot_read_the_orderbook_is_told_nothing(ws):
    _order(ws["drafter"], ws)
    _only_grants(ws, [("orderbook", "read")])
    assert _waiting(ws["buyer"])["orders_waiting_count"] == 1
    s = SessionLocal()
    try:
        s.execute(text("DELETE FROM group_module_grant WHERE module = 'orderbook' AND group_id IN"
                       " (SELECT group_id FROM permission_group WHERE name = 'only-ow'"
                       " AND workspace_id = :w)"), {"w": ws["wid"]})
        s.commit()
    finally:
        s.close()
    body = _waiting(ws["buyer"])
    assert "orders_waiting" not in body and "orders_waiting_count" not in body
