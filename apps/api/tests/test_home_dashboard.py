"""Tests for GET /home/dashboard composite endpoint.

Uses the autouse-TRUNCATE pattern from test_items_routes.py.
Raw SQL inserts bypass the route layer for setup.

Reference table seeding required before inserting items:
  - status_options: items.status FK target
  - stages: item_stages.stage_key FK target
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal

from .helpers import login, login_same_workspace
from .conftest import truncate_fixture


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


_cleanup = truncate_fixture(*_EXTRA_TABLES)




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
    c, wid, uid = login(role="admin")
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
    c, wid, uid = login(role="manager")

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
    c, wid, uid = login(role="drafter")

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


def _contract(db, *, pid: int, original: str, variations: tuple[str, ...] = (), status: str = "Current",
              undecided: tuple[tuple[str, str], ...] = ()) -> None:
    """A project's contract (`original` ex the variations) and its Approved variations; sets the project
    status. `undecided` is (status, delta) pairs of Draft / Rejected ones, which never count (Q608)."""
    db.execute(text("UPDATE projects SET status = :s WHERE project_id = :p"), {"s": status, "p": pid})
    db.execute(text("INSERT INTO project_contract(project_id, original_value) VALUES (:p, :v)"),
               {"p": pid, "v": original})
    for delta in variations:
        db.execute(text("INSERT INTO project_contract_variation(project_id, description, amount_delta,"
                        " status, decided_at) VALUES (:p, 'v', :d, 'Approved', now())"), {"p": pid, "d": delta})
    for st, delta in undecided:
        db.execute(text("INSERT INTO project_contract_variation(project_id, description, amount_delta,"
                        " status, decided_at, decision_note) VALUES (:p, 'v', :d, :s,"
                        " CASE WHEN :s = 'Draft' THEN NULL ELSE now() END,"
                        " CASE WHEN :s = 'Rejected' THEN 'no' END)"), {"p": pid, "d": delta, "s": st})
    db.commit()


def _value_card(c) -> dict | None:
    return next((m for m in c.get("/home/dashboard").json()["metrics"] if m["key"] == "value_in_progress"), None)


def test_value_in_progress_adds_up_the_current_value_of_live_projects_for_an_admin():
    """Q634: original value plus variations, live (`Current`) projects only, workspace-wide."""
    c, wid, uid = login(role="admin")
    db = SessionLocal()
    try:
        live_a = _create_project(db, wid=wid, uid=uid, code="VP-A")
        live_b = _create_project(db, wid=wid, uid=uid, code="VP-B")
        held = _create_project(db, wid=wid, uid=uid, code="VP-H")
        closed = _create_project(db, wid=wid, uid=uid, code="VP-C")
        no_contract = _create_project(db, wid=wid, uid=uid, code="VP-N")  # never converted: no contract
        _contract(db, pid=live_a, original="1000.50", variations=("200.25", "-50.00"),
                  undecided=(("Draft", "777.00"), ("Rejected", "888.00")))   # Q608: neither counts
        _contract(db, pid=live_b, original="3000.00")
        _contract(db, pid=held, original="9999.00", status="Hold")
        _contract(db, pid=closed, original="9999.00", status="Closed")
        assert no_contract
    finally:
        db.close()
    card = _value_card(c)
    assert card is not None
    assert card["value"] == 4150.75          # 1000.50 + 200.25 - 50.00 + 3000.00
    assert card["unit"] == "money"
    assert card["href"] is None              # nothing lists projects by contract value to open


def test_a_managers_value_in_progress_counts_only_their_own_projects():
    c, wid, uid = login(role="manager")
    _, other = login_same_workspace(wid, "manager")
    db = SessionLocal()
    try:
        mine = _create_project(db, wid=wid, uid=uid, code="VM-1")
        theirs = _create_project(db, wid=wid, uid=other, code="VM-2")
        _contract(db, pid=mine, original="500.00")
        _contract(db, pid=theirs, original="7000.00")
    finally:
        db.close()
    assert _value_card(c)["value"] == 500.0


def test_value_in_progress_is_left_out_for_roles_that_may_not_see_money():
    """Money is manager / admin only (as the project budget): the card is absent, not zero."""
    for role in ("drafter", "editor", "viewer"):
        c, wid, uid = login(role=role)
        r = c.get("/home/dashboard").json()
        assert _value_card(c) is None, role
        assert [m["key"] for m in r["metrics"]] == ["overdue", "in_optimisation", "awaiting_install"], role


def test_dashboard_purchase_officer_metrics_shape():
    """Purchase officer gets role_view='purchase_officer' and procurement-centric metric keys."""
    c, wid, uid = login(role="purchase_officer")

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
    """purchase_orders has no workspace_id of its own; open_pos and pending_approvals
    (orders with status 'Pending') must still not count another workspace's rows."""
    c, wid, uid = login(role="purchase_officer")
    other_c, other_wid, other_uid = login(role="purchase_officer")

    db = SessionLocal()
    try:
        vendor = db.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Mine', 'Board', :w) RETURNING vendor_id"),
            {"w": wid},
        ).scalar()
        db.execute(
            text("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category, status)
                    VALUES ('PO-MINE-1', :v, :u, 'mine', 'Board', 'Pending')"""),
            {"v": vendor, "u": uid},
        )
        # An Approved order is open but not awaiting approval.
        db.execute(
            text("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category, status)
                    VALUES ('PO-MINE-2', :v, :u, 'approved', 'Board', 'Approved')"""),
            {"v": vendor, "u": uid},
        )

        other_vendor = db.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Other', 'Board', :w) RETURNING vendor_id"),
            {"w": other_wid},
        ).scalar()
        db.execute(
            text("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category, status)
                    VALUES ('PO-OTHER-1', :v, :u, 'not mine', 'Board', 'Pending')"""),
            {"v": other_vendor, "u": other_uid},
        )
        db.commit()
    finally:
        db.close()

    metrics = {m["key"]: m["value"] for m in c.get("/home/dashboard").json()["metrics"]}
    assert metrics["open_pos"] == 2
    assert metrics["pending_approvals"] == 1
    links = {m["key"]: m["href"] for m in c.get("/home/dashboard").json()["metrics"]}
    assert links["pending_approvals"] == "/orderbook?status=Pending"

    other_metrics = {m["key"]: m["value"] for m in other_c.get("/home/dashboard").json()["metrics"]}
    assert other_metrics["open_pos"] == 1
    assert other_metrics["pending_approvals"] == 1


def test_dashboard_includes_team_activity_from_audit_log():
    """Seeded audit_log row appears in team_activity, newest first."""
    c, wid, uid = login(role="admin")

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
    # locked_at (not status) is what `_metrics_estimator`'s "drafts_open"
    # card keys off — set it for every post-SUBMITTED status, matching what
    # the real MGMT_APPROVAL -> SUBMITTED transition always does.
    locked_at = "now()" if status in ("SUBMITTED", "WON", "LOST", "WITHDRAWN") else "NULL"
    rid = db.execute(
        text(
            "INSERT INTO estimate_revision(estimate_id, rev_no, status, "
            f"locked_at, expires_at, converted_project_id, created_by) "
            f"VALUES (:e, 1, :s, {locked_at}, :exp, :conv, :u) RETURNING revision_id"
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
    c, wid, uid = login(role="estimator")
    db = SessionLocal()
    try:
        today = date.today()
        conv_pid = _create_project(db, wid=wid, uid=uid, code="CONV-1")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-A", status="OPPORTUNITY")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-B", status="QUOTE_PREPARED")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-C", status="SUBMITTED")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-D", status="SUBMITTED",
                       expires_at=today + timedelta(days=3))
        _seed_estimate(db, wid=wid, uid=uid, no="EST-E", status="WON")
        _seed_estimate(db, wid=wid, uid=uid, no="EST-F", status="WON",
                       converted_project_id=conv_pid)
        _seed_estimate(db, wid=wid, uid=uid, no="EST-G", status="LOST")
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
    c, _wid, _uid = login(role="estimator")
    data = c.get("/home/dashboard").json()
    assert data["role_view"] == "estimator"
    assert all(m["value"] == 0 for m in data["metrics"])


def test_dashboard_editor_gets_editor_view_with_general_metrics():
    """Editor is now its own role_view but still receives the general
    production cards, not the estimating ones."""
    c, _wid, _uid = login(role="editor")
    data = c.get("/home/dashboard").json()
    assert data["role_view"] == "editor"
    keys = {m["key"] for m in data["metrics"]}
    assert "overdue" in keys           # general/production card present
    assert "drafts_open" not in keys   # not the estimator set


def test_open_pos_tile_link_shows_exactly_the_orders_it_counts():
    """The tile links to /orderbook?status=open; the Orders list must treat `open` as "not
    Delivered / Cancelled / Rejected" (it used to match a status literally called 'open')."""
    c, wid, uid = login(role="purchase_officer")
    db = SessionLocal()
    try:
        vendor = db.execute(
            text("INSERT INTO vendors(name, category, workspace_id) VALUES('V', 'Board', :w) RETURNING vendor_id"),
            {"w": wid},
        ).scalar()
        for n, status in enumerate(["Draft", "Pending", "Approved", "Delivered", "Cancelled", "Rejected"]):
            db.execute(
                text("""INSERT INTO purchase_orders(po_number, vendor_id, requester_id, description, category, status)
                        VALUES (:n, :v, :u, 'x', 'Board', :s)"""),
                {"n": f"PO-OPEN-{n}", "v": vendor, "u": uid, "s": status},
            )
        db.commit()
    finally:
        db.close()

    tiles = {m["key"]: m for m in c.get("/home/dashboard").json()["metrics"]}
    assert tiles["open_pos"]["href"] == "/orderbook?status=open"
    listed = c.get("/orders?status=open").json()["orders"]
    assert tiles["open_pos"]["value"] == len(listed) == 3
    assert {o["status"] for o in listed} == {"Draft", "Pending", "Approved"}
    # a real status still filters literally
    assert [o["status"] for o in c.get("/orders?status=Delivered").json()["orders"]] == ["Delivered"]
