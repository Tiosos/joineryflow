"""Tests for GET /procurement-queue (Procurement Workbench v1, Task 13).

Covers:
  - Cross-project rollup: 2 projects with 1 batch each -> 2 rows.
  - ?supplier=... filter (ILIKE).
  - ?status=IN_TRANSIT filter (matches derived status only).
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
            "hardware_materials",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _login(role: str = "manager"):
    """Create a fresh workspace + user, log in, return (client, wid, uid)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
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


def _seed_two_projects_one_material(*, wid: int, uid: int) -> tuple[int, int, int]:
    """Insert 2 projects (pm_id=uid) and a hardware material; return (p1, p2, mat)."""
    db = SessionLocal()
    try:
        p1 = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id, workspace_id)
                VALUES ('P1', 'P1', :u, :w)
                RETURNING project_id
                """
            ),
            {"u": uid, "w": wid},
        ).scalar()
        p2 = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id, workspace_id)
                VALUES ('P2', 'P2', :u, :w)
                RETURNING project_id
                """
            ),
            {"u": uid, "w": wid},
        ).scalar()
        # `sku` is a NOT NULL legacy column with a global UNIQUE; uuid suffix
        # avoids collisions with seed data left over from prior tests.
        sku_suffix = uuid.uuid4().hex[:8]
        mat = db.execute(
            text(
                """
                INSERT INTO hardware_materials(sku, description, workspace_id)
                VALUES (:sku, 'X', :w)
                RETURNING material_id
                """
            ),
            {"sku": f"SKU-{sku_suffix}", "w": wid},
        ).scalar()
        db.commit()
    finally:
        db.close()
    return p1, p2, mat


def _seed_two_batches(*, p1: int, p2: int, mat: int) -> None:
    """Insert one IN_TRANSIT batch per project, one Acme + one Bravo."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO procurement_batches
                  (project_id, material_type, material_id, supplier,
                   qty_ordered, ordered_date, eta_date)
                VALUES
                  (:p1, 'HARDWARE', :m, 'Acme',  5, CURRENT_DATE, CURRENT_DATE + 7),
                  (:p2, 'HARDWARE', :m, 'Bravo', 3, CURRENT_DATE, CURRENT_DATE + 14)
                """
            ),
            {"p1": p1, "p2": p2, "m": mat},
        )
        db.commit()
    finally:
        db.close()


# ── Test cases ────────────────────────────────────────────────────────────────


def test_queue_lists_both_projects():
    """GET /procurement-queue returns 1 row per batch across all workspace projects."""
    c, wid, uid = _login("manager")
    p1, p2, mat = _seed_two_projects_one_material(wid=wid, uid=uid)
    _seed_two_batches(p1=p1, p2=p2, mat=mat)

    r = c.get("/procurement-queue")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["rows"]) == 2
    assert {row["supplier"] for row in body["rows"]} == {"Acme", "Bravo"}


def test_queue_filter_by_supplier():
    """?supplier=Acme returns only the Acme batch."""
    c, wid, uid = _login("manager")
    p1, p2, mat = _seed_two_projects_one_material(wid=wid, uid=uid)
    _seed_two_batches(p1=p1, p2=p2, mat=mat)

    r = c.get("/procurement-queue?supplier=Acme")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["supplier"] == "Acme"


def test_queue_filter_by_status():
    """?status=IN_TRANSIT returns only IN_TRANSIT batches; OPEN excluded."""
    c, wid, uid = _login("manager")
    p1, p2, mat = _seed_two_projects_one_material(wid=wid, uid=uid)
    _seed_two_batches(p1=p1, p2=p2, mat=mat)

    # Add a third OPEN batch (no ordered_date) under p1; should be excluded.
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO procurement_batches
                  (project_id, material_type, material_id, supplier, qty_ordered)
                VALUES (:p, 'HARDWARE', :m, 'Charlie', 2)
                """
            ),
            {"p": p1, "m": mat},
        )
        db.commit()
    finally:
        db.close()

    r = c.get("/procurement-queue?status=IN_TRANSIT")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["rows"]) == 2
    assert all(row["status"] == "IN_TRANSIT" for row in body["rows"])
