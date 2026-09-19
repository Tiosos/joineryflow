"""Tests for lock semantics on items (spec §6.4 T15, re-cut by B7 / Q509).

11 test cases covering:
  - First-save claim (unlocked + unowned item gets claimed on PATCH)
  - Controlled Lock: a non-owner's save is held as a request, not applied
  - Re-saving revises your own pending request instead of stacking a second
  - Owner approves → the change lands, credited to the requester
  - Owner rejects → the item is untouched
  - A manager may decide; an unrelated drafter may not
  - Deciding twice → 409 ALREADY_DECIDED
  - Release keeps owner_id (sticky claim)
  - Transfer by owner
  - Transfer by non-owner → 403
  - Manager force-transfer
  - GET lock_warning populated for non-owner

Uses the same truncate/seed patterns as test_items_routes.py.
"""
import uuid

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


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        extra = (
            "batch_allocations",
            "procurement_batches",
            "item_stages",
            "item_hardware_lines",
            "project_hardware_catalog",
            "item_lock_request",
            "items",
            "hardware_materials",
            "board_materials",
            "status_options",
            "stages",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _seed_refs(db) -> None:
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


def _make_user(
    db,
    *,
    workspace_id: int,
    role: str,
    name: str = "Test User",
) -> tuple[int, str, str]:
    """Insert a user in workspace and return (uid, email, password)."""
    suffix = uuid.uuid4().hex[:8]
    email = f"u-{suffix}@example.com"
    pw = "pw"
    uid = db.execute(
        text(
            """
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, :name, :p, :r)
            RETURNING id
            """
        ),
        {"w": workspace_id, "e": email, "name": name, "p": hash_password(pw), "r": role},
    ).scalar()
    db.commit()
    return uid, email, pw


def _login_user(*, workspace_slug: str, email: str, password: str) -> TestClient:
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": workspace_slug, "email": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return c


def _setup_workspace_and_project(
    role_a: str = "drafter", project_name: str = "Lock Project"
) -> dict:
    """Create workspace + project + primary user A.  Returns context dict."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"ws-{suffix}"
    db = SessionLocal()
    try:
        _seed_refs(db)
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'Locks WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid_a, email_a, pw_a = _make_user(
            db, workspace_id=wid, role=role_a, name="Drafter A"
        )
        pid = db.execute(
            text(
                "INSERT INTO projects(project_code, name, pm_id, workspace_id)"
                " VALUES(:code, :pname, :uid, :wid) RETURNING project_id"
            ),
            {"code": f"LP-{suffix}", "pname": project_name, "uid": uid_a, "wid": wid},
        ).scalar()
        db.commit()
    finally:
        db.close()

    c_a = _login_user(workspace_slug=slug, email=email_a, password=pw_a)
    return {"wid": wid, "slug": slug, "uid_a": uid_a, "pid": pid, "c_a": c_a}


def _insert_unlocked_item(db, *, project_id: int, num: int) -> int:
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code,
                              item_locked, cutlist_owner_id)
            VALUES (:num, :pid, 'CLEAR', 'Lock test item', 'LK-01', false, NULL)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id},
    ).scalar()
    db.commit()
    return iid


def _get_item_state(iid: int) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT item_locked, cutlist_owner_id FROM items WHERE item_id = :iid"
            ),
            {"iid": iid},
        ).mappings().first()
        return dict(row) if row else {}
    finally:
        db.close()


# ── Test 1 ─────────────────────────────────────────────────────────────────────


def test_first_save_claims_ownership_and_locks():
    """PATCH on unlocked, unowned item claims ownership and sets item_locked=true."""
    ctx = _setup_workspace_and_project()
    db = SessionLocal()
    try:
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1001)
    finally:
        db.close()

    state_before = _get_item_state(iid)
    assert state_before["item_locked"] is False
    assert state_before["cutlist_owner_id"] is None

    r = ctx["c_a"].patch(f"/items/{iid}", json={"description": "Claimed by A"})
    assert r.status_code == 200, r.text

    state_after = _get_item_state(iid)
    assert state_after["item_locked"] is True, "item_locked should be True after first save"
    assert state_after["cutlist_owner_id"] == ctx["uid_a"], "owner should be actor A"


# ── Test 2 ─────────────────────────────────────────────────────────────────────


def test_second_save_by_other_becomes_a_lock_request():
    """Controlled Lock (Q509): a non-owner PATCH is held, not applied.

    Replaces the pre-B7 behaviour, where the save went through and only left an
    `item.lock_overridden` audit row behind it.
    """
    ctx = _setup_workspace_and_project()
    db = SessionLocal()
    try:
        uid_b, email_b, pw_b = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter B"
        )
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1002)
    finally:
        db.close()

    c_b = _login_user(workspace_slug=ctx["slug"], email=email_b, password=pw_b)

    # A patches first → claims lock
    r = ctx["c_a"].patch(f"/items/{iid}", json={"description": "A's edit"})
    assert r.status_code == 200, r.text
    assert _get_item_state(iid)["cutlist_owner_id"] == ctx["uid_a"]

    # B patches → held as a request, not applied
    r2 = c_b.patch(f"/items/{iid}", json={"description": "B's proposal"})
    assert r2.status_code == 409, (
        f"Non-owner PATCH should be held (409), got {r2.status_code}: {r2.text}"
    )
    detail = r2.json()["detail"]
    assert detail["code"] == "LOCK_REQUEST_CREATED"
    assert detail["owner_id"] == ctx["uid_a"]
    assert detail["fields"] == ["description"]

    # The item itself is untouched, and the lock is still A's
    db2 = SessionLocal()
    try:
        desc = db2.execute(
            text("SELECT description FROM items WHERE item_id = :iid"), {"iid": iid}
        ).scalar()
    finally:
        db2.close()
    assert desc == "A's edit", "B's save must not reach the item"
    assert _get_item_state(iid)["cutlist_owner_id"] == ctx["uid_a"]

    # The request is visible on the item, pending, carrying B's body
    r3 = ctx["c_a"].get(f"/items/{iid}/lock-requests?status=pending")
    assert r3.status_code == 200, r3.text
    reqs = r3.json()
    assert len(reqs) == 1
    assert reqs[0]["requested_by"] == uid_b
    assert reqs[0]["requested_changes"] == {"description": "B's proposal"}
    assert reqs[0]["status"] == "pending"

    # ...and audited as a request, not an override
    db3 = SessionLocal()
    try:
        events = [
            row[0]
            for row in db3.execute(
                text(
                    "SELECT event FROM audit_log WHERE target = :t ORDER BY id"
                ),
                {"t": str(iid)},
            ).all()
        ]
    finally:
        db3.close()
    assert "item.lock_request.create" in events
    assert "item.lock_overridden" not in events, (
        "the override event is retired by the Controlled Lock"
    )


# ── Test 3 ─────────────────────────────────────────────────────────────────────


def test_release_lock_keeps_owner_id():
    """DELETE /items/{id}/lock clears item_locked but leaves cutlist_owner_id intact."""
    ctx = _setup_workspace_and_project()
    db = SessionLocal()
    try:
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1003)
    finally:
        db.close()

    # A claims lock via PATCH
    ctx["c_a"].patch(f"/items/{iid}", json={"description": "Lock claimed"})
    state_after_claim = _get_item_state(iid)
    assert state_after_claim["item_locked"] is True
    assert state_after_claim["cutlist_owner_id"] == ctx["uid_a"]

    # A releases lock
    r = ctx["c_a"].delete(f"/items/{iid}/lock")
    assert r.status_code == 200, r.text

    state_after_release = _get_item_state(iid)
    assert state_after_release["item_locked"] is False, (
        "item_locked should be False after release"
    )
    assert state_after_release["cutlist_owner_id"] == ctx["uid_a"], (
        "cutlist_owner_id should remain A after lock release (sticky claim)"
    )


# ── Test 4 ─────────────────────────────────────────────────────────────────────


def test_transfer_lock_by_owner():
    """Owner A can transfer lock to B via POST /items/{id}/lock with {owner_id: B}."""
    ctx = _setup_workspace_and_project()
    db = SessionLocal()
    try:
        uid_b, email_b, pw_b = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter B"
        )
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1004)
    finally:
        db.close()

    # A claims lock
    ctx["c_a"].patch(f"/items/{iid}", json={"description": "A owns this"})

    # A transfers to B
    r = ctx["c_a"].post(f"/items/{iid}/lock", json={"owner_id": uid_b})
    assert r.status_code == 200, r.text

    state = _get_item_state(iid)
    assert state["cutlist_owner_id"] == uid_b, (
        f"Expected owner=B({uid_b}), got {state['cutlist_owner_id']}"
    )
    assert state["item_locked"] is True


# ── Test 5 ─────────────────────────────────────────────────────────────────────


def test_transfer_lock_by_non_owner_403():
    """Drafter C (not owner, not manager/admin) cannot transfer A's lock."""
    ctx = _setup_workspace_and_project()
    db = SessionLocal()
    try:
        uid_b, email_b, pw_b = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter B"
        )
        uid_c, email_c, pw_c = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter C"
        )
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1005)
    finally:
        db.close()

    # A claims lock
    ctx["c_a"].patch(f"/items/{iid}", json={"description": "A's item"})

    # C (not owner) tries to transfer to B → should be 403
    c_c = _login_user(workspace_slug=ctx["slug"], email=email_c, password=pw_c)
    r = c_c.post(f"/items/{iid}/lock", json={"owner_id": uid_b})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


# ── Test 6 ─────────────────────────────────────────────────────────────────────


def test_manager_can_force_transfer():
    """Manager (not the owner) can transfer lock to another user."""
    ctx = _setup_workspace_and_project(role_a="drafter")
    db = SessionLocal()
    try:
        uid_mgr, email_mgr, pw_mgr = _make_user(
            db, workspace_id=ctx["wid"], role="manager", name="Manager"
        )
        uid_b, email_b, pw_b = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter B"
        )
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1006)
    finally:
        db.close()

    # A claims lock
    ctx["c_a"].patch(f"/items/{iid}", json={"description": "A owns this"})

    state_after_claim = _get_item_state(iid)
    assert state_after_claim["cutlist_owner_id"] == ctx["uid_a"]

    # Manager transfers to B
    c_mgr = _login_user(workspace_slug=ctx["slug"], email=email_mgr, password=pw_mgr)
    r = c_mgr.post(f"/items/{iid}/lock", json={"owner_id": uid_b})
    assert r.status_code == 200, (
        f"Manager should be able to force-transfer: {r.status_code}: {r.text}"
    )

    state_final = _get_item_state(iid)
    assert state_final["cutlist_owner_id"] == uid_b, (
        f"Expected owner=B after manager transfer, got {state_final['cutlist_owner_id']}"
    )


# ── Test 7 ─────────────────────────────────────────────────────────────────────


def test_lock_warning_in_get_item_response():
    """GET /items/{id} as non-owner of a locked item returns lock_warning with owner_name."""
    ctx = _setup_workspace_and_project(role_a="drafter")
    db = SessionLocal()
    try:
        uid_b, email_b, pw_b = _make_user(
            db,
            workspace_id=ctx["wid"],
            role="drafter",
            name="Drafter B Full Name",
        )
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=1007)
    finally:
        db.close()

    # B logs in and claims lock via POST /items/{id}/lock
    c_b = _login_user(workspace_slug=ctx["slug"], email=email_b, password=pw_b)
    r = c_b.post(f"/items/{iid}/lock")
    assert r.status_code == 200, r.text

    state = _get_item_state(iid)
    assert state["item_locked"] is True
    assert state["cutlist_owner_id"] == uid_b

    # A GETs the item — should see lock_warning pointing at B
    r2 = ctx["c_a"].get(f"/items/{iid}")
    assert r2.status_code == 200, r2.text
    item = r2.json()

    assert item["lock_warning"] is not None, "Non-owner should see lock_warning"
    lw = item["lock_warning"]
    assert lw["owner_id"] == uid_b
    assert lw["owner_name"] == "Drafter B Full Name"
    assert isinstance(lw["last_edit_minutes_ago"], int)


# ── Controlled Lock: request lifecycle (B7 / Q509) ────────────────────────────


def _locked_item_with_request(role_b: str = "drafter") -> dict:
    """A owns the lock on an item; B's save is held as a pending request."""
    ctx = _setup_workspace_and_project()
    db = SessionLocal()
    try:
        uid_b, email_b, pw_b = _make_user(
            db, workspace_id=ctx["wid"], role=role_b, name="Drafter B"
        )
        iid = _insert_unlocked_item(db, project_id=ctx["pid"], num=2001)
    finally:
        db.close()

    c_b = _login_user(workspace_slug=ctx["slug"], email=email_b, password=pw_b)
    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "A's edit"}).status_code == 200

    r = c_b.patch(f"/items/{iid}", json={"description": "B's proposal", "qty": 7})
    assert r.status_code == 409, r.text
    ctx.update(
        uid_b=uid_b, c_b=c_b, iid=iid, rid=r.json()["detail"]["request_id"]
    )
    return ctx


def _item_field(iid: int, col: str):
    db = SessionLocal()
    try:
        return db.execute(
            text(f"SELECT {col} FROM items WHERE item_id = :iid"), {"iid": iid}
        ).scalar()
    finally:
        db.close()


def test_resaving_revises_the_same_pending_request():
    """uniq_pending_lock_request: one live proposal per person, not a queue."""
    ctx = _locked_item_with_request()

    r = ctx["c_b"].patch(f"/items/{ctx['iid']}", json={"description": "B, second thoughts"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["request_id"] == ctx["rid"], "should revise, not create"

    rows = ctx["c_a"].get(f"/items/{ctx['iid']}/lock-requests?status=pending").json()
    assert len(rows) == 1
    assert rows[0]["requested_changes"] == {"description": "B, second thoughts"}, (
        "the latest proposal replaces the earlier one"
    )


def test_owner_approves_and_the_change_lands_credited_to_requester():
    ctx = _locked_item_with_request()

    r = ctx["c_a"].post(f"/lock-requests/{ctx['rid']}/approve", json={"note": "fine"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["decided_by"] == ctx["uid_a"]
    assert body["decision_note"] == "fine"

    assert _item_field(ctx["iid"], "description") == "B's proposal"
    assert _item_field(ctx["iid"], "qty") == 7
    # The lock does not move: approving is not handing the item over.
    assert _get_item_state(ctx["iid"])["cutlist_owner_id"] == ctx["uid_a"]

    db = SessionLocal()
    try:
        authors = {
            row[0]
            for row in db.execute(
                text("SELECT actor_id FROM item_edit_log WHERE item_id = :iid"),
                {"iid": ctx["iid"]},
            ).all()
        }
        approve_payload = db.execute(
            text(
                "SELECT payload FROM audit_log WHERE event = 'item.lock_request.approve'"
                " AND target = :t ORDER BY id DESC LIMIT 1"
            ),
            {"t": str(ctx["iid"])},
        ).scalar()
    finally:
        db.close()

    assert ctx["uid_b"] in authors, "the edit log credits the requester"
    assert approve_payload["requested_by"] == ctx["uid_b"]
    assert sorted(approve_payload["applied_fields"]) == ["description", "qty"]


def test_owner_rejects_and_the_item_is_untouched():
    ctx = _locked_item_with_request()

    r = ctx["c_a"].post(f"/lock-requests/{ctx['rid']}/reject", json={"note": "no"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"

    assert _item_field(ctx["iid"], "description") == "A's edit"
    assert _item_field(ctx["iid"], "qty") != 7


def test_manager_may_decide_but_an_unrelated_drafter_may_not():
    ctx = _locked_item_with_request()
    db = SessionLocal()
    try:
        _, email_c, pw_c = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter C"
        )
        _, email_m, pw_m = _make_user(
            db, workspace_id=ctx["wid"], role="manager", name="Manager M"
        )
    finally:
        db.close()

    c_c = _login_user(workspace_slug=ctx["slug"], email=email_c, password=pw_c)
    r = c_c.post(f"/lock-requests/{ctx['rid']}/approve")
    assert r.status_code == 403, f"a bystander must not decide: {r.text}"

    c_m = _login_user(workspace_slug=ctx["slug"], email=email_m, password=pw_m)
    r2 = c_m.post(f"/lock-requests/{ctx['rid']}/approve")
    assert r2.status_code == 200, r2.text
    assert _item_field(ctx["iid"], "description") == "B's proposal"


def test_deciding_twice_conflicts():
    ctx = _locked_item_with_request()
    assert ctx["c_a"].post(f"/lock-requests/{ctx['rid']}/approve").status_code == 200
    r = ctx["c_a"].post(f"/lock-requests/{ctx['rid']}/reject")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "ALREADY_DECIDED"


def test_lock_request_is_workspace_isolated():
    """A decider in another workspace cannot even see the request."""
    ctx = _locked_item_with_request()
    other = _setup_workspace_and_project(role_a="manager", project_name="Other Project")

    r = other["c_a"].post(f"/lock-requests/{ctx['rid']}/approve")
    assert r.status_code == 404, r.text
    assert _item_field(ctx["iid"], "description") == "A's edit"


def test_owner_save_still_applies_directly():
    """The lock only holds *other* people's saves."""
    ctx = _locked_item_with_request()
    r = ctx["c_a"].patch(f"/items/{ctx['iid']}", json={"description": "A again"})
    assert r.status_code == 200, r.text
    assert _item_field(ctx["iid"], "description") == "A again"
