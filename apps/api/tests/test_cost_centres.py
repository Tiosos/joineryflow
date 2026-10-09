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


# ── Rename and deactivate ────────────────────────────────────────────────────

def _patch(c, cc, **body):
    return c.patch(f"/cost-centers/{cc['cost_center_id']}", json=body)


def test_a_purchase_officer_renames_a_cost_centre_and_orders_show_the_new_name(ws):
    cc = _make(ws["buyer"], code="GNR", name="Genral")   # a typo
    o = _order(ws["buyer"], ws)
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    r = _patch(ws["buyer"], cc, code="GEN", name="General")
    assert r.status_code == 200, r.text
    assert (r.json()["code"], r.json()["name"], r.json()["is_active"]) == ("GEN", "General", True)
    got = ws["buyer"].get(f"/orders/{o['po_id']}").json()
    assert (got["cost_center_id"], got["cost_center_code"], got["cost_center_name"]) == (
        cc["cost_center_id"], "GEN", "General")
    r = ws["manager"].patch(f"/cost-centers/{cc['cost_center_id']}", json={"name": "X"})
    assert (r.status_code, r.json()["detail"]["code"]) == (403, "COST_CENTRE_FORBIDDEN")


def test_a_rename_cannot_take_a_code_already_used_in_the_workspace(ws):
    a = _make(ws["buyer"], code="A")
    _make(ws["buyer"], code="B")
    r = _patch(ws["buyer"], a, code="B")
    assert (r.status_code, r.json()["detail"]["code"]) == (409, "COST_CENTRE_EXISTS")
    assert _patch(ws["buyer"], a, code="A", name="Same code, new name").status_code == 200  # its own code is fine


def test_a_rename_is_allowed_after_budget_rows_are_posted(ws):
    cc = _make(ws["buyer"])
    o = _order(ws["buyer"], ws, "2500.00")
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200
    assert _sql("SELECT count(*) FROM budget_transactions WHERE po_id = :o", o=o["po_id"]) == 1
    assert _patch(ws["buyer"], cc, name="Renamed").status_code == 200


def test_deactivating_hides_it_from_new_orders_but_leaves_the_orders_that_use_it(ws):
    cc = _make(ws["buyer"])
    o = _order(ws["buyer"], ws, "2500.00")
    other = _order(ws["buyer"], ws)
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    ws["buyer"].post(f"/orders/{o['po_id']}/approval/request")
    assert _patch(ws["buyer"], cc, is_active=False).json()["is_active"] is False

    # the list still carries it (so it can be switched back on), marked inactive
    listed = ws["manager"].get("/cost-centers").json()["cost_centers"]
    assert [(c["code"], c["is_active"]) for c in listed] == [("GEN", False)]
    # it cannot be chosen on another order ...
    r = ws["buyer"].patch(f"/orders/{other['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    assert (r.status_code, r.json()["detail"]["code"]) == (404, "COST_CENTER_NOT_FOUND")
    # ... but the order that already has it keeps it, and its approval still commits against it
    assert ws["buyer"].get(f"/orders/{o['po_id']}").json()["cost_center_code"] == "GEN"
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200
    assert _sql("SELECT min(cost_center_id) FROM budget_transactions WHERE po_id = :o", o=o["po_id"]) \
        == cc["cost_center_id"]

    assert _patch(ws["buyer"], cc, is_active=True).json()["is_active"] is True
    assert ws["buyer"].patch(f"/orders/{other['po_id']}",
                             json={"cost_center_id": cc["cost_center_id"]}).status_code == 200


def test_cost_centre_patch_refuses_nulls_unknown_and_other_workspaces_ids(ws):
    cc = _make(ws["buyer"])
    for field in ("code", "name", "is_active"):
        r = _patch(ws["buyer"], cc, **{field: None})
        assert r.status_code == 422 and field in r.text, field
    assert _patch(ws["buyer"], cc, code="").status_code == 422
    other, _wid, _uid = login("purchase_officer", prefix="cc4")
    theirs = _make(other)
    r_foreign = ws["buyer"].patch(f"/cost-centers/{theirs['cost_center_id']}", json={"name": "Mine now"})
    r_ghost = ws["buyer"].patch("/cost-centers/99999999", json={"name": "Mine now"})
    assert (r_foreign.status_code, r_foreign.json()) == (r_ghost.status_code, r_ghost.json()) == (
        404, {"detail": "cost centre not found"})
    assert other.get("/cost-centers").json()["cost_centers"][0]["name"] == "General"
    # an edit is audited with what it changed
    assert _patch(ws["buyer"], cc, name="Audited").status_code == 200
    assert _sql("SELECT count(*) FROM audit_log WHERE event = 'cost_centre.update'") == 1


# ── Budget figures (information only) ────────────────────────────────────────

def _approved_on(ws, cc, total):
    o = _order(ws["buyer"], ws, total)
    ws["buyer"].patch(f"/orders/{o['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    assert ws["buyer"].post(f"/orders/{o['po_id']}/approval/request").status_code == 200
    assert ws["manager"].post(f"/orders/{o['po_id']}/approval/approve", json={}).status_code == 200
    return o["po_id"]


def _figures(c, code="GEN"):
    row = next(x for x in c.get("/cost-centers").json()["cost_centers"] if x["code"] == code)
    return tuple(row[k] for k in ("budget_amount", "committed", "spent", "remaining"))


def test_figures_follow_the_ledger_through_approve_deliver_and_cancel(ws):
    cc = _make(ws["buyer"], budget="10000")
    assert _figures(ws["manager"]) == ("10000.00", "0.00", "0.00", "10000.00")   # a reader sees them too

    a = _approved_on(ws, cc, "2500.00")          # approving commits the order's total
    assert _figures(ws["manager"]) == ("10000.00", "2500.00", "0.00", "7500.00")

    small = _order(ws["buyer"], ws, "300.00")    # needs no approval: only the cost is booked
    ws["buyer"].patch(f"/orders/{small['po_id']}", json={"cost_center_id": cc["cost_center_id"]})
    assert ws["buyer"].patch(f"/orders/{small['po_id']}", json={"status": "Delivered"}).status_code == 200
    assert _figures(ws["manager"]) == ("10000.00", "2500.00", "300.00", "7200.00")

    # delivering the approved one turns its commitment into spend, counted once
    assert ws["buyer"].patch(f"/orders/{a}", json={"status": "Delivered"}).status_code == 200
    assert _figures(ws["manager"]) == ("10000.00", "0.00", "2800.00", "7200.00")

    b = _approved_on(ws, cc, "2100.00")          # cancelling releases what it held
    assert _figures(ws["manager"])[1:] == ("2100.00", "2800.00", "5100.00")
    assert ws["buyer"].delete(f"/orders/{b}").status_code == 204
    assert _figures(ws["manager"]) == ("10000.00", "0.00", "2800.00", "7200.00")


def test_going_over_budget_is_shown_as_a_negative_remainder_and_blocks_nothing(ws):
    cc = _make(ws["buyer"], budget="1000")
    _approved_on(ws, cc, "2500.00")              # still approves: the budget only informs
    assert _figures(ws["manager"]) == ("1000.00", "2500.00", "0.00", "-1500.00")


def test_a_purchase_officer_edits_the_budget_and_the_figures_follow(ws):
    cc = _make(ws["buyer"], budget="1000")
    _approved_on(ws, cc, "2500.00")
    r = _patch(ws["buyer"], cc, budget_amount="4000.50")
    assert r.status_code == 200, r.text
    assert (r.json()["budget_amount"], r.json()["remaining"]) == ("4000.50", "1500.50")
    r = ws["manager"].patch(f"/cost-centers/{cc['cost_center_id']}", json={"budget_amount": "1"})
    assert (r.status_code, r.json()["detail"]["code"]) == (403, "COST_CENTRE_FORBIDDEN")
    assert _patch(ws["buyer"], cc, budget_amount="-1").status_code == 422
    r = _patch(ws["buyer"], cc, budget_amount=None)
    assert r.status_code == 422 and "budget_amount" in r.text
    assert _sql("SELECT payload->'budget_amount'->>'to' FROM audit_log"
                " WHERE event = 'cost_centre.update'") == "4000.50"


def test_figures_are_per_cost_centre_and_per_workspace(ws):
    mine = _make(ws["buyer"], code="MINE", budget="500")
    _make(ws["buyer"], code="OTHER", budget="900")
    _approved_on(ws, mine, "2500.00")
    assert _figures(ws["manager"], "MINE")[1] == "2500.00"
    assert _figures(ws["manager"], "OTHER") == ("900.00", "0.00", "0.00", "900.00")
    stranger, _wid, _uid = login("purchase_officer", prefix="cc5")
    theirs = _make(stranger, code="MINE", budget="77")
    assert _figures(stranger, "MINE") == ("77.00", "0.00", "0.00", "77.00") and theirs["committed"] == "0.00"
