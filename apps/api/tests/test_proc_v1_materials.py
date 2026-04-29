"""Tests for GET /projects/{pid}/materials (procurement v1 rollup).

Covers:
  - happy-path rollup (1 hardware material, demand=5, on-order=4, received=3,
    allocated=2, shortfall=0 -> status OK).
  - 404 for unknown project_id.
  - workspace isolation: project owned by workspace B is invisible to a user
    logged into workspace A (gets 404 from get_project's pm_id workspace filter).
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


def _seed_golden_project(db, *, wid: int, uid: int) -> int:
    """Create a project with one hardware material, one catalog row, one item,
    one hardware line (qty=5), one delivered batch (qty_ordered=3, qty_received=3),
    one in-transit batch (qty_ordered=4), one allocation (qty_allocated=2 against
    the delivered batch). Returns the project_id.
    """
    pid = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id)
            VALUES ('HJ-001', 'Test Project', :uid)
            RETURNING project_id
            """
        ),
        {"uid": uid},
    ).scalar()

    # Hardware material (catalog table — workspace_id is set per migration 0007).
    mat_id = db.execute(
        text(
            """
            INSERT INTO hardware_materials(sku, description, workspace_id, unit_cost)
            VALUES ('DS-500', 'Drawer slide 500mm', :w, 12.50)
            RETURNING material_id
            """
        ),
        {"w": wid},
    ).scalar()

    # Project-scoped catalog link
    cat_id = db.execute(
        text(
            """
            INSERT INTO project_hardware_catalog(project_id, material_type, material_id, added_by)
            VALUES (:p, 'HARDWARE', :m, :u)
            RETURNING catalog_id
            """
        ),
        {"p": pid, "m": mat_id, "u": uid},
    ).scalar()

    # Item
    item_id = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code, item_locked)
            VALUES (1, :p, 'CLEAR', 'Test item', 'CAB-01', false)
            RETURNING item_id
            """
        ),
        {"p": pid},
    ).scalar()

    # Hardware line: demand qty = 5
    line_id = db.execute(
        text(
            """
            INSERT INTO item_hardware_lines(item_id, seq, qty, catalog_id)
            VALUES (:i, 1, 5, :c)
            RETURNING line_id
            """
        ),
        {"i": item_id, "c": cat_id},
    ).scalar()

    # Delivered batch: qty_ordered=3, qty_received=3, received_date set
    delivered_batch_id = db.execute(
        text(
            """
            INSERT INTO procurement_batches(
                project_id, material_type, material_id,
                supplier, qty_ordered, qty_received,
                ordered_date, received_date
            )
            VALUES (:p, 'HARDWARE', :m, 'Acme', 3, 3,
                    DATE '2026-04-01', DATE '2026-04-10')
            RETURNING batch_id
            """
        ),
        {"p": pid, "m": mat_id},
    ).scalar()

    # In-transit batch: qty_ordered=4, no received_date, no cancelled_at
    db.execute(
        text(
            """
            INSERT INTO procurement_batches(
                project_id, material_type, material_id,
                supplier, qty_ordered, qty_received,
                ordered_date, eta_date
            )
            VALUES (:p, 'HARDWARE', :m, 'Acme', 4, 0,
                    DATE '2026-04-15', DATE '2026-05-15')
            """
        ),
        {"p": pid, "m": mat_id},
    )

    # Allocation: qty_allocated=2 against the delivered batch
    db.execute(
        text(
            """
            INSERT INTO batch_allocations(batch_id, item_hardware_line_id, qty_allocated)
            VALUES (:b, :l, 2)
            """
        ),
        {"b": delivered_batch_id, "l": line_id},
    )

    db.commit()
    return pid


# ── Test cases ────────────────────────────────────────────────────────────────


def test_project_materials_rollup():
    """Happy path: rollup aggregates demand, batches, and allocations."""
    c, wid, uid = _login("manager")
    db = SessionLocal()
    try:
        pid = _seed_golden_project(db, wid=wid, uid=uid)
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/materials")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["material_type"] == "HARDWARE"
    assert row["name"] == "Drawer slide 500mm"
    assert row["sku"] == "DS-500"
    # Pydantic serializes Decimal as string by default
    assert float(row["qty_demand"]) == 5
    assert float(row["qty_on_order"]) == 4
    assert float(row["qty_received"]) == 3
    assert float(row["qty_allocated"]) == 2
    assert float(row["shortfall"]) == 0
    assert row["status"] == "OK"
    assert row["earliest_eta"] == "2026-05-15"


def test_project_materials_404_for_unknown_project():
    """Unknown project_id yields 404."""
    c, _, _ = _login("manager")
    r = c.get("/projects/999999/materials")
    assert r.status_code == 404


def test_project_materials_workspace_isolated():
    """A user in workspace A cannot see a project owned by workspace B (gets 404)."""
    # Workspace A: requesting user
    c_a, _, _ = _login("manager")

    # Workspace B: separate workspace + user; create a project there.
    suffix = uuid.uuid4().hex[:8]
    slug_b = f"h-{suffix}"
    email_b = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid_b = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'B') RETURNING id"),
            {"s": slug_b},
        ).scalar()
        uid_b = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'B', :p, 'manager')
                RETURNING id
                """
            ),
            {"w": wid_b, "e": email_b, "p": hash_password("pw")},
        ).scalar()
        pid_b = db.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id)
                VALUES ('B-001', 'Other Workspace Project', :uid)
                RETURNING project_id
                """
            ),
            {"uid": uid_b},
        ).scalar()
        db.commit()
    finally:
        db.close()

    # User A cannot see project B's materials.
    r = c_a.get(f"/projects/{pid_b}/materials")
    assert r.status_code == 404
