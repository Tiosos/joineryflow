"""Tests for GET /procurement-queue (Procurement Workbench v1, Task 13).

Covers:
  - Cross-project rollup: 2 projects with 1 batch each -> 2 rows.
  - ?supplier=... filter (ILIKE).
  - ?status=IN_TRANSIT filter (matches derived status only).
"""
import uuid

from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login
from .conftest import truncate_fixture


_cleanup = truncate_fixture(
    "batch_allocations",
    "procurement_batches",
    "hardware_materials",
)


def _login(role: str = "manager"):
    return login(role, prefix="h")




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


# ── ETA filter (the home dashboard tiles link here) ──────────────────────────


def _seed_eta_batches(*, p1: int, mat: int) -> None:
    """Overdue, due-this-week, due-later, and received-but-late batches under one project."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO procurement_batches
                  (project_id, material_type, material_id, supplier, qty_ordered,
                   ordered_date, eta_date, received_date)
                VALUES
                  (:p, 'HARDWARE', :m, 'Late',   1, CURRENT_DATE - 9, CURRENT_DATE - 2, NULL),
                  (:p, 'HARDWARE', :m, 'Soon',   1, CURRENT_DATE,     CURRENT_DATE + 3, NULL),
                  (:p, 'HARDWARE', :m, 'Later',  1, CURRENT_DATE,     CURRENT_DATE + 30, NULL),
                  (:p, 'HARDWARE', :m, 'Landed', 1, CURRENT_DATE - 9, CURRENT_DATE - 2, CURRENT_DATE - 1)
                """
            ),
            {"p": p1, "m": mat},
        )
        db.commit()
    finally:
        db.close()


def test_queue_eta_filters_match_the_dashboard_tiles():
    """?eta=overdue / ?eta=this_week return exactly the batches the purchase officer's
    'Overdue Deliveries' / 'Deliveries This Week' tiles count (a received batch is neither)."""
    c, wid, uid = _login("purchase_officer")
    p1, _p2, mat = _seed_two_projects_one_material(wid=wid, uid=uid)
    _seed_eta_batches(p1=p1, mat=mat)

    overdue = c.get("/procurement-queue?eta=overdue").json()["rows"]
    this_week = c.get("/procurement-queue?eta=this_week").json()["rows"]
    assert [r["supplier"] for r in overdue] == ["Late"]
    assert [r["supplier"] for r in this_week] == ["Soon"]
    assert len(c.get("/procurement-queue").json()["rows"]) == 4

    tiles = {m["key"]: m for m in c.get("/home/dashboard").json()["metrics"]}
    assert tiles["overdue"]["value"] == len(overdue)
    assert tiles["deliveries_this_week"]["value"] == len(this_week)
    assert tiles["overdue"]["href"] == "/orderbook?tab=queue&eta=overdue"
    assert tiles["deliveries_this_week"]["href"] == "/orderbook?tab=queue&eta=this_week"


def test_queue_eta_rejects_an_unknown_value():
    c, _wid, _uid = _login("manager")
    assert c.get("/procurement-queue?eta=yesterday").status_code == 422
