"""Tests for /catalog/* CRUD endpoints (sub-project #7a).

Pattern: per-test workspace + drafter user + autouse TRUNCATE of the 6
catalog tables. Mirrors test_proc_v1_catalogs.py but exercises the new
catalog-gated surface ("/catalog" singular) added by #7a.
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
            "equipment_hire",
            "appliances",
            "benchtop_materials",
            "custom_made",
            "hardware_materials",
            "board_materials",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _login(role: str = "drafter"):
    """Create fresh workspace + user, log in. Return (client, wid, uid)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"c-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'C') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = db.execute(
            text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
            """),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c, wid, uid


def _seed_board(wid: int, *, code: str, sku: str, description: str = "Board",
                synonyms: list[str] | None = None, supplier: str | None = None) -> int:
    db = SessionLocal()
    try:
        mid = db.execute(text("""
            INSERT INTO board_materials(code, sku, description, workspace_id, synonyms, default_supplier)
            VALUES (:c, :s, :d, :w, :syn, :sup) RETURNING material_id
        """), {"c": code, "s": sku, "d": description, "w": wid,
               "syn": synonyms or [], "sup": supplier}).scalar()
        db.commit()
        return mid
    finally:
        db.close()


def _seed_project(wid: int, uid: int, *, code: str = "ALF-001") -> int:
    db = SessionLocal()
    try:
        pid = db.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES (:c, 'Alfred', :u, :w) RETURNING project_id
        """), {"c": code, "u": uid, "w": wid}).scalar()
        db.commit()
        return pid
    finally:
        db.close()


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_board_materials_returns_seeded_rows():
    c, wid, _ = _login()
    _seed_board(wid, code="18-PB", sku="board-1", description="18mm Particleboard")
    r = c.get("/catalog/board-materials")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "board"
    assert any(row["sku"] == "board-1" for row in body["rows"])


def test_list_filters_by_q():
    c, wid, _ = _login()
    _seed_board(wid, code="A", sku="board-A", description="Particleboard White")
    _seed_board(wid, code="B", sku="board-B", description="MDF Black")
    r = c.get("/catalog/board-materials?q=Particle")
    assert r.status_code == 200
    skus = [row["sku"] for row in r.json()["rows"]]
    assert "board-A" in skus and "board-B" not in skus


def test_list_filters_by_supplier():
    c, wid, _ = _login()
    _seed_board(wid, code="A", sku="board-A", description="X", supplier="Laminex")
    _seed_board(wid, code="B", sku="board-B", description="Y", supplier="Polytec")
    r = c.get("/catalog/board-materials?supplier=Laminex")
    skus = [row["sku"] for row in r.json()["rows"]]
    assert skus == ["board-A"]


def test_list_archived_false_excludes_archived():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="board-A")
    c.post(f"/catalog/board-materials/{mid}/archive")
    r = c.get("/catalog/board-materials")
    assert r.status_code == 200
    assert all(row["material_id"] != mid for row in r.json()["rows"])


def test_list_archived_true_includes_archived():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="board-A")
    c.post(f"/catalog/board-materials/{mid}/archive")
    r = c.get("/catalog/board-materials?archived=true")
    assert any(row["material_id"] == mid for row in r.json()["rows"])


# ── Get ───────────────────────────────────────────────────────────────────────

def test_get_board_material_by_id_returns_synonyms():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="board-A", synonyms=["alt1", "alt2"])
    r = c.get(f"/catalog/board-materials/{mid}")
    assert r.status_code == 200
    body = r.json()
    assert body["synonyms"] == ["alt1", "alt2"]


def test_get_unknown_id_returns_404():
    c, _, _ = _login()
    r = c.get("/catalog/board-materials/999999")
    assert r.status_code == 404


def test_get_unknown_slug_returns_404():
    c, _, _ = _login()
    r = c.get("/catalog/not-a-slug/1")
    assert r.status_code == 404


# ── Create ────────────────────────────────────────────────────────────────────

def test_post_board_material_creates_row_with_synonyms():
    c, _, _ = _login()
    r = c.post("/catalog/board-materials", json={
        "code": "18-PB", "sku": "b-1", "description": "18mm PB",
        "synonyms": ["18-PB-alt"], "default_supplier": "Laminex",
        "default_lead_time_days": 5,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sku"] == "b-1"
    assert body["synonyms"] == ["18-PB-alt"]
    assert body["default_supplier"] == "Laminex"


def test_post_board_material_returns_409_on_duplicate_code():
    c, _, _ = _login()
    r1 = c.post("/catalog/board-materials", json={
        "code": "DUP", "sku": "b-1", "description": "X",
    })
    assert r1.status_code == 201
    r2 = c.post("/catalog/board-materials", json={
        "code": "DUP", "sku": "b-2", "description": "Y",
    })
    assert r2.status_code == 409


def test_post_hardware_material_with_default_supplier_and_lead_time():
    c, _, _ = _login()
    r = c.post("/catalog/hardware-materials", json={
        "sku": "hw-1", "description": "Blum runner",
        "default_supplier": "Blum", "default_lead_time_days": 14,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["default_supplier"] == "Blum"
    assert body["default_lead_time_days"] == 14


def test_post_equipment_hire_requires_project_id():
    c, _, _ = _login()
    r = c.post("/catalog/equipment-hire", json={
        "contract_ref": "EH-1", "sku": "eh-1", "description": "Crane",
    })
    assert r.status_code == 422


def test_post_equipment_hire_with_project_id_succeeds():
    c, wid, uid = _login()
    pid = _seed_project(wid, uid)
    r = c.post("/catalog/equipment-hire", json={
        "contract_ref": "EH-1", "sku": "eh-1", "description": "Crane",
        "project_id": pid,
    })
    assert r.status_code == 201, r.text


# ── Patch ─────────────────────────────────────────────────────────────────────

def test_patch_partial_update_only_changed_columns():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="b-1", description="Original")
    r = c.patch(f"/catalog/board-materials/{mid}", json={
        "default_supplier": "Polytec",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["default_supplier"] == "Polytec"
    assert body["description"] == "Original"


def test_patch_synonyms_replaces_array():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="b-1", synonyms=["old1", "old2"])
    r = c.patch(f"/catalog/board-materials/{mid}", json={
        "synonyms": ["new1"],
    })
    assert r.status_code == 200
    assert r.json()["synonyms"] == ["new1"]


def test_patch_unknown_id_returns_404():
    c, _, _ = _login()
    r = c.patch("/catalog/board-materials/999999", json={"description": "X"})
    assert r.status_code == 404


# ── Archive ───────────────────────────────────────────────────────────────────

def test_archive_sets_archived_at_and_archived_by():
    c, wid, uid = _login()
    mid = _seed_board(wid, code="A", sku="b-1")
    r = c.post(f"/catalog/board-materials/{mid}/archive")
    assert r.status_code == 200
    body = r.json()
    assert body["archived_at"] is not None
    assert body["archived_by"] == uid


def test_archive_already_archived_returns_409():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="b-1")
    c.post(f"/catalog/board-materials/{mid}/archive")
    r = c.post(f"/catalog/board-materials/{mid}/archive")
    assert r.status_code == 409


def test_archive_unknown_id_returns_404():
    c, _, _ = _login()
    r = c.post("/catalog/board-materials/999999/archive")
    assert r.status_code == 404


# ── Bulk import ───────────────────────────────────────────────────────────────

def test_bulk_import_5_rows_all_succeed():
    c, _, _ = _login()
    rows = [
        {"code": f"C-{i}", "sku": f"b-{i}", "description": f"Board {i}"}
        for i in range(5)
    ]
    r = c.post("/catalog/board-materials/bulk", json={"rows": rows})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 5
    assert body["errors"] == []


def test_bulk_import_with_one_invalid_row_creates_zero():
    c, _, _ = _login()
    rows = [
        {"code": "C-1", "sku": "b-1", "description": "OK"},
        {"code": "C-2", "sku": "b-2"},
        {"code": "C-3", "sku": "b-3", "description": "OK3"},
    ]
    r = c.post("/catalog/board-materials/bulk", json={"rows": rows})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 0
    assert any(e["row_index"] == 1 for e in body["errors"])


def test_bulk_import_writes_one_audit_row():
    c, wid, _ = _login()
    rows = [{"code": f"C-{i}", "sku": f"b-{i}", "description": f"X{i}"} for i in range(3)]
    r = c.post("/catalog/board-materials/bulk", json={"rows": rows})
    assert r.status_code == 200 and r.json()["created"] == 3
    db = SessionLocal()
    try:
        n = db.execute(text("""
            SELECT COUNT(*) FROM audit_log
            WHERE workspace_id = :w AND event = 'catalog.board.csv_import'
        """), {"w": wid}).scalar()
        assert n == 1
    finally:
        db.close()


# ── Audit hooks ───────────────────────────────────────────────────────────────

def test_create_writes_catalog_table_create_audit():
    c, wid, _ = _login()
    r = c.post("/catalog/board-materials", json={
        "code": "A", "sku": "b-1", "description": "X",
    })
    assert r.status_code == 201
    db = SessionLocal()
    try:
        n = db.execute(text("""
            SELECT COUNT(*) FROM audit_log
            WHERE workspace_id = :w AND event = 'catalog.board.create'
        """), {"w": wid}).scalar()
        assert n == 1
    finally:
        db.close()


def test_patch_writes_catalog_table_update_audit_with_payload():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="b-1")
    r = c.patch(f"/catalog/board-materials/{mid}", json={"description": "Y"})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT payload FROM audit_log
            WHERE workspace_id = :w AND event = 'catalog.board.update'
            ORDER BY audit_id DESC LIMIT 1
        """), {"w": wid}).mappings().first()
        assert row is not None
        assert row["payload"]["description"] == "Y"
    finally:
        db.close()


def test_archive_writes_catalog_table_archive_audit():
    c, wid, _ = _login()
    mid = _seed_board(wid, code="A", sku="b-1")
    c.post(f"/catalog/board-materials/{mid}/archive")
    db = SessionLocal()
    try:
        n = db.execute(text("""
            SELECT COUNT(*) FROM audit_log
            WHERE workspace_id = :w AND event = 'catalog.board.archive'
        """), {"w": wid}).scalar()
        assert n == 1
    finally:
        db.close()
