"""Tests for §L close-out (Plan V1 §12, Q508/Q511/Q512):

- Hard Lock (Q508): blocks PATCH /items/{id} for everyone, including the
  owner, until a manager/admin clears it.
- Approval Lock (Q508): derived from items.status == 'APPROVED'; blocks
  PATCH /items/{id} until status moves away from APPROVED.
- Field-level optimistic concurrency (Q511/Q512) on the three named
  surfaces: item editor, cutlist, orders.

Uses the same truncate/seed/login helper patterns as test_lock_semantics.py.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

_STATUS_KEYS = [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4), ("APPROVED", 5)]
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
            "item_status_log",
            "po_line_items",
            "purchase_orders",
            "vendors",
            "cutlist",
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


def _make_user(db, *, workspace_id: int, role: str, name: str = "Test User"):
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


def _setup_workspace_and_project(role_a: str = "manager") -> dict:
    suffix = uuid.uuid4().hex[:8]
    slug = f"ws-{suffix}"
    db = SessionLocal()
    try:
        _seed_refs(db)
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'L WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid_a, email_a, pw_a = _make_user(db, workspace_id=wid, role=role_a, name="User A")
        pid = db.execute(
            text(
                "INSERT INTO projects(project_code, name, pm_id, workspace_id)"
                " VALUES(:code, :pname, :uid, :wid) RETURNING project_id"
            ),
            {"code": f"LP-{suffix}", "pname": "L Project", "uid": uid_a, "wid": wid},
        ).scalar()
        db.commit()
    finally:
        db.close()

    c_a = _login_user(workspace_slug=slug, email=email_a, password=pw_a)
    return {"wid": wid, "slug": slug, "uid_a": uid_a, "pid": pid, "c_a": c_a}


def _insert_item(db, *, project_id: int, num: int) -> int:
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code,
                              item_locked, cutlist_owner_id)
            VALUES (:num, :pid, 'CLEAR', 'L test item', 'LK-01', false, NULL)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id},
    ).scalar()
    db.commit()
    return iid


def _item_field(iid: int, col: str):
    db = SessionLocal()
    try:
        return db.execute(
            text(f"SELECT {col} FROM items WHERE item_id = :iid"), {"iid": iid}
        ).scalar()
    finally:
        db.close()


def _audit_events(target: str) -> list[str]:
    db = SessionLocal()
    try:
        return [
            row[0]
            for row in db.execute(
                text("SELECT event FROM audit_log WHERE target = :t ORDER BY id"),
                {"t": target},
            ).all()
        ]
    finally:
        db.close()


# ── Hard Lock (Q508) ──────────────────────────────────────────────────────────


def test_manager_can_hard_lock_and_it_blocks_everyone_including_owner():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3001)
    finally:
        db.close()

    # A claims ownership first
    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "A's edit"}).status_code == 200

    r = ctx["c_a"].post(f"/items/{iid}/hard-lock")
    assert r.status_code == 200, r.text
    assert r.json()["hard_locked_at"] is not None
    assert r.json()["hard_locked_by"] == ctx["uid_a"]

    # Even the owner (A) cannot PATCH while hard-locked.
    r2 = ctx["c_a"].patch(f"/items/{iid}", json={"description": "should not land"})
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"]["code"] == "HARD_LOCKED"
    assert _item_field(iid, "description") == "A's edit"

    assert "item.hard_lock" in _audit_events(str(iid))


def test_drafter_cannot_hard_lock():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        uid_d, email_d, pw_d = _make_user(
            db, workspace_id=ctx["wid"], role="drafter", name="Drafter D"
        )
        iid = _insert_item(db, project_id=ctx["pid"], num=3002)
    finally:
        db.close()

    c_d = _login_user(workspace_slug=ctx["slug"], email=email_d, password=pw_d)
    r = c_d.post(f"/items/{iid}/hard-lock")
    assert r.status_code == 403, r.text


def test_clearing_hard_lock_lets_patches_through_again():
    ctx = _setup_workspace_and_project(role_a="admin")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3003)
    finally:
        db.close()

    assert ctx["c_a"].post(f"/items/{iid}/hard-lock").status_code == 200
    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "x"}).status_code == 409

    r = ctx["c_a"].delete(f"/items/{iid}/hard-lock")
    assert r.status_code == 200, r.text
    assert r.json()["hard_locked_at"] is None
    assert r.json()["hard_locked_by"] is None

    r2 = ctx["c_a"].patch(f"/items/{iid}", json={"description": "now allowed"})
    assert r2.status_code == 200, r2.text
    assert _item_field(iid, "description") == "now allowed"
    assert "item.hard_unlock" in _audit_events(str(iid))


# ── Approval Lock (Q508) ──────────────────────────────────────────────────────


def test_setting_status_approved_locks_the_item():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3004)
    finally:
        db.close()

    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "before approval"}).status_code == 200

    r = ctx["c_a"].patch(f"/items/{iid}/status", json={"status": "APPROVED", "note": "signed off"})
    assert r.status_code == 200, r.text

    r2 = ctx["c_a"].patch(f"/items/{iid}", json={"description": "should not land"})
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"]["code"] == "APPROVAL_LOCKED"
    assert _item_field(iid, "description") == "before approval"

    assert "item.approval_lock" in _audit_events(str(iid))


def test_moving_status_away_from_approved_unlocks():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3005)
    finally:
        db.close()

    assert ctx["c_a"].patch(f"/items/{iid}/status", json={"status": "APPROVED", "note": "ok"}).status_code == 200
    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "x"}).status_code == 409

    r = ctx["c_a"].patch(f"/items/{iid}/status", json={"status": "LIVE", "note": "reopen"})
    assert r.status_code == 200, r.text

    r2 = ctx["c_a"].patch(f"/items/{iid}", json={"description": "now allowed"})
    assert r2.status_code == 200, r2.text
    assert _item_field(iid, "description") == "now allowed"
    assert "item.approval_unlock" in _audit_events(str(iid))


# ── Field-level optimistic concurrency: items (Q511/Q512) ────────────────────


def test_item_patch_without_expected_versions_is_unaffected():
    """Omitting expected_versions keeps last-write-wins — every pre-existing caller."""
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3006)
    finally:
        db.close()

    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "first"}).status_code == 200
    r = ctx["c_a"].patch(f"/items/{iid}", json={"description": "second"})
    assert r.status_code == 200, r.text
    assert _item_field(iid, "description") == "second"


def test_item_stale_expected_version_is_a_field_conflict():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3007)
    finally:
        db.close()

    # First write bumps description's version to 1.
    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "v1"}).status_code == 200

    # A second write believing description is still at version 0 conflicts.
    r = ctx["c_a"].patch(
        f"/items/{iid}",
        json={"description": "v2 based on stale read", "expected_versions": {"description": 0}},
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "FIELD_CONFLICT"
    assert detail["conflicts"]["description"]["expected"] == 0
    assert detail["conflicts"]["description"]["current"] == 1
    assert detail["conflicts"]["description"]["current_value"] == "v1"
    assert _item_field(iid, "description") == "v1", "the stale write must not land"


def test_item_correct_expected_version_succeeds_and_bumps_again():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3008)
    finally:
        db.close()

    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "v1"}).status_code == 200
    r = ctx["c_a"].get(f"/items/{iid}")
    version = r.json()["field_versions"]["description"]
    assert version == 1

    r2 = ctx["c_a"].patch(
        f"/items/{iid}",
        json={"description": "v2", "expected_versions": {"description": version}},
    )
    assert r2.status_code == 200, r2.text
    assert _item_field(iid, "description") == "v2"
    assert r2.json()["field_versions"]["description"] == 2


def test_item_conflict_on_one_field_does_not_block_a_different_field():
    """Q366: only the genuinely conflicting field blocks — different fields
    edited concurrently never collide."""
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        iid = _insert_item(db, project_id=ctx["pid"], num=3009)
    finally:
        db.close()

    assert ctx["c_a"].patch(f"/items/{iid}", json={"description": "d1"}).status_code == 200

    # Editing `qty` with a correct (zero) expected version for qty succeeds,
    # even though description has already moved past version 0.
    r = ctx["c_a"].patch(
        f"/items/{iid}",
        json={"qty": 5, "expected_versions": {"qty": 0}},
    )
    assert r.status_code == 200, r.text
    assert _item_field(iid, "qty") == 5


# ── Field-level optimistic concurrency: cutlist (Q511/Q512) ──────────────────


def _insert_cutlist(db, *, project_id: int, actor_id: int) -> int:
    cid = db.execute(
        text(
            "INSERT INTO cutlist(project_id, cutlist_no, name, created_by)"
            " VALUES (:p, 900101, 'Original name', :a) RETURNING cutlist_id"
        ),
        {"p": project_id, "a": actor_id},
    ).scalar()
    db.commit()
    return cid


def test_cutlist_stale_expected_version_is_a_field_conflict():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        cid = _insert_cutlist(db, project_id=ctx["pid"], actor_id=ctx["uid_a"])
    finally:
        db.close()

    assert ctx["c_a"].patch(f"/cutlists/{cid}", json={"name": "Renamed once"}).status_code == 200

    r = ctx["c_a"].patch(
        f"/cutlists/{cid}", json={"name": "Stale rename", "expected_versions": {"name": 0}}
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "FIELD_CONFLICT"
    assert detail["conflicts"]["name"]["current_value"] == "Renamed once"


def test_cutlist_correct_expected_version_succeeds():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        cid = _insert_cutlist(db, project_id=ctx["pid"], actor_id=ctx["uid_a"])
    finally:
        db.close()

    r0 = ctx["c_a"].get(f"/cutlists/{cid}")
    version = r0.json()["field_versions"].get("name", 0)

    r = ctx["c_a"].patch(
        f"/cutlists/{cid}", json={"name": "Renamed", "expected_versions": {"name": version}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"


# ── Field-level optimistic concurrency: orders (Q511/Q512) ───────────────────


def _insert_vendor(db, *, workspace_id: int) -> int:
    vid = db.execute(
        text(
            "INSERT INTO vendors(workspace_id, name, category)"
            " VALUES (:w, 'Test Vendor', 'Board') RETURNING vendor_id"
        ),
        {"w": workspace_id},
    ).scalar()
    db.commit()
    return vid


def _create_order(client: TestClient, *, vendor_id: int) -> int:
    r = client.post(
        "/orders",
        json={"vendor_id": vendor_id, "description": "Order desc", "category": "Board"},
    )
    assert r.status_code == 201, r.text
    return r.json()["po_id"]


def test_order_stale_expected_version_is_a_field_conflict():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        vid = _insert_vendor(db, workspace_id=ctx["wid"])
    finally:
        db.close()
    po_id = _create_order(ctx["c_a"], vendor_id=vid)

    assert ctx["c_a"].patch(f"/orders/{po_id}", json={"description": "v1"}).status_code == 200

    r = ctx["c_a"].patch(
        f"/orders/{po_id}",
        json={"description": "stale v2", "expected_versions": {"description": 0}},
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "FIELD_CONFLICT"
    assert detail["conflicts"]["description"]["current_value"] == "v1"


def test_order_correct_expected_version_succeeds():
    ctx = _setup_workspace_and_project(role_a="manager")
    db = SessionLocal()
    try:
        vid = _insert_vendor(db, workspace_id=ctx["wid"])
    finally:
        db.close()
    po_id = _create_order(ctx["c_a"], vendor_id=vid)

    assert ctx["c_a"].patch(f"/orders/{po_id}", json={"description": "v1"}).status_code == 200
    version = ctx["c_a"].get(f"/orders/{po_id}").json()["field_versions"]["description"]

    r = ctx["c_a"].patch(
        f"/orders/{po_id}",
        json={"description": "v2", "expected_versions": {"description": version}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "v2"
