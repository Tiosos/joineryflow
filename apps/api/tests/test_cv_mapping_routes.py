"""Tests for /catalog/cv-mappings/* (sub-project #7a).

The cv_material_mapping register translates freeform CV codes (e.g. '18-PB',
'700.0KC2.054.00') to (target_material_table, target_material_id). UNIQUE
on (workspace_id, cv_code). 10 cases per the plan.
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
    suffix = uuid.uuid4().hex[:8]
    slug = f"m-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'M') RETURNING id"),
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


def _seed_board(wid: int, *, code: str, sku: str, description: str = "Board") -> int:
    db = SessionLocal()
    try:
        mid = db.execute(text("""
            INSERT INTO board_materials(code, sku, description, workspace_id)
            VALUES (:c, :s, :d, :w) RETURNING material_id
        """), {"c": code, "s": sku, "d": description, "w": wid}).scalar()
        db.commit()
        return mid
    finally:
        db.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_list_cv_mappings_empty_workspace_returns_zero():
    c, _, _ = _login()
    r = c.get("/catalog/cv-mappings")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["rows"] == []


def test_post_cv_mapping_creates_row():
    c, wid, _ = _login()
    bid = _seed_board(wid, code="A", sku="b-1", description="18mm PB")
    r = c.post("/catalog/cv-mappings", json={
        "cv_code": "18-PB",
        "target_material_table": "board_materials",
        "target_material_id": bid,
        "notes": "Drafter pinned 2026-05",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["cv_code"] == "18-PB"
    assert body["target_material_table"] == "board_materials"
    assert body["target_material_id"] == bid


def test_post_cv_mapping_duplicate_code_returns_409():
    c, wid, _ = _login()
    bid = _seed_board(wid, code="A", sku="b-1")
    payload = {"cv_code": "DUP", "target_material_table": "board_materials",
               "target_material_id": bid}
    r1 = c.post("/catalog/cv-mappings", json=payload)
    assert r1.status_code == 201
    r2 = c.post("/catalog/cv-mappings", json=payload)
    assert r2.status_code == 409


def test_post_cv_mapping_with_invalid_target_table_returns_422():
    c, _, _ = _login()
    r = c.post("/catalog/cv-mappings", json={
        "cv_code": "X",
        "target_material_table": "not_a_table",
        "target_material_id": 1,
    })
    assert r.status_code == 422


def test_get_cv_mapping_returns_target_description():
    c, wid, _ = _login()
    bid = _seed_board(wid, code="A", sku="b-1", description="Pinned description")
    r = c.post("/catalog/cv-mappings", json={
        "cv_code": "PIN", "target_material_table": "board_materials",
        "target_material_id": bid,
    })
    assert r.status_code == 201
    rows = c.get("/catalog/cv-mappings").json()["rows"]
    found = next(r for r in rows if r["cv_code"] == "PIN")
    assert found["target_description"] == "Pinned description"


def test_patch_cv_mapping_repoints_to_new_target():
    c, wid, _ = _login()
    b1 = _seed_board(wid, code="A", sku="b-1", description="Old")
    b2 = _seed_board(wid, code="B", sku="b-2", description="New")
    created = c.post("/catalog/cv-mappings", json={
        "cv_code": "MOVE", "target_material_table": "board_materials",
        "target_material_id": b1,
    }).json()
    mid = created["cv_material_mapping_id"]
    r = c.patch(f"/catalog/cv-mappings/{mid}", json={"target_material_id": b2})
    assert r.status_code == 200
    assert r.json()["target_material_id"] == b2


def test_patch_cv_mapping_unknown_id_returns_404():
    c, _, _ = _login()
    r = c.patch("/catalog/cv-mappings/999999", json={"cv_code": "X"})
    assert r.status_code == 404


def test_delete_cv_mapping_hard_deletes():
    c, wid, _ = _login()
    bid = _seed_board(wid, code="A", sku="b-1")
    created = c.post("/catalog/cv-mappings", json={
        "cv_code": "DEL", "target_material_table": "board_materials",
        "target_material_id": bid,
    }).json()
    mid = created["cv_material_mapping_id"]
    r = c.delete(f"/catalog/cv-mappings/{mid}")
    assert r.status_code == 204
    rows = c.get("/catalog/cv-mappings").json()["rows"]
    assert all(r["cv_material_mapping_id"] != mid for r in rows)


def test_delete_cv_mapping_unknown_id_returns_404():
    c, _, _ = _login()
    r = c.delete("/catalog/cv-mappings/999999")
    assert r.status_code == 404


def test_create_writes_audit_event_cv_material_mapping_create():
    c, wid, _ = _login()
    bid = _seed_board(wid, code="A", sku="b-1")
    r = c.post("/catalog/cv-mappings", json={
        "cv_code": "AUDIT", "target_material_table": "board_materials",
        "target_material_id": bid,
    })
    assert r.status_code == 201
    db = SessionLocal()
    try:
        n = db.execute(text("""
            SELECT COUNT(*) FROM audit_log
            WHERE workspace_id = :w AND event = 'cv_material_mapping.create'
        """), {"w": wid}).scalar()
        assert n == 1
    finally:
        db.close()
