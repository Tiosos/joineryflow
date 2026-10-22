"""Close-out checks (user decision 2026-10-22: warn and confirm).

`GET /projects/{id}/close-out-checks` says what is still open on a project (QC defects and
rework, items not installed, open orders). It is advisory: nothing blocks `close-out`, whose
audit row keeps what was open and the reason given.
"""
import json

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login


@pytest.fixture
def proj(truncate_all):
    truncate_all()
    c, wid, uid = login("manager")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="CO-1")
    finally:
        db.close()
    return {"c": c, "w": wid, "u": uid, "pid": pid}


def _sql(sql, **p):
    db = SessionLocal()
    try:
        r = db.execute(text(sql), p)
        out = r.scalar() if r.returns_rows else None
        db.commit()
        return out
    finally:
        db.close()


def _item(p, status="LIVE"):
    return _sql("""INSERT INTO items(num, project_id, description, status)
                   VALUES (nextval('joinery_number_seq'), :p, 'x', :s) RETURNING item_id""",
                p=p["pid"], s=status)


def _checks(p):
    r = p["c"].get(f"/projects/{p['pid']}/close-out-checks")
    assert r.status_code == 200, r.text
    return r.json()


def test_an_empty_project_has_nothing_open(proj):
    assert _checks(proj) == {"open_defects": 0, "open_rework": 0, "items_not_installed": 0, "open_orders": 0}


def test_checks_count_what_is_open(proj):
    a, b, void, installed = _item(proj), _item(proj), _item(proj, "VOID"), _item(proj)
    _sql("INSERT INTO item_stages(item_id, stage_key, done_date) VALUES (:i, 'INST', CURRENT_DATE)", i=installed)
    _sql("UPDATE items SET deleted = true WHERE item_id = :i", i=_item(proj))     # soft-deleted: not counted
    for status in ("open", "open", "resolved"):
        _sql("INSERT INTO qc_defect(item_id, description, status, created_by) VALUES (:i, 'chip', :s, :u)",
             i=a, s=status, u=proj["u"])
    for status in ("open", "closed"):
        _sql("""INSERT INTO rework(item_id, kind, cause, scope, status, created_by)
                VALUES (:i, 'internal', 'c', 's', :s, :u)""", i=b, s=status, u=proj["u"])
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w) RETURNING vendor_id",
                  w=proj["w"])
    for status in ("Pending", "Approved", "Delivered", "Cancelled", "Rejected"):
        _sql("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, project_id, category,
                                            description, status)
                VALUES ('PO-T-' || nextval('po_number_seq'), :v, :u, :p, 'Board', 'x', :s)""",
             v=vendor, u=proj["u"], p=proj["pid"], s=status)
    assert void
    assert _checks(proj) == {"open_defects": 2, "open_rework": 1,
                             "items_not_installed": 2,        # a and b: VOID, installed and deleted are out
                             "open_orders": 2}                # Pending and Approved


def test_checks_are_manager_or_admin_and_this_workspaces(proj):
    pid = proj["pid"]
    assert login("drafter", wid=proj["w"])[0].get(f"/projects/{pid}/close-out-checks").status_code == 403
    other, _, _ = login("manager")
    r = other.get(f"/projects/{pid}/close-out-checks")
    ghost = other.get("/projects/999999999/close-out-checks")
    assert r.status_code == ghost.status_code == 404 and r.json() == ghost.json()


def test_close_out_is_never_blocked_and_audits_what_was_open_and_the_reason(proj):
    a = _item(proj)
    _sql("INSERT INTO qc_defect(item_id, description, created_by) VALUES (:i, 'chip', :u)", i=a, u=proj["u"])
    r = proj["c"].post(f"/projects/{proj['pid']}/close-out", json={"reason": "  Client signed off  "})
    assert r.status_code == 200, r.text
    payload = _sql("SELECT payload FROM audit_log WHERE event = 'project.close_out' AND target = :t",
                   t=str(proj["pid"]))
    payload = payload if isinstance(payload, dict) else json.loads(payload)
    assert payload["reason"] == "Client signed off"
    assert payload["open"]["open_defects"] == 1 and payload["open"]["items_not_installed"] == 1


def test_close_out_without_a_body_still_works(proj):
    assert proj["c"].post(f"/projects/{proj['pid']}/close-out").status_code == 200
    payload = _sql("SELECT payload FROM audit_log WHERE event = 'project.close_out' AND target = :t",
                   t=str(proj["pid"]))
    payload = payload if isinstance(payload, dict) else json.loads(payload)
    assert payload["reason"] is None
