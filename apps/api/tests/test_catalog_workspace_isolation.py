"""Workspace-isolation guarantees for /catalog/* (sub-project #7a).

Two-workspace fixture: every catalog read + write filters on workspace_id =
the actor's workspace. Cross-workspace returns 404, never 403 (per the
post-#5b workspace-isolation pattern).
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


def _two_workspaces(role: str = "drafter"):
    """Create two workspaces with one drafter user each. Return two dicts:
    {"client": TestClient logged in, "wid": <wid>, "uid": <uid>}."""
    out = []
    for tag in ("a", "b"):
        suffix = f"{tag}-{uuid.uuid4().hex[:6]}"
        slug = f"iso-{suffix}"
        email = f"u-{suffix}@example.com"
        s = SessionLocal()
        try:
            wid = s.execute(
                text("INSERT INTO workspace(slug, name) VALUES(:s, 'ISO') RETURNING id"),
                {"s": slug},
            ).scalar()
            uid = s.execute(text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
            """), {"w": wid, "e": email, "p": hash_password("pw"), "r": role}).scalar()
            s.commit()
        finally:
            s.close()
        c = TestClient(app)
        r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
        assert r.status_code == 200, r.text
        out.append({"client": c, "wid": wid, "uid": uid})
    return out[0], out[1]


def _seed_board(wid: int, *, code: str, sku: str, description: str = "X") -> int:
    s = SessionLocal()
    try:
        mid = s.execute(text("""
            INSERT INTO board_materials(code, sku, description, workspace_id)
            VALUES (:c, :s, :d, :w) RETURNING material_id
        """), {"c": code, "s": sku, "d": description, "w": wid}).scalar()
        s.commit()
        return mid
    finally:
        s.close()


# ── Catalog ───────────────────────────────────────────────────────────────────

def test_list_board_materials_excludes_other_workspace_rows():
    a, b = _two_workspaces()
    _seed_board(a["wid"], code="A1", sku="a-1", description="A board")
    _seed_board(b["wid"], code="B1", sku="b-1", description="B board")
    rows = a["client"].get("/catalog/board-materials").json()["rows"]
    skus = [r["sku"] for r in rows]
    assert "a-1" in skus
    assert "b-1" not in skus


def test_get_board_material_in_other_workspace_returns_404():
    a, b = _two_workspaces()
    bid = _seed_board(b["wid"], code="B1", sku="b-1")
    r = a["client"].get(f"/catalog/board-materials/{bid}")
    assert r.status_code == 404


def test_patch_board_material_in_other_workspace_returns_404():
    a, b = _two_workspaces()
    bid = _seed_board(b["wid"], code="B1", sku="b-1")
    r = a["client"].patch(f"/catalog/board-materials/{bid}", json={"description": "X"})
    assert r.status_code == 404


def test_archive_board_material_in_other_workspace_returns_404():
    a, b = _two_workspaces()
    bid = _seed_board(b["wid"], code="B1", sku="b-1")
    r = a["client"].post(f"/catalog/board-materials/{bid}/archive")
    assert r.status_code == 404


# ── CV mappings ───────────────────────────────────────────────────────────────

def test_list_cv_mappings_excludes_other_workspace_rows():
    a, b = _two_workspaces()
    bid_a = _seed_board(a["wid"], code="A1", sku="a-1")
    bid_b = _seed_board(b["wid"], code="B1", sku="b-1")
    a["client"].post("/catalog/cv-mappings", json={
        "cv_code": "A-CODE", "target_material_table": "board_materials",
        "target_material_id": bid_a,
    })
    b["client"].post("/catalog/cv-mappings", json={
        "cv_code": "B-CODE", "target_material_table": "board_materials",
        "target_material_id": bid_b,
    })
    rows = a["client"].get("/catalog/cv-mappings").json()["rows"]
    codes = [r["cv_code"] for r in rows]
    assert "A-CODE" in codes
    assert "B-CODE" not in codes


def test_post_cv_mapping_in_my_workspace_does_not_collide_with_other_workspace_same_cv_code():
    a, b = _two_workspaces()
    bid_a = _seed_board(a["wid"], code="A1", sku="a-1")
    bid_b = _seed_board(b["wid"], code="B1", sku="b-1")
    payload_a = {"cv_code": "SAME", "target_material_table": "board_materials",
                 "target_material_id": bid_a}
    payload_b = {"cv_code": "SAME", "target_material_table": "board_materials",
                 "target_material_id": bid_b}
    r1 = a["client"].post("/catalog/cv-mappings", json=payload_a)
    r2 = b["client"].post("/catalog/cv-mappings", json=payload_b)
    assert r1.status_code == 201
    assert r2.status_code == 201
