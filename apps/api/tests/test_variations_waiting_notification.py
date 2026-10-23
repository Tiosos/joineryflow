"""Variations awaiting approval show in the bell of whoever may decide them (Q617, Q608).

Recipients are fixed in code: managers and admins (the people `POST …/decision` lets decide) who
can write Tracking. A variation counts while it is a `Draft`; it drops out once approved or
rejected. Nothing is stored, so there is nothing to mark read.
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers_tasks import client, sql, workspace

_cleanup = truncate_fixture()


@pytest.fixture
def ws():
    w = workspace()
    sql("INSERT INTO project_contract(project_id, original_value) VALUES (:p, 1000)", p=w["pid"])
    return w


def _add(ws, role="drafter", desc="Extra shelf"):
    r = client(ws, role).post(f"/projects/{ws['pid']}/contract/variations",
                              json={"description": desc, "amount_delta": "10", "reason": "r"})
    assert r.status_code == 201, r.text
    return max(v["variation_id"] for v in r.json()["variations"])


def _waiting(c, **params):
    r = c.get("/notifications", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    return [a for a in body["attention"] if a["kind"] == "variation"], body["attention_totals"].get("variation")


def test_a_draft_is_waiting_for_a_manager_and_an_admin_only(ws):
    vid = _add(ws, desc="Extra shelf")
    for who in ("manager", "admin"):
        rows, total = _waiting(client(ws, who))
        assert total == 1 and len(rows) == 1, who
        row = rows[0]
        assert row["key"] == f"variation:{vid}" and row["url"] == f"/projects/{ws['pid']}"
        assert row["title"].startswith("VAR-001") and ws["slug"].upper() in row["title"]
        assert row["detail"] == "Extra shelf" and row["created_at"]
    for who in ("drafter", "editor", "estimator", "purchase_officer", "viewer"):
        assert _waiting(client(ws, who)) == ([], None), who          # not their decision, not even the author's


def test_a_managers_own_variation_is_approved_at_once_so_nothing_waits(ws):
    _add(ws, role="manager")
    assert _waiting(client(ws, "manager")) == ([], 0)


@pytest.mark.parametrize("decision,note", [("approved", None), ("rejected", "no")])
def test_a_decided_variation_leaves_the_list(ws, decision, note):
    vid = _add(ws)
    assert _waiting(client(ws, "manager"))[1] == 1
    r = client(ws, "manager").post(f"/projects/{ws['pid']}/contract/variations/{vid}/decision",
                                   json={"decision": decision, "note": note})
    assert r.status_code == 200, r.text
    assert _waiting(client(ws, "manager")) == ([], 0)


def test_the_list_is_newest_first(ws):
    first, second = _add(ws, desc="first"), _add(ws, desc="second")
    rows, _ = _waiting(client(ws, "manager"))
    assert [r["key"] for r in rows] == [f"variation:{second}", f"variation:{first}"]


def test_a_manager_who_cannot_write_tracking_is_told_nothing(ws):
    _add(ws)
    s = SessionLocal()
    try:
        gid = s.execute(text("INSERT INTO permission_group(workspace_id, name, is_system)"
                             " VALUES (:w, 'read-only', false) RETURNING group_id"), {"w": ws["wid"]}).scalar()
        s.execute(text("INSERT INTO group_module_grant(group_id, module, action) VALUES (:g, 'tracking', 'read')"),
                  {"g": gid})
        s.execute(text("INSERT INTO user_group_membership(user_id, group_id, project_id) VALUES (:u, :g, NULL)"),
                  {"u": ws["uid"]["manager"], "g": gid})
        s.commit()
    finally:
        s.close()
    assert _waiting(client(ws, "manager")) == ([], None)


def test_another_workspaces_manager_is_not_told(ws):
    _add(ws)
    other = workspace()
    assert _waiting(client(other, "manager")) == ([], 0)


def test_a_paged_or_unread_only_call_does_not_carry_the_list(ws):
    _add(ws)
    for params in ({"offset": 1}, {"unread_only": True}):
        assert _waiting(client(ws, "manager"), **params) == ([], None), params
