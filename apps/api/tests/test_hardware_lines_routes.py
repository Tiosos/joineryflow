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
    "status_options",
    "item_stages",
    "item_edit_log",
    "item_status_log",
    "item_hardware_lines",
    "items",
    "project_hardware_catalog_log",
    "project_hardware_catalog",
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
    """Insert a project owned by uid and return project_id.

    workspace_id is derived inline from the uid's app_user row, mirroring
    create_project_route's default of using the caller's workspace.
    """
    pid = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES (:code, :name, :uid, (SELECT workspace_id FROM app_user WHERE id = :uid))
            RETURNING project_id
            """
        ),
        {"code": code, "name": f"Project {code}", "uid": uid},
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


# ── T18 tests ──────────────────────────────────────────────────────────────────


def _seed_status(db) -> None:
    """Seed status_options reference rows (FK target for items.status)."""
    for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order) "
                "VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    db.commit()


def _create_item(db, *, project_id: int, uid: int, code: str = "ITEM-001") -> int:
    """Insert an item under a project and return item_id."""
    _seed_status(db)
    iid = db.execute(
        text(
            """
            INSERT INTO items(project_id, num, status)
            VALUES (:pid, 1, 'CLEAR')
            RETURNING item_id
            """
        ),
        {"pid": project_id},
    ).scalar()
    db.commit()
    return iid


def _add_hardware_line(db, *, item_id: int, catalog_id: int, qty: int = 1) -> int:
    """Raw insert an item_hardware_lines row and return line_id."""
    lid = db.execute(
        text(
            """
            INSERT INTO item_hardware_lines(item_id, catalog_id, qty)
            VALUES (:iid, :cid, :qty)
            RETURNING line_id
            """
        ),
        {"iid": item_id, "cid": catalog_id, "qty": qty},
    ).scalar()
    db.commit()
    return lid


def test_add_catalog_writes_log_in_same_txn():
    """POST hardware_catalog inserts both catalog row and log row."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-A1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18A", sku="SKU-T18A", description="Oak T18A")
    finally:
        db.close()

    r = c.post(
        f"/projects/{pid}/hardware_catalog",
        json={"source_table": "board_materials", "source_id": board_mid},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["catalog_id"]

    db = SessionLocal()
    try:
        cat_count = db.execute(
            text("SELECT COUNT(*) FROM project_hardware_catalog WHERE catalog_id = :cid"),
            {"cid": cid},
        ).scalar()
        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM project_hardware_catalog_log "
                "WHERE project_id = :pid AND action = 'ADD'"
            ),
            {"pid": pid},
        ).scalar()
    finally:
        db.close()

    assert cat_count == 1
    assert log_count == 1


def test_add_catalog_invalid_source_404():
    """POST hardware_catalog with non-existent source_id returns 404."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-A2")
    finally:
        db.close()

    r = c.post(
        f"/projects/{pid}/hardware_catalog",
        json={"source_table": "board_materials", "source_id": 999999},
    )
    assert r.status_code == 404, r.text


def test_remove_catalog_409_when_referenced():
    """DELETE hardware_catalog returns 409 when a hardware_line references it."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-B1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18B", sku="SKU-T18B", description="Walnut T18B")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
        _add_hardware_line(db, item_id=iid, catalog_id=cid)
    finally:
        db.close()

    r = c.delete(f"/projects/{pid}/hardware_catalog/{cid}")
    assert r.status_code == 409, r.text


def test_remove_catalog_writes_remove_log_row():
    """DELETE hardware_catalog inserts a REMOVE log row."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-B2")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18C", sku="SKU-T18C", description="Birch T18C")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
    finally:
        db.close()

    r = c.delete(f"/projects/{pid}/hardware_catalog/{cid}")
    assert r.status_code == 204, r.text

    db = SessionLocal()
    try:
        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM project_hardware_catalog_log "
                "WHERE project_id = :pid AND action = 'REMOVE'"
            ),
            {"pid": pid},
        ).scalar()
    finally:
        db.close()

    assert log_count == 1


def test_create_hardware_line_validates_catalog_belongs_to_project():
    """POST hardware_line with catalog_id from a different project returns 404."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid_a = _create_project(db, uid=uid, code="T18-C1A")
        pid_b = _create_project(db, uid=uid, code="T18-C1B")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18D", sku="SKU-T18D", description="Maple T18D")
        # Add catalog row to project B
        cid_b = _add_to_catalog(db, project_id=pid_b, material_type="BOARD", material_id=board_mid, added_by=uid)
        # Create item in project A
        iid_a = _create_item(db, project_id=pid_a, uid=uid)
    finally:
        db.close()

    # Try to create hardware line for item in project A using catalog from project B
    r = c.post(
        f"/items/{iid_a}/hardware_lines",
        json={"catalog_id": cid_b, "qty": 1},
    )
    assert r.status_code == 404, r.text


def test_patch_hardware_line_qty_writes_edit_log():
    """PATCH qty writes one item_edit_log row with field='hardware_lines.qty'."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-D1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18E", sku="SKU-T18E", description="Pine T18E")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
        lid = _add_hardware_line(db, item_id=iid, catalog_id=cid, qty=1)
    finally:
        db.close()

    r = c.patch(f"/hardware_lines/{lid}", json={"qty": 5})
    assert r.status_code == 200, r.text
    assert r.json()["qty"] == 5

    db = SessionLocal()
    try:
        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM item_edit_log "
                "WHERE item_id = :iid AND field = 'hardware_lines.qty'"
            ),
            {"iid": iid},
        ).scalar()
    finally:
        db.close()

    assert log_count == 1


def test_editor_403_on_hardware_line_create():
    """A user with auth_role='editor' gets 403 when POSTing a hardware line."""
    c, wid, uid = _login(role="editor")
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-E1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18F", sku="SKU-T18F", description="Cedar T18F")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
    finally:
        db.close()

    r = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": cid, "qty": 1})
    assert r.status_code == 403, r.text


def test_availability_endpoint_reflects_new_line():
    """After POSTing a hardware_line, GET /items/{id}/availability shows it as 'none'."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code="T18-F1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18G", sku="SKU-T18G", description="Ash T18G")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
    finally:
        db.close()

    r = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": cid, "qty": 2})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]

    r = c.get(f"/items/{iid}/availability")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_id"] == iid
    lines = body["lines"]
    assert len(lines) == 1
    assert lines[0]["line_id"] == lid
    assert lines[0]["status"] == "none"
