"""Tests for /batches/{bid}/allocations CRUD endpoints (Procurement Workbench v1, Task 9).

Covers:
  - POST /batches/{bid}/allocations within capacity -> 201.
  - POST that would exceed capacity -> 409 with "exceed" in detail.
  - PATCH /allocations/{aid} that would exceed capacity -> 409.
  - DELETE /allocations/{aid} releases capacity for re-allocation.
  - Cross-project line is rejected -> 400.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES


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


# Reference data for FK constraints on items and item_stages
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
    """Create a fresh workspace + user, log in, return (client, wid, uid)."""
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


def _seed_alloc_setup(*, wid: int, uid: int) -> dict:
    """Seed a project + material + catalog + item + hardware line + batch.

    Batch has qty_ordered=5 and qty_received=5 (so effective capacity = 5).
    """
    db = SessionLocal()
    try:
        pid = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id)
                VALUES ('P1', 'P', :u)
                RETURNING project_id
                """
            ),
            {"u": uid},
        ).scalar()
        mat_id = db.execute(
            text(
                """
                INSERT INTO hardware_materials(description, sku, workspace_id)
                VALUES ('Hinge', 'H-100', :w)
                RETURNING material_id
                """
            ),
            {"w": wid},
        ).scalar()
        cat_id = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog
                    (project_id, material_type, material_id, added_by)
                VALUES (:p, 'HARDWARE', :m, :u)
                RETURNING catalog_id
                """
            ),
            {"p": pid, "m": mat_id, "u": uid},
        ).scalar()
        item_id = db.execute(
            text(
                """
                INSERT INTO items(num, project_id, status, description, code, item_locked)
                VALUES (1, :p, 'CLEAR', 'Test item', 'TEST-01', false)
                RETURNING item_id
                """
            ),
            {"p": pid},
        ).scalar()
        line_id = db.execute(
            text(
                """
                INSERT INTO item_hardware_lines(item_id, qty, catalog_id)
                VALUES (:i, 5, :c)
                RETURNING line_id
                """
            ),
            {"i": item_id, "c": cat_id},
        ).scalar()
        bid = db.execute(
            text(
                """
                INSERT INTO procurement_batches
                    (project_id, material_type, material_id,
                     qty_ordered, qty_received, received_date)
                VALUES (:p, 'HARDWARE', :m, 5, 5, CURRENT_DATE)
                RETURNING batch_id
                """
            ),
            {"p": pid, "m": mat_id},
        ).scalar()
        db.commit()
    finally:
        db.close()
    return {
        "project_id":  pid,
        "material_id": mat_id,
        "catalog_id":  cat_id,
        "item_id":     item_id,
        "line_id":     line_id,
        "batch_id":    bid,
    }


# ── Test cases ────────────────────────────────────────────────────────────────


def test_create_allocation_within_capacity():
    """POST creates an allocation when qty fits within batch capacity."""
    c, wid, uid = _login("manager")
    s = _seed_alloc_setup(wid=wid, uid=uid)

    r = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 3},
    )
    assert r.status_code == 201, r.text
    assert float(r.json()["qty_allocated"]) == 3


def test_over_commit_returns_409():
    """A second POST that would push qty_allocated over capacity returns 409."""
    c, wid, uid = _login("manager")
    s = _seed_alloc_setup(wid=wid, uid=uid)

    first = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 4},
    )
    assert first.status_code == 201, first.text

    r = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 2},
    )
    assert r.status_code == 409, r.text
    assert "exceed" in r.json()["detail"].lower()


def test_patch_allocation_capacity_check():
    """PATCH that would push qty over capacity returns 409."""
    c, wid, uid = _login("manager")
    s = _seed_alloc_setup(wid=wid, uid=uid)

    aid = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 2},
    ).json()["allocation_id"]

    r = c.patch(f"/allocations/{aid}", json={"qty_allocated": 99})
    assert r.status_code == 409, r.text


def test_delete_allocation_releases_capacity():
    """DELETE frees capacity so the same qty can be re-allocated."""
    c, wid, uid = _login("manager")
    s = _seed_alloc_setup(wid=wid, uid=uid)

    aid = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 5},
    ).json()["allocation_id"]
    assert c.delete(f"/allocations/{aid}").status_code == 204

    r = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 5},
    )
    assert r.status_code == 201, r.text


def test_cross_project_line_rejected():
    """A line from a different project cannot be allocated to this batch."""
    c, wid, uid = _login("manager")
    s = _seed_alloc_setup(wid=wid, uid=uid)

    db = SessionLocal()
    try:
        other_pid = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id)
                VALUES ('P2', 'P2', :u)
                RETURNING project_id
                """
            ),
            {"u": uid},
        ).scalar()
        other_cat = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog
                    (project_id, material_type, material_id, added_by)
                VALUES (:p, 'HARDWARE', :m, :u)
                RETURNING catalog_id
                """
            ),
            {"p": other_pid, "m": s["material_id"], "u": uid},
        ).scalar()
        other_item = db.execute(
            text(
                """
                INSERT INTO items(num, project_id, status, description, code, item_locked)
                VALUES (2, :p, 'CLEAR', 'Other item', 'OTHER-01', false)
                RETURNING item_id
                """
            ),
            {"p": other_pid},
        ).scalar()
        other_line = db.execute(
            text(
                """
                INSERT INTO item_hardware_lines(item_id, qty, catalog_id)
                VALUES (:i, 1, :c)
                RETURNING line_id
                """
            ),
            {"i": other_item, "c": other_cat},
        ).scalar()
        db.commit()
    finally:
        db.close()

    r = c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": other_line, "qty_allocated": 1},
    )
    assert r.status_code == 400, r.text


def test_allocation_list_summary():
    """GET /batches/{bid}/allocations returns summary qty_received/allocated_total/remaining."""
    c, wid, uid = _login("manager")
    s = _seed_alloc_setup(wid=wid, uid=uid)

    # POST 1 allocation with qty=3
    c.post(
        f"/batches/{s['batch_id']}/allocations",
        json={"item_hardware_line_id": s["line_id"], "qty_allocated": 3},
    )

    # GET the batch allocations list
    r = c.get(f"/batches/{s['batch_id']}/allocations")
    assert r.status_code == 200, r.text
    body = r.json()

    # Verify summary fields
    assert float(body["qty_received"]) == 5
    assert float(body["qty_allocated_total"]) == 3
    assert float(body["qty_remaining"]) == 2
    assert len(body["allocations"]) == 1
    assert body["allocations"][0]["item_description"] == "Test item"
