"""Tests for GET /home/dashboard composite endpoint.

Uses the autouse-TRUNCATE pattern from test_items_routes.py.
Raw SQL inserts bypass the route layer for setup.

Reference table seeding required before inserting items:
  - status_options: items.status FK target
  - stages: item_stages.stage_key FK target
"""
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

_STATUS_KEYS = [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]
_STAGE_KEYS = [
    ("REQ", "Required", 1),
    ("SM", "Shop Material", 2),
    ("LISTED", "Listed", 3),
    ("DOWN", "Down", 4),
    ("CNC", "CNC", 5),
    ("EDGED", "Edged", 6),
    ("PAINTED", "Painted", 7),
    ("MADE", "Made", 8),
    ("DEL", "Delivered", 9),
    ("INST", "Installed", 10),
]

_EXTRA_TABLES = (
    "approval_workflows",
    "batch_allocations",
    "procurement_batches",
    "item_stages",
    "item_hardware_lines",
    "project_hardware_catalog",
    "items",
    "hardware_materials",
    "board_materials",
    "status_options",
    "stages",
)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        all_tables = ", ".join(list(_EXTRA_TABLES) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _seed_refs(db) -> None:
    """Insert status_options and stages reference rows (FK targets for items)."""
    for key, order in _STATUS_KEYS:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order)"
                " VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    for key, label, order in _STAGE_KEYS:
        db.execute(
            text(
                "INSERT INTO stages(stage_key, label, sort_order)"
                " VALUES(:k, :l, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "l": label, "o": order},
        )
    db.commit()


def _login(role: str = "admin"):
    """Create workspace + user, seed refs, return (client, wid, uid)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        _seed_refs(db)
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'H') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r)
                RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid


def _create_project(db, *, wid: int, uid: int, code: str = "HJ-001") -> int:
    """Insert a project scoped to workspace via projects.workspace_id, return project_id."""
    pid = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES (:code, :name, :uid, :wid)
            RETURNING project_id
            """
        ),
        {"code": code, "name": f"Project {code}", "uid": uid, "wid": wid},
    ).scalar()
    db.commit()
    return pid


def _insert_item(
    db,
    *,
    project_id: int,
    num: int,
    status: str = "CLEAR",
    cutlist_owner_id: int | None = None,
) -> int:
    """Insert a bare item, return item_id."""
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code, item_locked, cutlist_owner_id)
            VALUES (:num, :pid, :status, 'Test item', 'CAB-01', false, :owner)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id, "status": status, "owner": cutlist_owner_id},
    ).scalar()
    db.commit()
    return iid


def _insert_item_stage(
    db,
    *,
    item_id: int,
    stage_key: str,
    due_date: date,
    done_date: date | None = None,
) -> None:
    """Insert an item_stages row."""
    db.execute(
        text(
            """
            INSERT INTO item_stages(item_id, stage_key, due_date, done_date)
            VALUES (:iid, :sk, :dd, :done)
            ON CONFLICT (item_id, stage_key) DO UPDATE
              SET due_date = EXCLUDED.due_date, done_date = EXCLUDED.done_date
            """
        ),
        {"iid": item_id, "sk": stage_key, "dd": due_date, "done": done_date},
    )
    db.commit()


def _insert_audit(
    db,
    *,
    workspace_id: int,
    actor_id: int,
    event: str,
    target: str,
) -> None:
    """Insert an audit_log row."""
    db.execute(
        text(
            """
            INSERT INTO audit_log(workspace_id, actor_id, event, target, payload)
            VALUES (:wid, :aid, :ev, :tgt, '{}')
            """
        ),
        {"wid": workspace_id, "aid": actor_id, "ev": event, "tgt": target},
    )
    db.commit()


# ── Test cases ─────────────────────────────────────────────────────────────────


def test_dashboard_admin_returns_ceo_view():
    """Admin caller gets role_view='ceo', 4 metric cards, all_projects_count reflects workspace."""
    c, wid, uid = _login(role="admin")
    db = SessionLocal()
    try:
        _create_project(db, wid=wid, uid=uid, code="HJ-001")
        _create_project(db, wid=wid, uid=uid, code="HJ-002")
    finally:
        db.close()

    r = c.get("/home/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["role_view"] == "ceo"
    assert len(data["metrics"]) == 4
    assert data["all_projects_count"] == 2
    keys = {m["key"] for m in data["metrics"]}
    assert "overdue" in keys
    assert "in_optimisation" in keys
    assert "awaiting_install" in keys
    assert "value_in_progress" in keys


def test_dashboard_pm_scope_filters_to_own_projects():
    """Manager caller's overdue metric counts only items from their own projects.

    Two projects in same workspace: one owned by calling PM, one by another manager.
    Overdue item seeded in each project. Assert overdue == 1 (only own project).
    """
    c, wid, uid = _login(role="manager")

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        other_uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'Other', :p, 'manager')
                RETURNING id
                """
            ),
            {"w": wid, "e": f"other-{suffix}@example.com", "p": hash_password("pw")},
        ).scalar()
        db.commit()

        pm_pid = _create_project(db, wid=wid, uid=uid, code="PM-001")
        other_pid = _create_project(db, wid=wid, uid=other_uid, code="OT-001")

        yesterday = date.today() - timedelta(days=1)

        iid1 = _insert_item(db, project_id=pm_pid, num=100, status="CLEAR")
        _insert_item_stage(db, item_id=iid1, stage_key="REQ", due_date=yesterday)

        # Item in other project — should NOT appear in PM's overdue count
        iid2 = _insert_item(db, project_id=other_pid, num=101, status="CLEAR")
        _insert_item_stage(db, item_id=iid2, stage_key="REQ", due_date=yesterday)
    finally:
        db.close()

    r = c.get("/home/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["role_view"] == "pm"
    overdue_card = next(m for m in data["metrics"] if m["key"] == "overdue")
    assert overdue_card["value"] == 1


def test_dashboard_drafter_scope_filters_to_own_items():
    """Drafter's overdue metric counts only items where cutlist_owner_id = caller.

    Two items in the same project: one owned by drafter, one unowned.
    Both have overdue stages. Assert overdue == 1.
    """
    c, wid, uid = _login(role="drafter")

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        mgr_uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'Mgr', :p, 'manager')
                RETURNING id
                """
            ),
            {"w": wid, "e": f"mgr-{suffix}@example.com", "p": hash_password("pw")},
        ).scalar()
        db.commit()

        pid = _create_project(db, wid=wid, uid=mgr_uid, code="DR-001")

        yesterday = date.today() - timedelta(days=1)

        # Item owned by drafter
        iid1 = _insert_item(db, project_id=pid, num=200, cutlist_owner_id=uid)
        _insert_item_stage(db, item_id=iid1, stage_key="REQ", due_date=yesterday)

        # Item NOT owned by drafter — should NOT count
        iid2 = _insert_item(db, project_id=pid, num=201, cutlist_owner_id=None)
        _insert_item_stage(db, item_id=iid2, stage_key="REQ", due_date=yesterday)
    finally:
        db.close()

    r = c.get("/home/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["role_view"] == "drafter"
    overdue_card = next(m for m in data["metrics"] if m["key"] == "overdue")
    assert overdue_card["value"] == 1


def test_dashboard_purchase_officer_metrics_shape():
    """Purchase officer gets role_view='purchase_officer' and procurement-centric metric keys."""
    c, wid, uid = _login(role="purchase_officer")

    r = c.get("/home/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["role_view"] == "purchase_officer"
    assert len(data["metrics"]) == 4
    keys = {m["key"] for m in data["metrics"]}
    assert "overdue" in keys
    # At least one procurement-specific key must be present
    assert "open_pos" in keys or "deliveries_this_week" in keys


def test_dashboard_purchase_officer_open_pos_and_approvals_exclude_other_workspaces():
    """purchase_orders and approval_workflows have no workspace_id of their own;
    open_pos and pending_approvals must still not count another workspace's rows."""
    c, wid, uid = _login(role="purchase_officer")
    other_c, other_wid, other_uid = _login(role="purchase_officer")

    db = SessionLocal()
    try:
        vendor = db.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Mine', 'Board', :w) RETURNING vendor_id"),
            {"w": wid},
        ).scalar()
        po = db.execute(
            text("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category)
                    VALUES ('PO-MINE-1', :v, :u, 'mine', 'Board') RETURNING po_id"""),
            {"v": vendor, "u": uid},
        ).scalar()
        db.execute(
            text("INSERT INTO approval_workflows(po_id, approver_id) VALUES (:p, :u)"),
            {"p": po, "u": uid},
        )

        other_vendor = db.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Other', 'Board', :w) RETURNING vendor_id"),
            {"w": other_wid},
        ).scalar()
        other_po = db.execute(
            text("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category)
                    VALUES ('PO-OTHER-1', :v, :u, 'not mine', 'Board') RETURNING po_id"""),
            {"v": other_vendor, "u": other_uid},
        ).scalar()
        db.execute(
            text("INSERT INTO approval_workflows(po_id, approver_id) VALUES (:p, :u)"),
            {"p": other_po, "u": other_uid},
        )
        db.commit()
    finally:
        db.close()

    metrics = {m["key"]: m["value"] for m in c.get("/home/dashboard").json()["metrics"]}
    assert metrics["open_pos"] == 1
    assert metrics["pending_approvals"] == 1

    other_metrics = {m["key"]: m["value"] for m in other_c.get("/home/dashboard").json()["metrics"]}
    assert other_metrics["open_pos"] == 1
    assert other_metrics["pending_approvals"] == 1


def test_dashboard_includes_team_activity_from_audit_log():
    """Seeded audit_log row appears in team_activity, newest first."""
    c, wid, uid = _login(role="admin")

    db = SessionLocal()
    try:
        _insert_audit(
            db, workspace_id=wid, actor_id=uid, event="project.create", target="42"
        )
    finally:
        db.close()

    r = c.get("/home/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()

    activity = data["team_activity"]
    assert len(activity) >= 1
    events = [a["event"] for a in activity]
    assert "project.create" in events
    # First entry is the most recent (ORDER BY created_at DESC)
    assert activity[0]["event"] == "project.create"
    assert activity[0]["target"] == "42"


# ── Estimator + editor dashboards ───────────────────────────────────────────
#
# estimator and editor used to fall through _role_view to 'viewer' and got the
# production/cutlist cards. estimator now gets a quoting pipeline; editor keeps
# the (production-relevant) general cards but is reported as its own role_view.

def _seed_estimate(
    db, *, wid, uid, no, status, expires_at=None, converted_project_id=None
):
    cid = db.execute(
        text(
            "INSERT INTO customer(workspace_id, name, created_by) "
            "VALUES (:w, :n, :u) RETURNING customer_id"
        ),
        {"w": wid, "n": f"Cust-{no}", "u": uid},
    ).scalar()
    eid = db.execute(
        text(
            "INSERT INTO estimate(workspace_id, customer_id, estimate_no, "
            "title, created_by) VALUES (:w, :c, :no, 'Quote', :u) "
            "RETURNING estimate_id"
        ),
        {"w": wid, "c": cid, "no": no, "u": uid},
    ).scalar()
    rid = db.execute(
        text(
            "INSERT INTO estimate_revision(estimate_id, rev_no, status, "
            "expires_at, converted_project_id, created_by) "
            "VALUES (:e, 1, :s, :exp, :conv, :u) RETURNING revision_id"
        ),
        {"e": eid, "s": status, "exp": expires_at,
         "conv": converted_project_id, "u": uid},
    ).scalar()
    db.execute(
        text("UPDATE estimate SET current_revision_id = :r WHERE estimate_id = :e"),
        {"r": rid, "e": eid},
    )
    return eid, rid


def test_dashboard_estimator_metrics_shape():
    """Estimator gets role_view='estimator' and quoting-pipeline cards keyed
    off each estimate's current revision status."""
    c, wid, uid = _login(role="estimator")
    db = SessionLocal()
    try:
        today = date.today()
        conv_pid = _create_project(db, wid=wid, uid=uid, code="CONV-1")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-A", status="draft")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-B", status="draft")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-C", status="sent")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-D", status="sent",
                       expires_at=today + timedelta(days=3))
        _seed_estimate(db, wid=wid, uid=uid, no="EST-E", status="accepted")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-F", status="accepted",
                       converted_project_id=conv_pid)
        _seed_estimate(db, wid=wid, uid=uid, no="EST-G", status="rejected")
        db.commit()
    finally:
        db.close()

    data = c.get("/home/dashboard").json()
    assert data["role_view"] == "estimator"
    cards = {m["key"]: m["value"] for m in data["metrics"]}
    assert set(cards) == {
        "drafts_open", "awaiting_response", "accepted_unconverted", "expiring_soon",
    }
    assert cards["drafts_open"] == 2
    assert cards["awaiting_response"] == 2       # plain sent + expiring sent
    assert cards["accepted_unconverted"] == 1    # converted one excluded
    assert cards["expiring_soon"] == 1
    assert "overdue" not in cards                # no production card


def test_dashboard_estimator_empty_workspace_is_all_zero():
    c, _wid, _uid = _login(role="estimator")
    data = c.get("/home/dashboard").json()
    assert data["role_view"] == "estimator"
    assert all(m["value"] == 0 for m in data["metrics"])


def test_dashboard_editor_gets_editor_view_with_general_metrics():
    """Editor is now its own role_view but still receives the general
    production cards, not the estimating ones."""
    c, _wid, _uid = _login(role="editor")
    data = c.get("/home/dashboard").json()
    assert data["role_view"] == "editor"
    keys = {m["key"] for m in data["metrics"]}
    assert "overdue" in keys           # general/production card present
    assert "drafts_open" not in keys   # not the estimator set
