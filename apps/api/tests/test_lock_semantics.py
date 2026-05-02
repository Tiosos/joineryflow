"""Tests for soft-lock semantics on items (spec §6.4, T15 Step 4).

7 test cases covering:
  - First-save claim (unlocked + unowned item gets claimed on PATCH)
  - Lock-overridden audit (non-owner PATCH emits audit row, doesn't steal lock)
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


def _setup_workspace_and_project(role_a: str = "drafter") -> dict:
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
                " VALUES(:code, 'Lock Project', :uid, :wid) RETURNING project_id"
            ),
            {"code": f"LP-{suffix}", "uid": uid_a, "wid": wid},
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


def test_second_save_by_other_writes_lock_overridden_audit():
    """Non-owner PATCH succeeds but emits audit row 'item.lock_overridden'; lock stays with A."""
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

    state_after_a = _get_item_state(iid)
    assert state_after_a["cutlist_owner_id"] == ctx["uid_a"]

    # B patches → should succeed (200), not 403
    r2 = c_b.patch(f"/items/{iid}", json={"description": "B edits despite lock"})
    assert r2.status_code == 200, (
        f"Non-owner PATCH should succeed (200), got {r2.status_code}: {r2.text}"
    )

    # Audit log must have item.lock_overridden row
    db2 = SessionLocal()
    try:
        audit_row = db2.execute(
            text(
                """
                SELECT payload FROM audit_log
                WHERE event = 'item.lock_overridden'
                  AND target = :target
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"target": str(iid)},
        ).mappings().first()
    finally:
        db2.close()

    assert audit_row is not None, "Expected an 'item.lock_overridden' audit row"
    payload = audit_row["payload"]
    assert payload["prior_owner_id"] == ctx["uid_a"]
    assert payload["new_owner_id"] == uid_b

    # Lock still belongs to A (not stolen)
    state_final = _get_item_state(iid)
    assert state_final["cutlist_owner_id"] == ctx["uid_a"], (
        "owner should remain A after B's override"
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
