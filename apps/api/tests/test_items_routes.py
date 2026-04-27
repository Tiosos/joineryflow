"""Tests for GET /projects/{pid}/items (tracking grid feed).

Uses the autouse-TRUNCATE pattern from test_projects_routes.py.
Raw SQL inserts bypass the route layer (no item-write API exists yet).

Reference table seeding required before inserting items:
  - status_options: items.status FK target (empty after migrations)
  - stages: item_stages.stage_key FK target (empty after migrations)
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

# Reference data needed for FK constraints on items and item_stages
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
        # TRUNCATE items-module tables plus the full TRUNCATE_TABLES list.
        # status_options and stages are reference tables seeded per-test;
        # they must be truncated last (after items/item_stages that FK into them).
        extra = (
            "batch_allocations",
            "procurement_batches",
            "item_stages",
            "item_hardware_lines",
            "project_hardware_catalog",
            "items",
            "status_options",
            "stages",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(
            text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE")
        )
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


def _login(role: str = "manager"):
    """Create a fresh workspace + user, seed reference rows, return (client, wid, uid)."""
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
    """Insert a project scoped to the given workspace via pm_id and return project_id."""
    pid = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id)
            VALUES (:code, 'Test Project', :uid)
            RETURNING project_id
            """
        ),
        {"code": code, "uid": uid},
    ).scalar()
    db.commit()
    return pid


def _insert_item(
    db,
    *,
    project_id: int,
    num: int,
    status: str = "CLEAR",
    description: str = "Test item",
    code: str = "CAB-01",
) -> int:
    """Insert a bare item and return item_id."""
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code, item_locked)
            VALUES (:num, :pid, :status, :desc, :code, false)
            RETURNING item_id
            """
        ),
        {
            "num": num,
            "pid": project_id,
            "status": status,
            "desc": description,
            "code": code,
        },
    ).scalar()
    db.commit()
    return iid


# ── Test cases ─────────────────────────────────────────────────────────────────


def test_empty_project_returns_empty_items():
    """A project with no items returns project_id and an empty items list."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/items")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["items"] == []


def test_grid_pivots_stages():
    """item_stages rows are pivoted into a stages dict keyed by stage_key."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=1)
        # REQ: done; SM: due only; LISTED: both due and done
        db.execute(
            text(
                """
                INSERT INTO item_stages(item_id, stage_key, due_date, done_date)
                VALUES
                  (:iid, 'REQ',    '2026-04-01', '2026-04-05'),
                  (:iid, 'SM',     '2026-05-01', NULL),
                  (:iid, 'LISTED', '2026-05-10', '2026-05-12')
                """
            ),
            {"iid": iid},
        )
        db.commit()
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    stages = items[0]["stages"]
    assert set(stages.keys()) == {"REQ", "SM", "LISTED"}
    assert stages["REQ"]["due_date"] == "2026-04-01"
    assert stages["REQ"]["done_date"] == "2026-04-05"
    assert stages["SM"]["due_date"] == "2026-05-01"
    assert stages["SM"]["done_date"] is None
    assert stages["LISTED"]["done_date"] == "2026-05-12"


def test_status_filter():
    """?status=X returns only items whose status matches exactly."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        _insert_item(db, project_id=pid, num=1, status="CLEAR", description="Clear item")
        _insert_item(db, project_id=pid, num=2, status="HOLD", description="Hold item")
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/items", params={"status": "HOLD"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "HOLD"
    assert items[0]["description"] == "Hold item"


def test_search_filter():
    """?q=substring matches description or code case-insensitively."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        _insert_item(db, project_id=pid, num=1, description="Base cabinet unit", code="BC-01")
        _insert_item(db, project_id=pid, num=2, description="Wall shelf bracket", code="WS-02")
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/items", params={"q": "cabinet"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["description"] == "Base cabinet unit"


def test_cross_workspace_404():
    """Workspace B cannot access workspace A's project — must get 404."""
    c_a, wid_a, uid_a = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid_a, uid=uid_a, code="WS-A-001")
    finally:
        db.close()

    c_b, _wid_b, _uid_b = _login()
    r = c_b.get(f"/projects/{pid}/items")
    assert r.status_code == 404


def test_availability_rollup_counts_lines():
    """ready = lines with an allocation; blocked = lines without any allocation."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=1)

        # project_hardware_catalog entry (required FK for item_hardware_lines)
        cat_id = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog
                    (project_id, material_type, material_id, added_by)
                VALUES (:pid, 'HARDWARE', 1, :uid)
                RETURNING catalog_id
                """
            ),
            {"pid": pid, "uid": uid},
        ).scalar()

        # Two hardware lines on the item
        line1_id = db.execute(
            text(
                """
                INSERT INTO item_hardware_lines(item_id, qty, catalog_id)
                VALUES (:iid, 1, :cid)
                RETURNING line_id
                """
            ),
            {"iid": iid, "cid": cat_id},
        ).scalar()
        db.execute(
            text(
                """
                INSERT INTO item_hardware_lines(item_id, qty, catalog_id)
                VALUES (:iid, 2, :cid)
                RETURNING line_id
                """
            ),
            {"iid": iid, "cid": cat_id},
        )

        # One procurement batch
        batch_id = db.execute(
            text(
                """
                INSERT INTO procurement_batches
                    (project_id, material_type, material_id, qty_ordered)
                VALUES (:pid, 'HARDWARE', 1, 5)
                RETURNING batch_id
                """
            ),
            {"pid": pid},
        ).scalar()

        # Allocate only line1 — line2 remains unallocated (blocked)
        db.execute(
            text(
                """
                INSERT INTO batch_allocations
                    (batch_id, item_hardware_line_id, qty_allocated)
                VALUES (:bid, :lid, 1)
                """
            ),
            {"bid": batch_id, "lid": line1_id},
        )
        db.commit()
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    avail = items[0]["availability"]
    assert avail["ready"] == 1
    assert avail["blocked"] == 1


def test_availability_rollup_dedups_split_allocations():
    """A hardware line with 2 batch_allocations rows must count as 1 ready, not 2."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=1)

        # project_hardware_catalog entry
        cat_id = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog
                    (project_id, material_type, material_id, added_by)
                VALUES (:pid, 'HARDWARE', 1, :uid)
                RETURNING catalog_id
                """
            ),
            {"pid": pid, "uid": uid},
        ).scalar()

        # One hardware line on the item
        line_id = db.execute(
            text(
                """
                INSERT INTO item_hardware_lines(item_id, qty, catalog_id)
                VALUES (:iid, 2, :cid)
                RETURNING line_id
                """
            ),
            {"iid": iid, "cid": cat_id},
        ).scalar()

        # Two procurement batches (split shipments)
        batch_id_1 = db.execute(
            text(
                """
                INSERT INTO procurement_batches
                    (project_id, material_type, material_id, qty_ordered)
                VALUES (:pid, 'HARDWARE', 1, 3)
                RETURNING batch_id
                """
            ),
            {"pid": pid},
        ).scalar()
        batch_id_2 = db.execute(
            text(
                """
                INSERT INTO procurement_batches
                    (project_id, material_type, material_id, qty_ordered)
                VALUES (:pid, 'HARDWARE', 1, 2)
                RETURNING batch_id
                """
            ),
            {"pid": pid},
        ).scalar()

        # Allocate the same line from two different batches (split delivery)
        db.execute(
            text(
                """
                INSERT INTO batch_allocations
                    (batch_id, item_hardware_line_id, qty_allocated)
                VALUES (:bid1, :lid, 1), (:bid2, :lid, 1)
                """
            ),
            {"bid1": batch_id_1, "bid2": batch_id_2, "lid": line_id},
        )
        db.commit()
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    avail = items[0]["availability"]
    assert avail["ready"] == 1, f"Expected ready=1, got {avail['ready']} (bug: COUNT(*) double-counts split allocations)"
    assert avail["blocked"] == 0
