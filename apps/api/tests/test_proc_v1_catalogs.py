"""Tests for /catalogs/{type_} CRUD endpoints (Procurement Workbench v1, Task 11).

Covers (all targeting the `hardware` type):
  - GET /catalogs/hardware lists rows.
  - POST /catalogs/hardware happy path (201, returns description).
  - GET /catalogs/bogus -> 404 (unknown type).
  - PATCH /catalogs/hardware/{mid} updates description.
  - DELETE /catalogs/hardware/{mid} -> 204; subsequent GET -> 404.
  - POST with no insertable fields -> 422.

`hardware_materials` requires `sku` (NOT NULL UNIQUE) — every test uses a
uuid suffix so SKUs do not collide across tests run in the same session.
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
        # Wipe all 6 catalog tables in addition to the foundation TRUNCATE list.
        # equipment_hire references projects(project_id), so it is included for
        # safety even though the Task 11 tests only touch hardware_materials.
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


def _login(role: str = "admin"):
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


# ── Test cases ────────────────────────────────────────────────────────────────


def test_list_hardware_catalog():
    """GET /catalogs/hardware returns rows previously inserted directly."""
    c, wid, _uid = _login("admin")
    sku = f"X-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO hardware_materials(sku, description, workspace_id)"
                " VALUES (:s, 'X', :w)"
            ),
            {"s": sku, "w": wid},
        )
        db.commit()
    finally:
        db.close()

    r = c.get("/catalogs/hardware")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "hardware"
    assert any(row.get("description") == "X" and row.get("sku") == sku for row in body["rows"])


def test_create_hardware():
    """POST /catalogs/hardware with sku + description -> 201 and echoes description."""
    c, _wid, _uid = _login("admin")
    sku = f"H90-{uuid.uuid4().hex[:8]}"
    r = c.post("/catalogs/hardware", json={"sku": sku, "description": "Hinge 90deg"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["description"] == "Hinge 90deg"
    assert body["sku"] == sku
    assert body["type"] == "hardware"


def test_unknown_type_404():
    """GET /catalogs/bogus -> 404 (registry miss)."""
    c, _wid, _uid = _login("admin")
    r = c.get("/catalogs/bogus")
    assert r.status_code == 404


def test_patch_hardware():
    """PATCH /catalogs/hardware/{mid} updates description."""
    c, _wid, _uid = _login("admin")
    sku = f"P-{uuid.uuid4().hex[:8]}"
    mid = c.post(
        "/catalogs/hardware",
        json={"sku": sku, "description": "A"},
    ).json()["material_id"]

    r = c.patch(f"/catalogs/hardware/{mid}", json={"description": "B"})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "B"


def test_delete_hardware():
    """DELETE /catalogs/hardware/{mid} -> 204; subsequent GET -> 404."""
    c, _wid, _uid = _login("admin")
    sku = f"D-{uuid.uuid4().hex[:8]}"
    mid = c.post(
        "/catalogs/hardware",
        json={"sku": sku, "description": "Z"},
    ).json()["material_id"]

    r = c.delete(f"/catalogs/hardware/{mid}")
    assert r.status_code == 204
    g = c.get(f"/catalogs/hardware/{mid}")
    assert g.status_code == 404


def test_no_insertable_fields_returns_422():
    """POST with only unknown fields -> 422 with 'no insertable fields supplied'."""
    c, _wid, _uid = _login("admin")
    r = c.post("/catalogs/hardware", json={"bogus": "x"})
    assert r.status_code == 422, r.text
    assert "no insertable fields supplied" in r.json().get("detail", "").lower()


# ── Parametrised smoke tests for all 6 catalog types ───────────────────────────


@pytest.mark.parametrize(
    "type_,payload_builder",
    [
        (
            "board",
            lambda: {
                "code": f"MDF18-{uuid.uuid4().hex[:8]}",
                "description": "MDF 18mm",
                "sku": f"BD-{uuid.uuid4().hex[:8]}",
            },
        ),
        (
            "hardware",
            lambda: {
                "sku": f"HW-{uuid.uuid4().hex[:8]}",
                "description": "Hinge",
            },
        ),
        (
            "custom_made",
            lambda: {
                "internal_ref": f"CM-{uuid.uuid4().hex[:8]}",
                "description": "Custom panel",
                "sku": f"CM-{uuid.uuid4().hex[:8]}",
            },
        ),
        (
            "benchtop",
            lambda: {
                "slab_id": f"SLAB-{uuid.uuid4().hex[:8]}",
                "description": "Caesarstone slab",
                "sku": f"BT-{uuid.uuid4().hex[:8]}",
            },
        ),
        (
            "appliance",
            lambda: {
                "model_number": f"BSMS-{uuid.uuid4().hex[:8]}",
                "description": "Bosch SMS",
                "sku": f"AP-{uuid.uuid4().hex[:8]}",
            },
        ),
        (
            "hire",
            lambda: {
                "contract_ref": f"HIRE-{uuid.uuid4().hex[:8]}",
                "description": "Scissor lift 1 day",
                "sku": f"HR-{uuid.uuid4().hex[:8]}",
            },
        ),
    ],
)
def test_smoke_all_catalog_types(type_: str, payload_builder):
    """Smoke test: POST /catalogs/{type_} and GET /catalogs/{type_} for all 6 types."""
    c, _wid, uid = _login("admin")
    payload = payload_builder()

    # For hire, we must insert a project first (equipment_hire.project_id NOT NULL FK).
    if type_ == "hire":
        db = SessionLocal()
        try:
            project_id = db.execute(
                text(
                    "INSERT INTO projects(project_code, name, pm_id, workspace_id) "
                    "VALUES(:code, 'Smoke', :uid, "
                    "       (SELECT workspace_id FROM app_user WHERE id = :uid)) "
                    "RETURNING project_id"
                ),
                {"code": f"SMOKE-{uuid.uuid4().hex[:8]}", "uid": uid},
            ).scalar()
            db.commit()
        finally:
            db.close()
        payload["project_id"] = project_id

    # POST to create
    r = c.post(f"/catalogs/{type_}", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == type_
    assert body["description"] == payload["description"]
    mid = body.get("material_id") or body.get("hire_id")
    assert mid is not None

    # GET /catalogs/{type_} and verify our row is listed
    r = c.get(f"/catalogs/{type_}")
    assert r.status_code == 200, r.text
    listing = r.json()
    assert listing["type"] == type_
    # Verify the description is in at least one row
    assert any(row.get("description") == payload["description"] for row in listing["rows"])
