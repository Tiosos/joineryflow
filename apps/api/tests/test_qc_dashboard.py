"""QC Dashboard (Plan V1 §4.2): GET /qc/dashboard.

What these pin down:

  - scope is *started but not finished* cutlists, derived from Shop Floor:
    started = an assignment actually begun and not cancelled, or a completion
    that was not undone; finished = a PACKING completion that was not undone.
    Every boundary of that definition has its own case, including the ones a
    plausible-looking query gets wrong (a merely `assigned` task, a cancelled
    start, an undone completion, an undone PACKING)
  - records outside the scope are counted, never silently dropped
  - open records only; resolved defects and closed rework are history
  - defects by project and by stage (untagged last), rework by project and
    kind with cost and the count of records that have none
  - project / date filters, and the 404 / 422 edges
  - qc:read gates it; another workspace's data never leaks; related parts are
    not counted
  - read-only: it writes no audit row
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.auth.rbac_engine import seed_system_groups
from app.db import SessionLocal
from app.main import app
from .helpers import log_in

NOW = datetime.now(timezone.utc)


def _db():
    return SessionLocal()


def _workspace(roles=("manager", "viewer", "editor")) -> dict:
    slug = f"qcd-{uuid.uuid4().hex[:8]}"
    s = _db()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'QCD') RETURNING id"),
                        {"s": slug}).scalar()
        uids = {}
        for role in roles:
            uids[role] = s.execute(text(
                """INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                   VALUES(:w,:e,:n,:p,:r) RETURNING id"""),
                {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                 "p": hash_password("pw"), "r": role}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "uids": uids, "n": 0}


def _client(ws: dict, role: str = "manager") -> TestClient:
    c = TestClient(app)
    log_in(ws["slug"], f"{role}@{ws['slug']}.test", client=c)
    return c


def _project(ws: dict, code: str) -> int:
    s = _db()
    try:
        pid = s.execute(text("INSERT INTO projects(project_code,name,workspace_id)"
                             " VALUES(:c,:c,:w) RETURNING project_id"),
                        {"c": f"{code}-{ws['slug']}", "w": ws["wid"]}).scalar()
        s.commit()
        return pid
    finally:
        s.close()


def _item(ws: dict, pid: int, state: str | None) -> int:
    """A joinery item whose cutlist is in `state` (None = no cutlist at all).

    not_started  cutlist exists, nothing assigned
    assigned     an assignment that has NOT been begun
    started      an assignment in progress (started_at set)
    cancelled    an assignment that was begun and then cancelled
    completed    a DOWN completion
    undone       a DOWN completion that was undone
    finished     DOWN and PACKING completed
    unpacked     DOWN and PACKING completed, PACKING then undone
    """
    uid = ws["uids"]["manager"]
    s = _db()
    try:
        cl = None
        if state is not None:
            ws["n"] += 1
            cl = s.execute(text("INSERT INTO cutlist(project_id,cutlist_no,created_by)"
                                " VALUES(:p,:n,:u) RETURNING cutlist_id"),
                           {"p": pid, "n": 800000 + uuid.uuid4().int % 99999, "u": uid}).scalar()
        iid = s.execute(text("""INSERT INTO items(num, project_id, cutlist_id, description, status)
                                VALUES (nextval('joinery_number_seq'), :p, :cl, 'Vanity', 'CLEAR')
                                RETURNING item_id"""), {"p": pid, "cl": cl}).scalar()

        def assignment(status, *, started, cancelled=False):
            s.execute(text("""INSERT INTO worker_assignment(cutlist_id, stage_key, worker_id,
                                  status, assigned_by, started_at, cancelled_at)
                              VALUES (:cl,'CNC',:u,:st,:u,:sa,:ca)"""),
                      {"cl": cl, "u": uid, "st": status,
                       "sa": NOW if started else None, "ca": NOW if cancelled else None})

        def completion(stage, *, undone=False):
            s.execute(text("""INSERT INTO stage_completion_log(cutlist_id, stage_key, worker_id,
                                  completed_at, undone_at)
                              VALUES (:cl,:sk,:u,:t,:ud)"""),
                      {"cl": cl, "sk": stage, "u": uid, "t": NOW,
                       "ud": NOW if undone else None})

        if state == "assigned":
            assignment("assigned", started=False)
        elif state == "started":
            assignment("in_progress", started=True)
        elif state == "cancelled":
            assignment("cancelled", started=True, cancelled=True)
        elif state == "completed":
            completion("DOWN")
        elif state == "undone":
            completion("DOWN", undone=True)
        elif state == "finished":
            completion("DOWN")
            completion("PACKING")
        elif state == "unpacked":
            completion("DOWN")
            completion("PACKING", undone=True)
        s.commit()
        return iid
    finally:
        s.close()


def _defect(ws, iid, *, stage=None, status="open", age_days=0, desc="Chipped edge"):
    s = _db()
    try:
        s.execute(text("""INSERT INTO qc_defect(item_id, stage_key, description, status,
                              created_by, created_at)
                          VALUES (:i,:sk,:d,:st,:u,:t)"""),
                  {"i": iid, "sk": stage, "d": desc, "st": status, "u": ws["uids"]["manager"],
                   "t": NOW - timedelta(days=age_days)})
        s.commit()
    finally:
        s.close()


def _rework(ws, iid, *, kind="internal", cost=None, status="open", age_days=0):
    s = _db()
    try:
        s.execute(text("""INSERT INTO rework(item_id, kind, cause, scope, cost, status,
                              created_by, created_at)
                          VALUES (:i,:k,'cause','scope',:c,:st,:u,:t)"""),
                  {"i": iid, "k": kind, "c": cost, "st": status, "u": ws["uids"]["manager"],
                   "t": NOW - timedelta(days=age_days)})
        s.commit()
    finally:
        s.close()


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    return _workspace()


def _get(ws, role="manager", **params):
    return _client(ws, role).get("/qc/dashboard", params=params)


# ============================================================================
# Scope: started but not finished
# ============================================================================

def test_scope_is_started_but_not_finished_cutlists_at_every_boundary(ws):
    pid = _project(ws, "A")
    in_scope = {s: _item(ws, pid, s) for s in ("started", "completed", "unpacked")}
    out_scope = {s: _item(ws, pid, s) for s in
                 (None, "not_started", "assigned", "cancelled", "undone", "finished")}
    for iid in [*in_scope.values(), *out_scope.values()]:
        _defect(ws, iid)
        _rework(ws, iid)

    r = _get(ws)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"]["items_in_scope"] == 3
    assert {i["item_id"] for i in body["items"]} == set(in_scope.values())
    assert body["defects_open"] == 3 and body["rework_open"] == 3
    # nothing vanishes: the six left out are counted, for both kinds of record
    assert body["scope"]["open_defects_out_of_scope"] == 6
    assert body["scope"]["open_rework_out_of_scope"] == 6


def test_a_finished_cutlist_drops_out_and_an_undone_packing_brings_it_back(ws):
    pid = _project(ws, "A")
    iid = _item(ws, pid, "finished")
    _defect(ws, iid)
    assert _get(ws).json()["defects_open"] == 0
    s = _db()
    try:
        s.execute(text("UPDATE stage_completion_log SET undone_at = now()"
                       " WHERE stage_key = 'PACKING'"))
        s.commit()
    finally:
        s.close()
    assert _get(ws).json()["defects_open"] == 1


# ============================================================================
# Contents
# ============================================================================

def test_open_only_resolved_defects_and_closed_rework_are_history(ws):
    pid = _project(ws, "A")
    iid = _item(ws, pid, "started")
    _defect(ws, iid, status="open")
    _defect(ws, iid, status="resolved")
    _rework(ws, iid, status="open")
    _rework(ws, iid, status="closed")
    body = _get(ws).json()
    assert body["defects_open"] == 1 and body["rework_open"] == 1
    # history is not "out of scope" either: it is simply not part of this view
    assert body["scope"]["open_defects_out_of_scope"] == 0
    assert body["scope"]["open_rework_out_of_scope"] == 0


def test_defects_by_project_and_stage_with_untagged_last(ws):
    p1, p2 = _project(ws, "A"), _project(ws, "B")
    i1, i2 = _item(ws, p1, "started"), _item(ws, p2, "started")
    _defect(ws, i1, stage="CNC", age_days=5)
    _defect(ws, i1, stage="CNC", age_days=2)
    _defect(ws, i1, stage="DOWN", age_days=9)
    _defect(ws, i1, stage=None, age_days=1)
    _defect(ws, i2, stage="PACKING")

    body = _get(ws).json()
    assert body["defects_open"] == 5
    # workflow order (the `stages` lookup's sort_order), untagged last. Keys,
    # not labels: labels are lookup data and differ between databases.
    assert [(s["stage_key"], s["open"]) for s in body["defects_by_stage"]] == [
        ("DOWN", 1), ("CNC", 2), ("PACKING", 1), (None, 1)]
    assert body["defects_by_stage"][-1]["label"] == "Untagged"

    by = {p["project_id"]: p for p in body["defects_by_project"]}
    assert by[p1]["open"] == 4 and by[p2]["open"] == 1
    assert [(s["stage_key"], s["open"]) for s in by[p1]["by_stage"]] == [
        ("DOWN", 1), ("CNC", 2), (None, 1)]
    # the oldest open one is nine days old
    age = NOW - datetime.fromisoformat(by[p1]["oldest_open_at"])
    assert timedelta(days=8, hours=23) < age < timedelta(days=9, hours=1)


def test_rework_by_project_and_kind_with_cost_and_missing_cost(ws):
    p1 = _project(ws, "A")
    i1 = _item(ws, p1, "started")
    _rework(ws, i1, kind="internal", cost="100.50")
    _rework(ws, i1, kind="full", cost="250.00")
    _rework(ws, i1, kind="internal", cost=None)

    body = _get(ws).json()
    assert body["rework_open"] == 3
    (row,) = body["rework_by_project"]
    assert (row["internal"], row["full"]) == (2, 1)
    # money arrives as strings, per the repo convention
    assert row["cost_total"] == "350.50" and body["rework_cost_total"] == "350.50"
    # a total that under-counts says so: one open rework has no cost yet
    assert row["cost_missing"] == 1 and body["rework_cost_missing"] == 1


def test_items_drill_down_is_oldest_first_with_counts(ws):
    pid = _project(ws, "A")
    newer, older, clean = (_item(ws, pid, "started") for _ in range(3))
    _defect(ws, newer, age_days=1)
    _defect(ws, older, age_days=7)
    _rework(ws, older, age_days=3)

    items = _get(ws).json()["items"]
    assert [i["item_id"] for i in items] == [older, newer]      # clean item omitted
    assert clean not in {i["item_id"] for i in items}
    assert (items[0]["open_defects"], items[0]["open_rework"]) == (1, 1)
    assert (items[1]["open_defects"], items[1]["open_rework"]) == (1, 0)
    assert {"item_id", "num", "project_code", "oldest_open_at"} <= set(items[0])


def test_empty_dashboard_is_zeros_not_an_error(ws):
    body = _get(ws).json()
    assert body["defects_open"] == 0 and body["rework_open"] == 0
    assert body["rework_cost_total"] == "0" or body["rework_cost_total"] == "0.00"
    assert body["items"] == [] and body["defects_by_project"] == []
    assert body["scope"] == {"items_in_scope": 0, "open_defects_out_of_scope": 0,
                             "open_rework_out_of_scope": 0}


def test_related_parts_are_not_counted(ws):
    pid = _project(ws, "A")
    parent = _item(ws, pid, "started")
    s = _db()
    try:
        rp = s.execute(text("""INSERT INTO items(num, project_id, description, status, row_type,
                                   parent_item_id, related_part_type_key)
                               VALUES (nextval('joinery_number_seq'), :p, 'Top', 'CLEAR',
                                       'related_part', :par, 'benchtop') RETURNING item_id"""),
                       {"p": pid, "par": parent}).scalar()
        s.commit()
    finally:
        s.close()
    _defect(ws, rp)
    body = _get(ws).json()
    assert body["defects_open"] == 0
    assert body["scope"]["open_defects_out_of_scope"] == 0     # not even "outside": not a joinery item


# ============================================================================
# Filters
# ============================================================================

def test_project_filter_scopes_every_number_including_out_of_scope(ws):
    p1, p2 = _project(ws, "A"), _project(ws, "B")
    _defect(ws, _item(ws, p1, "started"))
    _defect(ws, _item(ws, p1, "not_started"))
    _defect(ws, _item(ws, p2, "started"))
    _defect(ws, _item(ws, p2, "started"))

    body = _get(ws, project_id=p1).json()
    assert body["defects_open"] == 1
    assert [p["project_id"] for p in body["defects_by_project"]] == [p1]
    assert body["scope"]["open_defects_out_of_scope"] == 1     # p1's only, not p2's
    assert body["scope"]["items_in_scope"] == 1


def test_date_range_filters_on_when_the_record_was_raised_inclusive(ws):
    pid = _project(ws, "A")
    iid = _item(ws, pid, "started")
    _defect(ws, iid, age_days=10)
    _defect(ws, iid, age_days=5)
    _defect(ws, iid, age_days=1)
    _rework(ws, iid, age_days=10)
    _rework(ws, iid, age_days=1)
    today = NOW.date()
    day = lambda n: (today - timedelta(days=n)).isoformat()   # noqa: E731

    assert _get(ws, date_from=day(6)).json()["defects_open"] == 2
    assert _get(ws, date_to=day(6)).json()["defects_open"] == 1
    both = _get(ws, date_from=day(6), date_to=day(4)).json()
    assert both["defects_open"] == 1 and both["rework_open"] == 0
    # `date_to` includes the whole of that day
    assert _get(ws, date_from=day(1), date_to=day(1)).json()["defects_open"] == 1
    # the out-of-scope counts honour the same window
    _defect(ws, _item(ws, pid, "not_started"), age_days=10)
    assert _get(ws, date_from=day(6)).json()["scope"]["open_defects_out_of_scope"] == 0
    assert _get(ws).json()["scope"]["open_defects_out_of_scope"] == 1


def test_bad_filters_are_clean_errors(ws):
    assert _get(ws, date_from="2026-02-02", date_to="2026-01-01").status_code == 422
    assert _get(ws, date_from="not-a-date").status_code == 422
    assert _get(ws, project_id=999999).status_code == 404
    other = _workspace()
    assert _get(ws, project_id=_project(other, "X")).status_code == 404


# ============================================================================
# Access and isolation
# ============================================================================

def test_qc_read_is_enough_and_qc_read_is_required(ws):
    _defect(ws, _item(ws, _project(ws, "A"), "started"))
    assert _get(ws, role="viewer").status_code == 200          # read-only role can see it
    assert _get(ws, role="editor").status_code == 200

    # Strip qc from the viewer's group: DB-governed users get a real 403.
    s = _db()
    try:
        seed_system_groups(s, workspace_id=ws["wid"])
        gid = s.execute(text("SELECT group_id FROM permission_group"
                             " WHERE workspace_id=:w AND name='viewer'"), {"w": ws["wid"]}).scalar()
        s.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id)"
                       " VALUES (:u,:g,NULL)"), {"u": ws["uids"]["viewer"], "g": gid})
        s.execute(text("DELETE FROM group_module_grant WHERE group_id=:g AND module='qc'"),
                  {"g": gid})
        s.commit()
    finally:
        s.close()
    assert _get(ws, role="viewer").status_code == 403
    assert _get(ws, role="manager").status_code == 200


def test_unauthenticated_is_refused(ws):
    assert TestClient(app).get("/qc/dashboard").status_code == 401


def test_another_workspaces_records_never_appear(ws):
    other = _workspace()
    _defect(other, _item(other, _project(other, "Z"), "started"))
    _rework(other, _item(other, _project(other, "Y"), "started"), cost="999.00")
    body = _get(ws).json()
    assert body["defects_open"] == 0 and body["rework_open"] == 0
    assert body["scope"]["open_defects_out_of_scope"] == 0
    assert body["rework_cost_total"] in ("0", "0.00")
    # and they do appear for their own workspace
    assert _get(other).json()["defects_open"] == 1


def test_it_is_read_only_and_writes_no_audit_row(ws):
    _defect(ws, _item(ws, _project(ws, "A"), "started"))
    s = _db()
    try:
        before = s.execute(text("SELECT count(*) FROM audit_log WHERE event NOT LIKE 'auth.%'")).scalar()
    finally:
        s.close()
    assert _get(ws).status_code == 200
    s = _db()
    try:
        after = s.execute(text("SELECT count(*) FROM audit_log WHERE event NOT LIKE 'auth.%'")).scalar()
    finally:
        s.close()
    assert after == before
