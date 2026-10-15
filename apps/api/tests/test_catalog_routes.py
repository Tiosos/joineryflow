"""Tests for /catalog/* CRUD endpoints (sub-project #7a).

Pattern: per-test workspace + drafter user + autouse TRUNCATE of the 6
catalog tables.

`/catalog/*` is the sole write surface for the six material catalog tables.
The `/catalogs/*` namespace that Procurement Workbench v1 shipped alongside it
has been retired — see the retirement guards at the bottom of this file.
"""

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import login
from .conftest import truncate_fixture


_cleanup = truncate_fixture(
    "batch_allocations",
    "procurement_batches",
    "equipment_hire",
    "appliances",
    "benchtop_materials",
    "custom_made",
    "hardware_materials",
    "board_materials",
)


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
    c, wid, _ = login("drafter")
    _seed_board(wid, code="18-PB", sku="board-1", description="18mm Particleboard")
    r = c.get("/catalog/board-materials")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "board"
    assert any(row["sku"] == "board-1" for row in body["rows"])


def test_list_filters_by_q():
    c, wid, _ = login("drafter")
    _seed_board(wid, code="A", sku="board-A", description="Particleboard White")
    _seed_board(wid, code="B", sku="board-B", description="MDF Black")
    r = c.get("/catalog/board-materials?q=Particle")
    assert r.status_code == 200
    skus = [row["sku"] for row in r.json()["rows"]]
    assert "board-A" in skus and "board-B" not in skus


def test_list_filters_by_supplier():
    c, wid, _ = login("drafter")
    _seed_board(wid, code="A", sku="board-A", description="X", supplier="Laminex")
    _seed_board(wid, code="B", sku="board-B", description="Y", supplier="Polytec")
    r = c.get("/catalog/board-materials?supplier=Laminex")
    skus = [row["sku"] for row in r.json()["rows"]]
    assert skus == ["board-A"]


def test_list_archived_false_excludes_archived():
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="board-A")
    c.post(f"/catalog/board-materials/{mid}/archive")
    r = c.get("/catalog/board-materials")
    assert r.status_code == 200
    assert all(row["material_id"] != mid for row in r.json()["rows"])


def test_list_archived_true_includes_archived():
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="board-A")
    c.post(f"/catalog/board-materials/{mid}/archive")
    r = c.get("/catalog/board-materials?archived=true")
    assert any(row["material_id"] == mid for row in r.json()["rows"])


# ── Get ───────────────────────────────────────────────────────────────────────

def test_get_board_material_by_id_returns_synonyms():
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="board-A", synonyms=["alt1", "alt2"])
    r = c.get(f"/catalog/board-materials/{mid}")
    assert r.status_code == 200
    body = r.json()
    assert body["synonyms"] == ["alt1", "alt2"]


def test_get_unknown_id_returns_404():
    c, _, _ = login("drafter")
    r = c.get("/catalog/board-materials/999999")
    assert r.status_code == 404


def test_get_unknown_slug_returns_404():
    c, _, _ = login("drafter")
    r = c.get("/catalog/not-a-slug/1")
    assert r.status_code == 404


# ── Create ────────────────────────────────────────────────────────────────────

def test_post_board_material_creates_row_with_synonyms():
    c, _, _ = login("drafter")
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
    c, _, _ = login("drafter")
    r1 = c.post("/catalog/board-materials", json={
        "code": "DUP", "sku": "b-1", "description": "X",
    })
    assert r1.status_code == 201
    r2 = c.post("/catalog/board-materials", json={
        "code": "DUP", "sku": "b-2", "description": "Y",
    })
    assert r2.status_code == 409


def test_post_hardware_material_with_default_supplier_and_lead_time():
    c, _, _ = login("drafter")
    r = c.post("/catalog/hardware-materials", json={
        "sku": "hw-1", "description": "Blum runner",
        "default_supplier": "Blum", "default_lead_time_days": 14,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["default_supplier"] == "Blum"
    assert body["default_lead_time_days"] == 14


def test_post_equipment_hire_requires_project_id():
    c, _, _ = login("drafter")
    r = c.post("/catalog/equipment-hire", json={
        "contract_ref": "EH-1", "sku": "eh-1", "description": "Crane",
    })
    assert r.status_code == 422


def test_post_equipment_hire_with_project_id_succeeds():
    c, wid, uid = login("drafter")
    pid = _seed_project(wid, uid)
    r = c.post("/catalog/equipment-hire", json={
        "contract_ref": "EH-1", "sku": "eh-1", "description": "Crane",
        "project_id": pid,
    })
    assert r.status_code == 201, r.text


# ── Patch ─────────────────────────────────────────────────────────────────────

def test_patch_partial_update_only_changed_columns():
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="b-1", description="Original")
    r = c.patch(f"/catalog/board-materials/{mid}", json={
        "default_supplier": "Polytec",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["default_supplier"] == "Polytec"
    assert body["description"] == "Original"


def test_patch_synonyms_replaces_array():
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="b-1", synonyms=["old1", "old2"])
    r = c.patch(f"/catalog/board-materials/{mid}", json={
        "synonyms": ["new1"],
    })
    assert r.status_code == 200
    assert r.json()["synonyms"] == ["new1"]


def test_patch_unknown_id_returns_404():
    c, _, _ = login("drafter")
    r = c.patch("/catalog/board-materials/999999", json={"description": "X"})
    assert r.status_code == 404


# ── Archive ───────────────────────────────────────────────────────────────────

def test_archive_sets_archived_at_and_archived_by():
    c, wid, uid = login("drafter")
    mid = _seed_board(wid, code="A", sku="b-1")
    r = c.post(f"/catalog/board-materials/{mid}/archive")
    assert r.status_code == 200
    body = r.json()
    assert body["archived_at"] is not None
    assert body["archived_by"] == uid


def test_archive_already_archived_returns_409():
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="b-1")
    c.post(f"/catalog/board-materials/{mid}/archive")
    r = c.post(f"/catalog/board-materials/{mid}/archive")
    assert r.status_code == 409


def test_archive_unknown_id_returns_404():
    c, _, _ = login("drafter")
    r = c.post("/catalog/board-materials/999999/archive")
    assert r.status_code == 404


# ── Bulk import ───────────────────────────────────────────────────────────────

def test_bulk_import_5_rows_all_succeed():
    c, _, _ = login("drafter")
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
    c, _, _ = login("drafter")
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
    c, wid, _ = login("drafter")
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
    c, wid, _ = login("drafter")
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
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="b-1")
    r = c.patch(f"/catalog/board-materials/{mid}", json={"description": "Y"})
    assert r.status_code == 200
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT payload FROM audit_log
            WHERE workspace_id = :w AND event = 'catalog.board.update'
            ORDER BY id DESC LIMIT 1
        """), {"w": wid}).mappings().first()
        assert row is not None
        assert row["payload"]["description"] == "Y"
    finally:
        db.close()


def test_archive_writes_catalog_table_archive_audit():
    c, wid, _ = login("drafter")
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


# ── Retirement of the `/catalogs/*` (plural) surface ──────────────────────────
#
# That namespace duplicated these six tables under the `orderbook` RBAC module,
# was not workspace-scoped, and its DELETE hard-deleted rows that `parts`,
# `board_inventory`, `cv_material_mapping` and `estimate_line_part` point at.
# These guards fail if it is ever remounted.

@pytest.mark.parametrize("type_", [
    "board", "hardware", "custom_made", "benchtop", "appliance", "hire",
])
def test_plural_catalogs_namespace_is_gone(type_):
    c, _, _ = login("drafter")
    assert c.get(f"/catalogs/{type_}").status_code == 404
    assert c.post(f"/catalogs/{type_}", json={"sku": "x"}).status_code == 404


def test_no_hard_delete_route_on_catalog_rows():
    """Removal is soft-archive only; DELETE must not reach a handler."""
    c, wid, _ = login("drafter")
    mid = _seed_board(wid, code="A", sku="b-1")
    assert c.delete(f"/catalog/board-materials/{mid}").status_code == 405
    assert c.delete(f"/catalogs/board/{mid}").status_code == 404
    # Row survives both attempts.
    assert c.get(f"/catalog/board-materials/{mid}").status_code == 200


def test_purchase_officer_cannot_write_catalog():
    """purchase_officer is {read, comment} on `catalog`. Before the plural
    surface was retired, `orderbook` write let them create and hard-delete."""
    c, wid, _ = login(role="purchase_officer")
    mid = _seed_board(wid, code="A", sku="b-1")
    assert c.get("/catalog/board-materials").status_code == 200
    assert c.post("/catalog/board-materials", json={
        "code": "B", "sku": "b-2", "description": "Board",
    }).status_code == 403
    assert c.patch(f"/catalog/board-materials/{mid}", json={"description": "X"}).status_code == 403
    assert c.post(f"/catalog/board-materials/{mid}/archive").status_code == 403


# ── Only validation errors are reported as bad input ─────────────────────────

def test_a_bug_inside_validation_is_a_server_error_not_a_bad_row(monkeypatch):
    """Bulk, create and patch used to catch `Exception` around `model_validate`, so a bug in
    a schema (here a RuntimeError) came back as a per-row error or a 422 instead of a 500."""
    from app.catalog.schemas import CreateBoardIn, PatchBoardIn

    c, wid, _uid = login("drafter")
    mid = _seed_board(wid, code="BX", sku="SKU-BX")

    def boom(cls, *a, **k):
        raise RuntimeError("schema bug")

    monkeypatch.setattr(CreateBoardIn, "model_validate", classmethod(boom))
    monkeypatch.setattr(PatchBoardIn, "model_validate", classmethod(boom))
    with pytest.raises(RuntimeError):
        c.post("/catalog/board-materials/bulk", json={"rows": [{"code": "B1", "description": "x"}]})
    with pytest.raises(RuntimeError):
        c.post("/catalog/board-materials", json={"code": "B2", "description": "x"})
    with pytest.raises(RuntimeError):
        c.patch(f"/catalog/board-materials/{mid}", json={"description": "y"})


# ── Unit cost (what an order line starts its price from) ──────────────────────

def test_unit_cost_is_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    r = c.post("/catalog/hardware-materials", json={"sku": "hw-cost", "description": "Hinge", "unit_cost": "12.5"})
    assert r.status_code == 201, r.text
    mid = r.json()["material_id"]
    assert r.json()["unit_cost"] == 12.5                                   # a JSON number, like the other catalog numbers
    listed = [x for x in c.get("/catalog/hardware-materials").json()["rows"] if x["material_id"] == mid][0]
    assert listed["unit_cost"] == 12.5

    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"unit_cost": 13.25})
    assert r.status_code == 200 and r.json()["unit_cost"] == 13.25
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"description": "Hinge 110"})   # another field leaves it alone
    assert r.json()["unit_cost"] == 13.25
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"unit_cost": None})            # an explicit null clears it
    assert r.status_code == 200 and r.json()["unit_cost"] is None
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"unit_cost": 0})               # zero is a price, not "none"
    assert r.json()["unit_cost"] == 0


def test_a_negative_or_oversized_unit_cost_is_refused_and_bulk_import_takes_one():
    c, _, _ = login("drafter")
    assert c.post("/catalog/hardware-materials",
                  json={"sku": "neg", "description": "x", "unit_cost": -1}).status_code == 422
    mid = c.post("/catalog/hardware-materials", json={"sku": "ok", "description": "x"}).json()["material_id"]
    assert c.patch(f"/catalog/hardware-materials/{mid}", json={"unit_cost": -0.01}).status_code == 422
    r = c.post("/catalog/board-materials/bulk", json={"rows": [
        {"code": "BK-1", "sku": "BK-1", "description": "Board", "unit_cost": "45.5"}]})
    assert r.status_code == 200 and r.json()["created"] == 1, r.text
    row = [x for x in c.get("/catalog/board-materials").json()["rows"] if x["sku"] == "BK-1"][0]
    assert row["unit_cost"] == 45.5


# ── Product type (the old system's type, kept beside the tab) ─────────────────

def test_product_type_is_created_listed_searched_patched_and_cleared():
    c, _, _ = login("drafter")
    r = c.post("/catalog/hardware-materials", json={"sku": "pt-1", "description": "Silicone", "product_type": "Supplies"})
    assert r.status_code == 201, r.text
    mid = r.json()["material_id"]
    assert r.json()["product_type"] == "Supplies"
    found = c.get("/catalog/hardware-materials", params={"q": "suppl"}).json()["rows"]       # search finds it by type
    assert [x["material_id"] for x in found] == [mid]
    assert c.patch(f"/catalog/hardware-materials/{mid}", json={"product_type": "Paint"}).json()["product_type"] == "Paint"
    assert c.patch(f"/catalog/hardware-materials/{mid}", json={"description": "x"}).json()["product_type"] == "Paint"
    assert c.patch(f"/catalog/hardware-materials/{mid}", json={"product_type": None}).json()["product_type"] is None
    assert c.post("/catalog/hardware-materials",
                  json={"sku": "pt-2", "description": "x", "product_type": "x" * 65}).status_code == 422
