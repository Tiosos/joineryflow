"""PO approval (migration 0054, docs/sub-projects/06-orders-procurement.md).

An order needs approval above the workspace limit (default 2000, set by a purchase officer) or when
the project manager flagged it. One approval is enough; purchase officer, manager and admin approve,
never the person who requested it. Approving posts a Commitment against the order's cost centre, if
it has one.
"""
import uuid

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
    buyer, wid, buyer_id = login("purchase_officer", prefix="ap")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    manager, manager_id = login_same_workspace(wid, "manager")
    drafter, _ = login_same_workspace(wid, "drafter")
    return {"wid": wid, "vendor": vendor, "buyer": buyer, "buyer_id": buyer_id,
            "manager": manager, "manager_id": manager_id, "drafter": drafter}


def _order(c, ws, total: str | None = "2500.00") -> dict:
    body = {"vendor_id": ws["vendor"], "description": f"o-{uuid.uuid4().hex[:6]}"}
    if total is not None:
        body["total_amount"] = total
    r = c.post("/orders", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _code(r) -> str:
    return r.json()["detail"]["code"]


# ── What needs approval ──────────────────────────────────────────────────────

def test_needs_approval_above_the_limit_or_when_flagged(ws):
    small = _order(ws["buyer"], ws, "2000.00")   # the limit itself does not need approval
    big = _order(ws["buyer"], ws, "2000.01")
    assert (small["needs_approval"], big["needs_approval"]) == (False, True)

    r = ws["manager"].patch(f"/orders/{small['po_id']}", json={"requires_approval": True})
    assert r.status_code == 200 and r.json()["needs_approval"] is True


def test_only_a_manager_or_admin_sets_the_flag(ws):
    o = _order(ws["buyer"], ws, "10.00")
    for who in ("drafter", "buyer"):
        r = ws[who].patch(f"/orders/{o['po_id']}", json={"requires_approval": True})
        assert (r.status_code, _code(r)) == (403, "APPROVAL_FLAG_FORBIDDEN")
    assert ws["manager"].patch(f"/orders/{o['po_id']}", json={"requires_approval": True}).status_code == 200


def test_the_limit_is_per_workspace_and_a_purchase_officers_to_change(ws):
    assert ws["buyer"].get("/order-settings").json()["approval_threshold"] == "2000"
    r = ws["manager"].put("/order-settings", json={"approval_threshold": "5000"})
    assert (r.status_code, _code(r)) == (403, "APPROVAL_LIMIT_FORBIDDEN")
    assert ws["buyer"].put("/order-settings", json={"approval_threshold": "5000"}).status_code == 200
    assert ws["manager"].get("/order-settings").json()["approval_threshold"] == "5000.00"
    assert ws["buyer"].put("/order-settings", json={"approval_threshold": "-1"}).status_code == 422

    assert _order(ws["buyer"], ws, "2500.00")["needs_approval"] is False
    other, _wid, _uid = login("purchase_officer", prefix="ap2")
    assert other.get("/order-settings").json()["approval_threshold"] == "2000"


# ── The flow ─────────────────────────────────────────────────────────────────

def test_request_then_another_approver_approves(ws):
    o = _order(ws["buyer"], ws)
    r = ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["approval_requested_by"]) == ("Pending", ws["buyer_id"])

    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={"note": "ok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["status"], body["approval_decided_by"], body["approval_note"]) == (
        "Approved", ws["manager_id"], "ok")
    # one approval is enough: nothing is left to decide
    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    assert (r.status_code, _code(r)) == (409, "NOT_PENDING")
    events = _sql("SELECT string_agg(event, ',' ORDER BY id) FROM audit_log WHERE event LIKE 'order.approval%'")
    assert events == "order.approval.request,order.approval.approve"


def test_the_requester_cannot_approve_and_a_drafter_cannot_at_all(ws):
    o = _order(ws["buyer"], ws)
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    r = ws["buyer"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    assert (r.status_code, _code(r)) == (409, "SELF_APPROVAL")
    assert ws["drafter"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 403
    assert ws["drafter"].post(f"/orders/{o['po_id']}/approval/reject", json={"note": "x"}).status_code == 403


def test_reject_needs_a_note_and_can_be_requested_again(ws):
    o = _order(ws["buyer"], ws)
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/reject", json={})
    assert (r.status_code, _code(r)) == (422, "NOTE_REQUIRED")
    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/reject", json={"note": "wrong supplier"})
    assert (r.json()["status"], r.json()["approval_note"]) == ("Rejected", "wrong supplier")

    r = ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["approval_decided_by"], r.json()["approval_note"]) == ("Pending", None, None)


def test_only_a_draft_or_rejected_order_can_be_requested_and_only_if_it_needs_it(ws):
    small = _order(ws["buyer"], ws, "100.00")
    r = ws["buyer"].post(f"/orders/{small['po_id']}/approval/request")
    assert (r.status_code, _code(r)) == (409, "NOT_REQUIRED")
    big = _order(ws["buyer"], ws)
    ws["buyer"].post(f"/orders/{big['po_id']}/approval/request")
    r = ws["buyer"].post(f"/orders/{big['po_id']}/approval/request")
    assert (r.status_code, _code(r), r.json()["detail"]["status"]) == (409, "NOT_REQUESTABLE", "Pending")


# ── A plain status PATCH may not skip it ─────────────────────────────────────

@pytest.mark.parametrize("status", ["Pending", "Approved", "Rejected"])
def test_status_patch_cannot_skip_approval_for_an_order_that_needs_it(ws, status):
    o = _order(ws["buyer"], ws)
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": status})
    assert (r.status_code, _code(r)) == (409, "APPROVAL_ROUTE_REQUIRED")
    assert ws["buyer"].get(f"/orders/{o['po_id']}").json()["status"] == "Draft"


def test_flag_and_status_in_one_patch_cannot_sidestep_it(ws):
    o = _order(ws["buyer"], ws, "10.00")
    r = ws["manager"].patch(f"/orders/{o['po_id']}", json={"requires_approval": True, "status": "Approved"})
    assert (r.status_code, _code(r)) == (409, "APPROVAL_ROUTE_REQUIRED")


def test_an_order_that_does_not_need_approval_keeps_its_free_status(ws):
    o = _order(ws["buyer"], ws, "10.00")
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Approved"})
    assert r.status_code == 200 and r.json()["status"] == "Approved"


# ── Delivered needs the approval too ─────────────────────────────────────────

def test_an_order_that_needs_approval_is_delivered_only_once_approved(ws):
    o = _order(ws["buyer"], ws)
    pid = o["po_id"]

    def deliver():
        return ws["buyer"].patch(f"/orders/{pid}", json={"status": "Delivered"})

    for step in ("Draft", "Pending", "Rejected"):
        if step == "Pending":
            assert ws["buyer"].post(f"/orders/{pid}/approval/request").status_code == 200
        if step == "Rejected":
            r = ws["manager"].post(f"/orders/{pid}/approval/reject", json={"note": "no"})
            assert r.status_code == 200, r.text
        r = deliver()
        assert (r.status_code, _code(r)) == (409, "APPROVAL_REQUIRED"), step
        assert r.json()["detail"]["status"] == step
        assert ws["buyer"].get(f"/orders/{pid}").json()["status"] == step

    assert ws["buyer"].post(f"/orders/{pid}/approval/request").status_code == 200
    assert ws["manager"].post(f"/orders/{pid}/approval/approve", json={}).status_code == 200
    r = deliver()
    assert r.status_code == 200 and r.json()["status"] == "Delivered"


def test_the_flag_and_delivered_in_one_patch_cannot_sidestep_it(ws):
    o = _order(ws["buyer"], ws, "10.00")
    r = ws["manager"].patch(f"/orders/{o['po_id']}", json={"requires_approval": True, "status": "Delivered"})
    assert (r.status_code, _code(r)) == (409, "APPROVAL_REQUIRED")


def test_an_order_that_does_not_need_approval_is_delivered_freely(ws):
    o = _order(ws["buyer"], ws, "10.00")
    r = ws["buyer"].patch(f"/orders/{o['po_id']}", json={"status": "Delivered"})
    assert r.status_code == 200 and r.json()["status"] == "Delivered"


# ── Budget commitment ────────────────────────────────────────────────────────

def _cost_centre(wid: int, code: str = "GEN") -> int:
    return _sql("INSERT INTO cost_centers(workspace_id, code, name, fiscal_year, budget_amount)"
                " VALUES (:w, :c, 'General', 2026, 50000) RETURNING cost_center_id", w=wid, c=code)


def test_approving_posts_a_commitment_when_the_order_has_a_cost_centre(ws):
    o = _order(ws["buyer"], ws, "2500.00")
    cc = _cost_centre(ws["wid"])
    _sql("UPDATE purchase_orders SET cost_center_id = :c WHERE po_id = :o", c=cc, o=o["po_id"])
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    rows = _sql("SELECT count(*) || ':' || sum(amount) FROM budget_transactions"
                " WHERE po_id = :o AND transaction_type = 'Commitment' AND cost_center_id = :c",
                o=o["po_id"], c=cc)
    assert rows == "1:2500.00"


def test_approving_without_a_cost_centre_just_skips_the_commitment(ws):
    o = _order(ws["buyer"], ws, "2500.00")
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    r = ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={})
    assert r.status_code == 200 and r.json()["status"] == "Approved"
    assert _sql("SELECT count(*) FROM budget_transactions WHERE po_id = :o", o=o["po_id"]) == 0


def test_rejecting_posts_no_commitment(ws):
    o = _order(ws["buyer"], ws, "2500.00")
    _sql("UPDATE purchase_orders SET cost_center_id = :c WHERE po_id = :o",
         c=_cost_centre(ws["wid"]), o=o["po_id"])
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    ws["manager"].post(f"/orders/{o['po_id']}/approval/reject", json={"note": "no"})
    assert _sql("SELECT count(*) FROM budget_transactions WHERE po_id = :o", o=o["po_id"]) == 0
