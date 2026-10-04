"""Tests for /batches CRUD endpoints (Procurement Workbench v1, Task 7).

Covers:
  - POST /batches happy path: status='OPEN' when only qty_ordered set.
  - PATCH /batches/{bid}: setting ordered_date flips derived status to 'IN_TRANSIT'.
  - DELETE /batches/{bid}: soft-cancels; subsequent GET shows status='CANCELLED'.
  - POST /batches with unknown project_id -> 404.
"""

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login
from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        extra = (
            "batch_allocations",
            "procurement_batches",
            "hardware_materials",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


# Reference data for FK constraints on items and item_stages




def _login(role: str = "manager"):
    return login(role, prefix="h")




def _seed_project_and_material(*, wid: int, uid: int) -> tuple[int, int]:
    """Insert a project (pm_id=uid) and a hardware material; return (pid, mat_id)."""
    db = SessionLocal()
    try:
        pid = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id, workspace_id)
                VALUES ('P1', 'P', :u, :w)
                RETURNING project_id
                """
            ),
            {"u": uid, "w": wid},
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
        db.commit()
    finally:
        db.close()
    return pid, mat_id


# ── Test cases ────────────────────────────────────────────────────────────────


def test_create_batch():
    """POST /batches creates an OPEN batch when only qty_ordered is set."""
    c, wid, uid = _login("manager")
    pid, mat_id = _seed_project_and_material(wid=wid, uid=uid)

    r = c.post(
        "/batches",
        json={
            "project_id": pid,
            "material_type": "HARDWARE",
            "material_id": mat_id,
            "supplier": "Acme",
            "po_ref": "PO-001",
            "qty_ordered": 10,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "OPEN"
    assert body["supplier"] == "Acme"
    assert body["po_ref"] == "PO-001"
    assert float(body["qty_ordered"]) == 10
    assert float(body["qty_received"]) == 0
    assert float(body["qty_allocated"]) == 0
    assert body["cancelled_at"] is None


def test_patch_batch_marks_in_transit():
    """PATCH ordered_date flips derived status to 'IN_TRANSIT'."""
    c, wid, uid = _login("manager")
    pid, mat_id = _seed_project_and_material(wid=wid, uid=uid)
    bid = c.post(
        "/batches",
        json={
            "project_id": pid,
            "material_type": "HARDWARE",
            "material_id": mat_id,
            "qty_ordered": 10,
        },
    ).json()["batch_id"]

    r = c.patch(f"/batches/{bid}", json={"ordered_date": "2026-04-01"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "IN_TRANSIT"
    assert r.json()["ordered_date"] == "2026-04-01"


def test_soft_cancel_batch():
    """DELETE soft-cancels; GET returns status='CANCELLED'."""
    c, wid, uid = _login("manager")
    pid, mat_id = _seed_project_and_material(wid=wid, uid=uid)
    bid = c.post(
        "/batches",
        json={
            "project_id": pid,
            "material_type": "HARDWARE",
            "material_id": mat_id,
            "qty_ordered": 10,
        },
    ).json()["batch_id"]

    r = c.delete(f"/batches/{bid}")
    assert r.status_code == 204

    g = c.get(f"/batches/{bid}")
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["status"] == "CANCELLED"
    assert body["cancelled_at"] is not None


def test_create_batch_404_for_unknown_project():
    """Unknown project_id yields 404 (workspace-scoped get_project miss)."""
    c, wid, uid = _login("manager")
    _, mat_id = _seed_project_and_material(wid=wid, uid=uid)

    r = c.post(
        "/batches",
        json={
            "project_id": 999999,
            "material_type": "HARDWARE",
            "material_id": mat_id,
            "qty_ordered": 1,
        },
    )
    assert r.status_code == 404


def test_soft_cancel_blocked_when_allocations_exist():
    """DELETE /batches/{bid} returns 409 when batch has allocations with qty_allocated > 0."""
    c, wid, uid = _login("manager")
    pid, mat_id = _seed_project_and_material(wid=wid, uid=uid)

    # Create a batch
    batch_resp = c.post(
        "/batches",
        json={
            "project_id": pid,
            "material_type": "HARDWARE",
            "material_id": mat_id,
            "supplier": "Acme",
            "po_ref": "PO-ALLOC-001",
            "qty_ordered": 20,
        },
    )
    assert batch_resp.status_code == 201, batch_resp.text
    bid = batch_resp.json()["batch_id"]

    # Seed database helpers for items and allocations
    db = SessionLocal()
    try:
        # Create a project hardware catalog entry (FK for item_hardware_lines)
        cat_id = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog
                    (project_id, material_type, material_id, added_by)
                VALUES (:pid, 'HARDWARE', :mid, :uid)
                RETURNING catalog_id
                """
            ),
            {"pid": pid, "mid": mat_id, "uid": uid},
        ).scalar()

        # Create an item
        iid = db.execute(
            text(
                """
                INSERT INTO items(num, project_id, status, description, code, item_locked)
                VALUES (1, :pid, 'CLEAR', 'Test item for alloc', 'TEST-01', false)
                RETURNING item_id
                """
            ),
            {"pid": pid},
        ).scalar()

        # Create an item hardware line
        line_id = db.execute(
            text(
                """
                INSERT INTO item_hardware_lines(item_id, qty, catalog_id)
                VALUES (:iid, 5, :cid)
                RETURNING line_id
                """
            ),
            {"iid": iid, "cid": cat_id},
        ).scalar()

        # Create an allocation with qty_allocated > 0
        db.execute(
            text(
                """
                INSERT INTO batch_allocations
                    (batch_id, item_hardware_line_id, qty_allocated)
                VALUES (:bid, :lid, 3)
                """
            ),
            {"bid": bid, "lid": line_id},
        )
        db.commit()
    finally:
        db.close()

    # Attempt DELETE — should fail with 409 and mention "alloc"
    r = c.delete(f"/batches/{bid}")
    assert r.status_code == 409, r.text
    body = r.json()
    assert "alloc" in body.get("detail", "").lower()
