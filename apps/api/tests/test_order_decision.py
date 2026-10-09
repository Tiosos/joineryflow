"""An order is added as Pending; a purchase officer decides it (migration 0056).

There is no approval process in the software: whoever adds an order in the Orderbook leaves it
`Pending`, and a purchase officer (or a manager / admin: the `orderbook:approve` grant) sets
`Approved` or `Rejected` by hand after their own review. Any sign-off from a manager or admin
happens outside the software. Rejecting needs a reason (`rejection_note`). An order commits its
total against its cost centre while it is Approved, and the commitment follows the order.
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
    buyer, wid, _uid = login("purchase_officer", prefix="dc")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                  " RETURNING vendor_id", w=wid)
    manager, _ = login_same_workspace(wid, "manager")
    admin, _ = login_same_workspace(wid, "admin")
    drafter, _ = login_same_workspace(wid, "drafter")
    cc = buyer.post("/cost-centers", json={"code": "GEN", "name": "General", "budget_amount": "9000"}).json()
    return {"wid": wid, "vendor": vendor, "buyer": buyer, "manager": manager, "admin": admin,
            "drafter": drafter, "cc": cc["cost_center_id"]}


def _order(c, ws, total="2500.00", cost_centre=True) -> dict:
    r = c.post("/orders", json={"vendor_id": ws["vendor"], "description": "o", "total_amount": total})
    assert r.status_code == 201, r.text
    o = r.json()
    if cost_centre:
        assert c.patch(f"/orders/{o['po_id']}", json={"cost_center_id": ws["cc"]}).status_code == 200
    return o


def _code(r) -> str:
    return r.json()["detail"]["code"]


def _set(c, po, **body):
    return c.patch(f"/orders/{po}", json=body)


# ── Where an order starts and who decides ────────────────────────────────────

def test_an_order_added_in_the_orderbook_starts_pending(ws):
    for who in ("buyer", "drafter", "manager"):
        o = ws[who].post("/orders", json={"vendor_id": ws["vendor"], "description": "x"}).json()
        assert o["status"] == "Pending", who


def test_the_old_approval_surface_is_gone(ws):
    o = _order(ws["buyer"], ws)
    for method, path in (("post", f"/orders/{o['po_id']}/approval/request"),
                         ("post", f"/orders/{o['po_id']}/approval/approve"),
                         ("post", f"/orders/{o['po_id']}/approval/reject"),
                         ("get", "/order-settings"), ("put", "/order-settings")):
        assert getattr(ws["buyer"], method)(path).status_code in (404, 405), path
    body = ws["buyer"].get(f"/orders/{o['po_id']}").json()
    for gone in ("needs_approval", "requires_approval", "approved_total", "approval_note",
                 "approval_requested_by", "approval_decided_by"):
        assert gone not in body, gone
    assert body["rejection_note"] is None


@pytest.mark.parametrize("who", ["buyer", "manager", "admin"])
def test_purchase_officer_manager_and_admin_can_approve_or_reject(ws, who):
    a = _order(ws[who], ws, cost_centre=False)
    assert _set(ws[who], a["po_id"], status="Approved").json()["status"] == "Approved"
    b = _order(ws[who], ws, cost_centre=False)
    r = _set(ws[who], b["po_id"], status="Rejected", rejection_note="Wrong supplier")
    assert (r.status_code, r.json()["status"]) == (200, "Rejected")


def test_a_drafter_cannot_decide_an_order_or_undo_a_decision(ws):
    o = _order(ws["drafter"], ws, cost_centre=False)
    for status in ("Approved", "Rejected"):
        r = _set(ws["drafter"], o["po_id"], status=status, rejection_note="x")
        assert (r.status_code, _code(r)) == (403, "DECISION_FORBIDDEN"), status
    assert ws["drafter"].get(f"/orders/{o['po_id']}").json()["status"] == "Pending"
    # everything else about the order is still theirs to edit
    assert _set(ws["drafter"], o["po_id"], status="Hold", notes="waiting").status_code == 200
    # ... but moving a decided order out of its decision is a decider's
    assert _set(ws["buyer"], o["po_id"], status="Approved").status_code == 200
    r = _set(ws["drafter"], o["po_id"], status="Hold")
    assert (r.status_code, _code(r)) == (403, "DECISION_FORBIDDEN")


def test_size_makes_no_difference_and_delivery_needs_no_approval(ws):
    big = _order(ws["buyer"], ws, "50000.00", cost_centre=False)
    assert _set(ws["buyer"], big["po_id"], status="Delivered").status_code == 200   # still Pending
    other = _order(ws["buyer"], ws, "50000.00", cost_centre=False)
    assert _set(ws["manager"], other["po_id"], status="Approved").status_code == 200


# ── The rejection note ───────────────────────────────────────────────────────

def test_rejecting_needs_a_reason_which_stays_on_the_order(ws):
    o = _order(ws["buyer"], ws, cost_centre=False)
    for body in ({"status": "Rejected"}, {"status": "Rejected", "rejection_note": "   "}):
        r = _set(ws["buyer"], o["po_id"], **body)
        assert (r.status_code, _code(r)) == (409, "REJECTION_NOTE_REQUIRED"), body
    assert ws["buyer"].get(f"/orders/{o['po_id']}").json()["status"] == "Pending"

    r = _set(ws["buyer"], o["po_id"], status="Rejected", rejection_note="  Over our price list ")
    assert (r.json()["status"], r.json()["rejection_note"]) == ("Rejected", "Over our price list")
    # the reason can be corrected while it is Rejected, but not emptied
    assert _set(ws["buyer"], o["po_id"], rejection_note="Wrong supplier").json()["rejection_note"] == "Wrong supplier"
    assert _code(_set(ws["buyer"], o["po_id"], rejection_note="")) == "REJECTION_NOTE_REQUIRED"
    # a decision is audited with who made it
    assert _sql("SELECT count(*) FROM audit_log WHERE event = 'order.update' AND target = :t",
                t=str(o["po_id"])) >= 2


def test_the_note_goes_when_the_order_leaves_rejected_and_is_refused_elsewhere(ws):
    o = _order(ws["buyer"], ws, cost_centre=False)
    _set(ws["buyer"], o["po_id"], status="Rejected", rejection_note="No")
    back = _set(ws["buyer"], o["po_id"], status="Pending")
    assert (back.status_code, back.json()["status"], back.json()["rejection_note"]) == (200, "Pending", None)
    r = _set(ws["buyer"], o["po_id"], status="Hold", rejection_note="No")
    assert (r.status_code, _code(r)) == (409, "REJECTION_NOTE_NOT_APPLICABLE")
    r = _set(ws["buyer"], o["po_id"], notes="just a note", rejection_note="No")
    assert (r.status_code, _code(r)) == (409, "REJECTION_NOTE_NOT_APPLICABLE")


# ── The commitment follows the order ─────────────────────────────────────────

def test_approving_commits_the_total_and_only_while_approved(ws):
    o = _order(ws["buyer"], ws)
    po = o["po_id"]
    assert _ledger(po) == []                              # Pending holds no budget
    _set(ws["manager"], po, status="Approved")
    assert _ledger(po) == [("Commitment", "2500.00")]
    _set(ws["buyer"], po, status="Hold")                  # leaving Approved releases it
    assert _ledger(po) == [("Commitment", "2500.00"), ("Release", "-2500.00")]
    _set(ws["buyer"], po, status="Approved")              # and approving again commits again
    assert _ledger(po)[-1] == ("Commitment", "2500.00")
    _set(ws["buyer"], po, status="Rejected", rejection_note="changed our minds")
    assert sum(float(a) for _t, a in _ledger(po)) == 0.0


def test_editing_the_total_of_an_approved_order_moves_the_commitment(ws):
    po = _order(ws["buyer"], ws)["po_id"]
    _set(ws["buyer"], po, status="Approved")
    _set(ws["buyer"], po, total_amount="3000.00")         # a header-only order: total set directly
    _set(ws["buyer"], po, total_amount="2800.00")
    assert _ledger(po) == [("Commitment", "2500.00"), ("Commitment", "500.00"), ("Release", "-200.00")]
    assert _sql("SELECT sum(amount)::text FROM budget_transactions WHERE po_id = :o", o=po) == "2800.00"


def test_line_edits_on_an_approved_order_move_the_commitment_too(ws):
    po = _order(ws["buyer"], ws, "0", )["po_id"]
    line = ws["buyer"].post(f"/orders/{po}/lines", json={
        "item_description": "Board", "quantity": "10", "unit_price": "100.00"}).json()["lines"][0]
    _set(ws["manager"], po, status="Approved")
    assert _ledger(po) == [("Commitment", "1000.00")]
    ws["buyer"].post(f"/orders/{po}/lines", json={"item_description": "Edge", "quantity": "5", "unit_price": "20.00"})
    assert _sql("SELECT sum(amount)::text FROM budget_transactions WHERE po_id = :o", o=po) == "1100.00"
    ws["buyer"].delete(f"/orders/{po}/lines/{line['line_id']}")
    assert _sql("SELECT sum(amount)::text FROM budget_transactions WHERE po_id = :o", o=po) == "100.00"


def test_a_pending_order_posts_nothing_when_edited(ws):
    po = _order(ws["buyer"], ws)["po_id"]
    _set(ws["buyer"], po, total_amount="9999.00")
    assert _ledger(po) == []


def test_choosing_the_cost_centre_after_approval_commits_then(ws):
    po = _order(ws["buyer"], ws, cost_centre=False)["po_id"]
    _set(ws["manager"], po, status="Approved")
    assert _ledger(po) == []                              # no cost centre: nothing to commit against
    _set(ws["buyer"], po, cost_center_id=ws["cc"])
    assert _ledger(po) == [("Commitment", "2500.00")]


def test_reopening_a_delivered_order_does_not_count_its_money_twice(ws):
    po = _order(ws["buyer"], ws)["po_id"]
    _set(ws["buyer"], po, status="Approved")
    _set(ws["buyer"], po, status="Delivered")
    before = _ledger(po)
    assert [t for t, _ in before] == ["Commitment", "Expenditure", "Release"]
    _set(ws["buyer"], po, status="Approved")              # reopened: its spend is already booked
    assert _ledger(po) == before


def test_reopening_a_cancelled_order_to_approved_commits_it_again(ws):
    po = _order(ws["buyer"], ws)["po_id"]
    _set(ws["buyer"], po, status="Approved")
    assert ws["buyer"].delete(f"/orders/{po}").status_code == 204
    assert sum(float(a) for _t, a in _ledger(po)) == 0.0
    _set(ws["buyer"], po, status="Approved")
    assert sum(float(a) for _t, a in _ledger(po)) == 2500.0
