"""Tests for GET /projects/{pid}/hardware_catalog.

Uses the autouse-TRUNCATE pattern from test_items_routes.py.
Raw SQL inserts bypass the route layer (no catalog-write API exists in T13).

Schema notes carried forward from queries.py:
- project_hardware_catalog has no workspace_id; scoped via projects.pm_id chain.
- project_hardware_catalog has no qty column; endpoint returns 1.0 for all rows.
- equipment_hire PK is hire_id; custom_made supplier is NULL.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

# Source tables beyond the base TRUNCATE_TABLES list that we insert into
_EXTRA_TABLES = (
    "project_hardware_catalog_log",
    "project_hardware_catalog",
    "item_hardware_lines",
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        all_tables = ", ".join(list(_EXTRA_TABLES) + list(TRUNCATE_TABLES))
        s.execute(
            text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _login(role: str = "manager"):
    """Create a fresh workspace + user and return (client, workspace_id, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"hw-{suffix}"
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


def _create_project(db, *, uid: int, code: str = "HJ-001") -> int:
    """Insert a project owned by uid and return project_id."""
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


def _insert_board(
    db,
    *,
    wid: int,
    code: str = "BRD-001",
    description: str = "Oak Board",
    sku: str = "SKU-BRD",
    unit_cost: float = 12.50,
) -> int:
    mid = db.execute(
        text(
            """
            INSERT INTO board_materials(code, description, workspace_id, sku, unit_cost)
            VALUES (:code, :desc, :wid, :sku, :cost)
            RETURNING material_id
            """
        ),
        {"code": code, "desc": description, "wid": wid, "sku": sku, "cost": unit_cost},
    ).scalar()
    db.commit()
    return mid


def _insert_hardware(
    db,
    *,
    wid: int,
    sku: str = "HW-001",
    description: str = "Hinge",
    unit_cost: float = 3.75,
) -> int:
    mid = db.execute(
        text(
            """
            INSERT INTO hardware_materials(sku, description, workspace_id, unit_cost)
            VALUES (:sku, :desc, :wid, :cost)
            RETURNING material_id
            """
        ),
        {"sku": sku, "desc": description, "wid": wid, "cost": unit_cost},
    ).scalar()
    db.commit()
    return mid


def _add_to_catalog(
    db,
    *,
    project_id: int,
    material_type: str,
    material_id: int,
    added_by: int,
) -> int:
    cid = db.execute(
        text(
            """
            INSERT INTO project_hardware_catalog(project_id, material_type, material_id, added_by)
            VALUES (:pid, :mtype, :mid, :by)
            RETURNING catalog_id
            """
        ),
        {
            "pid": project_id,
            "mtype": material_type,
            "mid": material_id,
            "by": added_by,
        },
    ).scalar()
    db.commit()
    return cid


# ── Test cases ─────────────────────────────────────────────────────────────────

def test_catalog_empty_for_new_project():
    """A project with no catalog rows returns project_id and an empty rows list."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid)
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["rows"] == []


def test_catalog_resolves_two_source_tables():
    """Catalog rows from BOARD and HARDWARE types surface with correct source_table strings."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid)
        board_mid = _insert_board(
            db, wid=wid, code="BRD-A", sku="SKU-A", description="Oak Board"
        )
        hw_mid = _insert_hardware(db, wid=wid, sku="HW-A", description="Hinge")
        _add_to_catalog(
            db, project_id=pid, material_type="BOARD",
            material_id=board_mid, added_by=uid,
        )
        _add_to_catalog(
            db, project_id=pid, material_type="HARDWARE",
            material_id=hw_mid, added_by=uid,
        )
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 2
    source_tables = {row["source_table"] for row in rows}
    assert "board_materials" in source_tables
    assert "hardware_materials" in source_tables


def test_catalog_404_for_other_workspace():
    """A user from workspace B cannot access workspace A's project catalog."""
    c_a, wid_a, uid_a = _login()
    c_b, _wid_b, _uid_b = _login()

    db = SessionLocal()
    try:
        pid_a = _create_project(db, uid=uid_a, code="HJ-WA1")
    finally:
        db.close()

    r = c_b.get(f"/projects/{pid_a}/hardware_catalog")
    assert r.status_code == 404, r.text


def test_catalog_includes_qty_and_unit_cost():
    """Catalog row echoes unit_cost from the source table; qty is always 1.0."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid)
        board_mid = _insert_board(
            db, wid=wid, code="BRD-B", sku="SKU-B",
            description="Walnut Sheet", unit_cost=24.99,
        )
        _add_to_catalog(
            db, project_id=pid, material_type="BOARD",
            material_id=board_mid, added_by=uid,
        )
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert abs(row["unit_cost"] - 24.99) < 0.01
    assert row["qty"] == 1.0
