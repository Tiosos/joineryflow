"""Tests for project_contract + variations (Q491) and the actual-costs
rollup (Q493/Q549)."""

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login, login_same_workspace



pytestmark = pytest.mark.usefixtures("truncate_after")


def _make_project(wid: int, uid: int, code: str) -> int:
    s = SessionLocal()
    try:
        pid = s.execute(
            text(
                "INSERT INTO projects(project_code, name, workspace_id, created_by) "
                "VALUES (:c, :c, :w, :cb) RETURNING project_id"
            ),
            {"c": code, "w": wid, "cb": str(uid)},
        ).scalar()
        s.commit()
        return pid
    finally:
        s.close()


def _make_contract(pid: int, uid: int, original_value: str) -> None:
    s = SessionLocal()
    try:
        s.execute(
            text(
                "INSERT INTO project_contract(project_id, original_value, created_by) "
                "VALUES (:p, :v, :u)"
            ),
            {"p": pid, "v": original_value, "u": uid},
        )
        s.commit()
    finally:
        s.close()


def test_get_contract_404_when_missing():
    c, wid, uid = login()
    pid = _make_project(wid, uid, "P1")
    r = c.get(f"/projects/{pid}/contract")
    assert r.status_code == 404


def test_get_contract_returns_original_with_no_variations():
    c, wid, uid = login()
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "100000.00")
    r = c.get(f"/projects/{pid}/contract")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["original_value"]) == 100000.00
    assert float(body["current_value"]) == 100000.00
    assert body["variations"] == []


def test_create_variation_updates_current_value():
    c, wid, uid = login()
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "100000.00")
    r = c.post(f"/projects/{pid}/contract/variations",
               json={"description": "Extra bench", "amount_delta": "2500.00"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert float(body["current_value"]) == 102500.00
    assert float(body["original_value"]) == 100000.00  # never overwritten (§17)
    assert len(body["variations"]) == 1


def test_negative_variation_reduces_current_value():
    c, wid, uid = login()
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "100000.00")
    c.post(f"/projects/{pid}/contract/variations",
           json={"description": "Descope tiling", "amount_delta": "-3000.00"})
    r = c.get(f"/projects/{pid}/contract")
    assert float(r.json()["current_value"]) == 97000.00


def test_contract_workspace_isolation():
    c1, wid1, uid1 = login()
    pid = _make_project(wid1, uid1, "P1")
    _make_contract(pid, uid1, "50000.00")
    c2, *_ = login()
    assert c2.get(f"/projects/{pid}/contract").status_code == 404
    r = c2.post(f"/projects/{pid}/contract/variations",
                json={"description": "x", "amount_delta": "1"})
    assert r.status_code == 404


def test_drafter_cannot_write_but_can_read():
    c, wid, uid = login(role="drafter")
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "10000.00")
    assert c.get(f"/projects/{pid}/contract").status_code == 200
    r = c.post(f"/projects/{pid}/contract/variations",
               json={"description": "x", "amount_delta": "1"})
    assert r.status_code == 201  # drafter has tracking:write too


def test_viewer_cannot_write():
    c, wid, uid = login(role="viewer")
    pid = _make_project(wid, uid, "P1")
    _make_contract(pid, uid, "10000.00")
    r = c.post(f"/projects/{pid}/contract/variations",
               json={"description": "x", "amount_delta": "1"})
    assert r.status_code == 403


# --- Variation approval states (Q608) --------------------------------------

def _add(c, pid: int, desc: str = "Extra", amount: str = "100.00") -> dict:
    r = c.post(f"/projects/{pid}/contract/variations", json={"description": desc, "amount_delta": amount})
    assert r.status_code == 201, r.text
    return r.json()


def _decide(c, pid: int, vid: int, decision: str, note: str | None = None):
    return c.post(f"/projects/{pid}/contract/variations/{vid}/decision", json={"decision": decision, "note": note})


def _setup(role: str = "manager"):
    c, wid, uid = login(role=role)
    pid = _make_project(wid, uid, "V1")
    _make_contract(pid, uid, "1000.00")
    return c, wid, uid, pid


def test_a_managers_variation_is_approved_at_once_and_counts():
    c, wid, uid, pid = _setup()
    body = _add(c, pid, "Benchtop upgrade", "250.00")
    v = body["variations"][0]
    assert v["status"] == "Approved" and v["decided_by"] == uid and v["decided_at"] is not None
    assert float(body["current_value"]) == 1250.0


def test_anyone_elses_variation_is_a_draft_and_does_not_count():
    c, wid, uid, pid = _setup()
    d, _ = login_same_workspace(wid, "drafter")
    body = _add(d, pid, "Maybe a bench", "400.00")
    v = body["variations"][0]
    assert v["status"] == "Draft" and v["decided_by"] is None and v["decided_at"] is None
    assert float(body["current_value"]) == 1000.0                   # a Draft is not in the contract value yet


def test_a_manager_approves_a_draft_and_it_counts_from_then_on():
    c, wid, uid, pid = _setup()
    d, _ = login_same_workspace(wid, "drafter")
    vid = _add(d, pid, "Bench", "400.00")["variations"][0]["variation_id"]
    r = _decide(c, pid, vid, "approved", "Client signed")
    assert r.status_code == 200, r.text
    v = r.json()["variations"][0]
    assert (v["status"], v["decided_by"], v["decision_note"]) == ("Approved", uid, "Client signed")
    assert float(r.json()["current_value"]) == 1400.0
    assert float(c.get(f"/projects/{pid}/contract").json()["current_value"]) == 1400.0


def test_rejecting_needs_a_note_and_a_rejected_variation_never_counts():
    c, wid, uid, pid = _setup()
    d, _ = login_same_workspace(wid, "drafter")
    vid = _add(d, pid, "Bench", "400.00")["variations"][0]["variation_id"]
    for note in (None, "", "   "):
        r = _decide(c, pid, vid, "rejected", note)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "REJECTION_NOTE_REQUIRED", note
    r = _decide(c, pid, vid, "rejected", "Not in the contract")
    assert r.status_code == 200, r.text
    v = r.json()["variations"][0]
    assert (v["status"], v["decision_note"], v["decided_by"]) == ("Rejected", "Not in the contract", uid)
    assert float(r.json()["current_value"]) == 1000.0


@pytest.mark.parametrize("role", ["drafter", "editor"])
def test_only_a_manager_or_admin_decides(role):
    c, wid, uid, pid = _setup()
    other, _ = login_same_workspace(wid, role)
    vid = _add(other, pid, "Bench", "400.00")["variations"][0]["variation_id"]
    r = _decide(other, pid, vid, "approved")                      # not even the one who added it
    assert r.status_code == 403 and r.json()["detail"]["code"] == "DECISION_FORBIDDEN"
    assert c.get(f"/projects/{pid}/contract").json()["variations"][0]["status"] == "Draft"


def test_a_decision_is_final():
    c, wid, uid, pid = _setup()
    d, _ = login_same_workspace(wid, "drafter")
    vid = _add(d, pid, "Bench", "400.00")["variations"][0]["variation_id"]
    assert _decide(c, pid, vid, "approved").status_code == 200
    for decision, note in (("approved", None), ("rejected", "changed my mind")):
        r = _decide(c, pid, vid, decision, note)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "VARIATION_ALREADY_DECIDED"
    assert float(c.get(f"/projects/{pid}/contract").json()["current_value"]) == 1400.0


def test_a_draft_is_edited_by_its_creator_or_a_manager_and_nobody_else():
    c, wid, uid, pid = _setup()
    d1, _ = login_same_workspace(wid, "drafter", "D1")
    d2, _ = login_same_workspace(wid, "drafter", "D2")
    vid = _add(d1, pid, "Bnch", "400.00")["variations"][0]["variation_id"]
    url = f"/projects/{pid}/contract/variations/{vid}"
    r = d1.patch(url, json={"description": "Bench"})
    assert r.status_code == 200 and r.json()["variations"][0]["description"] == "Bench"
    r = d2.patch(url, json={"amount_delta": "999"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "NOT_YOUR_VARIATION"
    r = c.patch(url, json={"amount_delta": "450.00"})              # a manager may
    assert r.status_code == 200 and float(r.json()["variations"][0]["amount_delta"]) == 450.0
    assert float(r.json()["current_value"]) == 1000.0              # still a Draft
    for bad in ({"description": None}, {"amount_delta": None}, {"description": ""}):
        assert c.patch(url, json=bad).status_code == 422, bad
    assert _decide(c, pid, vid, "approved").status_code == 200
    r = c.patch(url, json={"description": "late edit"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "VARIATION_NOT_DRAFT"


def test_an_unknown_variation_or_another_workspaces_is_a_404():
    c, wid, uid, pid = _setup()
    vid = _add(c, pid)["variations"][0]["variation_id"]
    other_pid = _make_project(wid, uid, "V2")
    _make_contract(other_pid, uid, "10.00")
    assert _decide(c, pid, vid + 999, "approved").status_code == 404
    assert _decide(c, other_pid, vid, "approved").status_code == 404           # right id, wrong project
    assert c.patch(f"/projects/{other_pid}/contract/variations/{vid}", json={"description": "x"}).status_code == 404
    foreign, *_ = login()
    assert _decide(foreign, pid, vid, "approved").status_code == 404
    assert foreign.patch(f"/projects/{pid}/contract/variations/{vid}", json={"description": "x"}).status_code == 404


def test_edits_and_decisions_are_audited():
    c, wid, uid, pid = _setup()
    d, _ = login_same_workspace(wid, "drafter")
    vid = _add(d, pid, "Bench", "400.00")["variations"][0]["variation_id"]
    d.patch(f"/projects/{pid}/contract/variations/{vid}", json={"amount_delta": "410"})
    _decide(c, pid, vid, "approved")
    s = SessionLocal()
    try:
        events = {e for (e,) in s.execute(
            text("SELECT event FROM audit_log WHERE workspace_id = :w AND event LIKE 'project.contract.variation_%'"),
            {"w": wid})}
    finally:
        s.close()
    assert {"project.contract.variation_add", "project.contract.variation_edit",
            "project.contract.variation_decide"} <= events


# --- Variation item links (Q609) -------------------------------------------


def _item(pid: int, desc: str = "Vanity", **cols) -> int:
    """A live Joinery Item in project `pid`; `cols` sets extras (row_type, deleted, parent_item_id...)."""
    s = SessionLocal()
    try:
        names = ["num", "project_id", "description", "status", *cols]
        vals = ["nextval('joinery_number_seq')", ":p", ":d", "'CLEAR'", *(f":{k}" for k in cols)]
        iid = s.execute(
            text(f"INSERT INTO items({', '.join(names)}) VALUES ({', '.join(vals)}) RETURNING item_id"),
            {"p": pid, "d": desc, **cols},
        ).scalar()
        s.commit()
        return iid
    finally:
        s.close()


def _post(c, pid: int, item_ids, desc="Linked", amount="10.00"):
    return c.post(f"/projects/{pid}/contract/variations",
                  json={"description": desc, "amount_delta": amount, "item_ids": item_ids})


def test_a_variation_has_no_items_unless_it_is_linked_to_some():
    c, wid, uid, pid = _setup()
    assert _add(c, pid)["variations"][0]["items"] == []           # a project-level variation


def test_a_variation_can_be_linked_to_several_items_of_its_project():
    c, wid, uid, pid = _setup()
    a, b = _item(pid, "Vanity"), _item(pid, "Wardrobe")
    r = _post(c, pid, [b, a, a])                                   # duplicates collapse
    assert r.status_code == 201, r.text
    got = r.json()["variations"][0]["items"]
    assert sorted(i["item_id"] for i in got) == sorted([a, b])
    assert {i["description"] for i in got} == {"Vanity", "Wardrobe"}
    assert all(isinstance(i["num"], int) for i in got)
    assert c.get(f"/projects/{pid}/contract").json()["variations"][0]["items"] == got


def test_only_a_live_joinery_item_of_the_same_project_can_be_linked():
    c, wid, uid, pid = _setup()
    other = _make_project(wid, uid, "V2")
    elsewhere = _item(other)
    parent = _item(pid)
    related = _item(pid, "Top", row_type="related_part", parent_item_id=parent,
                    related_part_type_key="benchtop")
    gone = _item(pid, "Gone", deleted=True)
    c2, wid2, uid2 = login(role="admin")
    foreign = _item(_make_project(wid2, uid2, "FX"))
    ghost = _post(c, pid, [987654321])
    assert ghost.status_code == 404 and ghost.json()["detail"]["code"] == "ITEM_NOT_FOUND"
    for bad in (elsewhere, related, gone, foreign):                 # every one answers like a missing id
        r = _post(c, pid, [parent, bad])
        assert (r.status_code, r.json()) == (ghost.status_code, ghost.json()), bad
    assert c.get(f"/projects/{pid}/contract").json()["variations"] == []     # nothing was half-written


def test_a_draft_s_links_are_replaced_on_edit_and_frozen_once_decided():
    c, wid, uid, pid = _setup()
    cd, _ = login_same_workspace(wid, "drafter")
    a, b = _item(pid, "A"), _item(pid, "B")
    vid = cd.post(f"/projects/{pid}/contract/variations",
                  json={"description": "d", "amount_delta": "5", "item_ids": [a]}).json()["variations"][0]["variation_id"]
    r = cd.patch(f"/projects/{pid}/contract/variations/{vid}", json={"item_ids": [b]})
    assert r.status_code == 200 and [i["item_id"] for i in r.json()["variations"][0]["items"]] == [b]
    r = cd.patch(f"/projects/{pid}/contract/variations/{vid}", json={"description": "renamed"})
    assert [i["item_id"] for i in r.json()["variations"][0]["items"]] == [b]      # omitted = unchanged
    assert cd.patch(f"/projects/{pid}/contract/variations/{vid}", json={"item_ids": None}).status_code == 422
    r = cd.patch(f"/projects/{pid}/contract/variations/{vid}", json={"item_ids": []})
    assert r.status_code == 200 and r.json()["variations"][0]["items"] == []        # [] unlinks all
    assert cd.patch(f"/projects/{pid}/contract/variations/{vid}", json={"item_ids": [987654321]}).status_code == 404
    assert _decide(c, pid, vid, "approved").status_code == 200
    r = c.patch(f"/projects/{pid}/contract/variations/{vid}", json={"item_ids": [a]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "VARIATION_NOT_DRAFT"


def test_a_deleted_item_drops_off_the_variation_and_comes_back_on_restore():
    c, wid, uid, pid = _setup()
    a = _item(pid, "A")
    assert _post(c, pid, [a]).status_code == 201
    assert c.delete(f"/items/{a}").status_code in (200, 204)
    assert c.get(f"/projects/{pid}/contract").json()["variations"][0]["items"] == []
    assert c.post(f"/items/{a}/restore").status_code == 204
    assert [i["item_id"] for i in c.get(f"/projects/{pid}/contract").json()["variations"][0]["items"]] == [a]


def test_linking_is_audited():
    c, wid, uid, pid = _setup()
    a = _item(pid)
    _post(c, pid, [a])
    s = SessionLocal()
    try:
        payload = s.execute(text("SELECT payload FROM audit_log WHERE event = 'project.contract.variation_add'"
                                 " AND workspace_id = :w"), {"w": wid}).scalar()
    finally:
        s.close()
    assert payload["item_ids"] == [a]


# --- Void (Q610) -------------------------------------------------------------


def _void(c, pid: int, vid: int, reason: str | None = "Entered twice"):
    return c.post(f"/projects/{pid}/contract/variations/{vid}/void", json={"reason": reason})


def test_a_manager_voids_an_approved_variation_which_stays_listed_but_stops_counting():
    c, wid, uid, pid = _setup()
    a = _add(c, pid, "Benchtop upgrade", "250.00")["variations"][0]["variation_id"]
    _add(c, pid, "Keep", "50.00")
    assert float(c.get(f"/projects/{pid}/contract").json()["current_value"]) == 1300.0
    r = _void(c, pid, a)
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["current_value"]) == 1050.0
    v = next(x for x in body["variations"] if x["variation_id"] == a)
    assert v["status"] == "Voided" and v["void_reason"] == "Entered twice"
    assert v["voided_by"] == uid and v["voided_at"] is not None
    assert v["decided_by"] == uid and v["decided_at"] is not None          # the approval is kept
    assert float(v["amount_delta"]) == 250.0                               # the row is untouched
    assert len(body["variations"]) == 2


def test_voiding_needs_a_reason_and_a_manager_or_admin():
    c, wid, uid, pid = _setup()
    vid = _add(c, pid)["variations"][0]["variation_id"]
    for blank in (None, "", "   "):
        r = _void(c, pid, vid, blank)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "VOID_REASON_REQUIRED", blank
    for role in ("drafter", "editor"):
        other, _ = login_same_workspace(wid, role)
        r = _void(other, pid, vid)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "DECISION_FORBIDDEN"
    assert c.get(f"/projects/{pid}/contract").json()["variations"][0]["status"] == "Approved"


def test_only_an_approved_variation_can_be_voided_and_a_void_is_final():
    c, wid, uid, pid = _setup()
    d, _ = login_same_workspace(wid, "drafter")
    draft = _add(d, pid, "Draft")["variations"][0]["variation_id"]
    rejected = _add(d, pid, "Rejected")["variations"][1]["variation_id"]
    assert _decide(c, pid, rejected, "rejected", "no").status_code == 200
    approved = _add(c, pid, "Approved", "70.00")["variations"][2]["variation_id"]
    for vid in (draft, rejected):
        r = _void(c, pid, vid)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "VARIATION_NOT_APPROVED", vid
    assert _void(c, pid, approved).status_code == 200
    r = _void(c, pid, approved)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "VARIATION_NOT_APPROVED"
    for call in (lambda: _decide(c, pid, approved, "approved"),
                 lambda: c.patch(f"/projects/{pid}/contract/variations/{approved}", json={"description": "x"})):
        assert call().status_code == 409                                  # a voided one is not reopened or edited
    assert float(c.get(f"/projects/{pid}/contract").json()["current_value"]) == 1000.0


def test_an_unknown_variation_or_another_workspaces_cannot_be_voided():
    c, wid, uid, pid = _setup()
    vid = _add(c, pid)["variations"][0]["variation_id"]
    other = _make_project(wid, uid, "V9")
    _make_contract(other, uid, "10.00")
    assert _void(c, pid, 987654321).status_code == 404
    assert _void(c, other, vid).status_code == 404                         # right id, wrong project
    c2, _, _ = login(role="admin")
    assert _void(c2, pid, vid).status_code == 404                          # another workspace's admin
    assert c.get(f"/projects/{pid}/contract").json()["variations"][0]["status"] == "Approved"


def test_a_void_is_audited_and_leaves_the_value_in_progress_card_without_it():
    c, wid, uid, pid = _setup()
    vid = _add(c, pid, "Gone", "500.00")["variations"][0]["variation_id"]
    _void(c, pid, vid, "Client withdrew")
    s = SessionLocal()
    try:
        payload = s.execute(text("SELECT payload FROM audit_log WHERE event = 'project.contract.variation_void'"
                                 " AND workspace_id = :w"), {"w": wid}).scalar()
        live = s.execute(text("SELECT status FROM projects WHERE project_id = :p"), {"p": pid}).scalar()
    finally:
        s.close()
    assert payload["variation_id"] == vid and payload["reason"] == "Client withdrew"
    from app.project_contracts.queries import live_contract_value
    db = SessionLocal()
    try:
        assert live == "Current"
        assert float(live_contract_value(db, workspace_id=wid)) == 1000.0     # not 1500
    finally:
        db.close()


# --- Actual costs (Q493/Q549) ---------------------------------------------

def test_actual_costs_zero_for_untouched_project():
    c, wid, uid = login()
    pid = _make_project(wid, uid, "P1")
    r = c.get(f"/projects/{pid}/actual-costs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert float(body["materials_actual"]) == 0
    assert float(body["labour_actual"]) == 0
    assert float(body["total_actual"]) == 0


def test_actual_costs_materials_from_received_batches():
    c, wid, uid = login()
    pid = _make_project(wid, uid, "P1")
    s = SessionLocal()
    try:
        board_id = s.execute(
            text(
                """
                INSERT INTO board_materials(workspace_id, sku, code, description,
                    cost_per_sheet, unit_cost, default_supplier)
                VALUES (:w, 'SKU1', 'SKU1', 'Board', 50, 50, 'Sup')
                RETURNING material_id
                """
            ),
            {"w": wid},
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO procurement_batches(
                    project_id, material_type, material_id, qty_ordered,
                    qty_received, cost_per_unit
                ) VALUES (:p, 'BOARD', :m, 10, 4, 25.00)
                """
            ),
            {"p": pid, "m": board_id},
        )
        s.commit()
    finally:
        s.close()
    r = c.get(f"/projects/{pid}/actual-costs")
    assert r.status_code == 200, r.text
    assert float(r.json()["materials_actual"]) == 100.00  # 4 * 25.00


def test_actual_costs_workspace_isolation():
    c1, wid1, uid1 = login()
    pid = _make_project(wid1, uid1, "P1")
    c2, *_ = login()
    assert c2.get(f"/projects/{pid}/actual-costs").status_code == 404
