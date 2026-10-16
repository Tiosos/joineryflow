"""Edging has a catalog table of its own (migration 0069) and works wherever a material is picked."""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login
from .helpers_estimating_orders import _bootstrap
from .conftest import truncate_fixture

_cleanup = truncate_fixture(
    "batch_allocations", "procurement_batches", "project_hardware_catalog_log", "project_hardware_catalog",
    "edging_materials", "hardware_materials",
)
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"colour": "Casentino Beech Woodmatt", "edge_type": "PVC", "um": "ea", "product_website": "https://e.test/x",
          "roll_length_m": 100, "edge_width_mm": 21, "edge_thickness_mm": 1, "glued": True}


def _mk(c, sku="ed-1", **extra):
    r = c.post("/catalog/edging-materials", json={"sku": sku, "description": f"Edge {sku}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_edging_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **FIELDS)
    mid = row["material_id"]
    assert row["type"] == "edging" and row["has_image"] is False
    assert {k: row[k] for k in ("colour", "edge_type", "um", "product_website", "glued")} == {
        k: FIELDS[k] for k in ("colour", "edge_type", "um", "product_website", "glued")}
    assert (row["roll_length_m"], row["edge_width_mm"], row["edge_thickness_mm"]) == (100, 21, 1)   # JSON numbers
    assert [x["material_id"] for x in c.get("/catalog/edging-materials").json()["rows"]] == [mid]

    r = c.patch(f"/catalog/edging-materials/{mid}", json={"colour": "Black", "edge_width_mm": 22.5, "um": None})
    assert r.status_code == 200 and r.json()["colour"] == "Black" and r.json()["edge_width_mm"] == 22.5
    assert r.json()["um"] is None and r.json()["edge_type"] == "PVC"             # null clears only what it names
    r = c.patch(f"/catalog/edging-materials/{mid}", json={"roll_length_m": None, "glued": False})
    assert r.json()["roll_length_m"] is None and r.json()["glued"] is False
    assert c.patch(f"/catalog/edging-materials/{mid}", json={"glued": None}).json()["glued"] is False   # NOT NULL: dropped
    assert c.patch(f"/catalog/edging-materials/{mid}", json={"edge_thickness_mm": -1}).status_code == 422
    assert c.post("/catalog/edging-materials", json={"sku": "e-x", "description": "x", "roll_length_m": -5}).status_code == 422


def test_other_tables_do_not_take_edging_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/hardware-materials", json={"sku": "hw-e", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"edge_type": "PVC"})
    assert r.status_code == 200 and "edge_type" not in r.json()


def test_edging_image_is_stored_served_and_removed_and_hardware_has_none():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/edging-materials/{mid}/image").status_code == 404
    assert c.put(f"/catalog/edging-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    got = c.get(f"/catalog/edging-materials/{mid}/image")
    assert got.content == PNG and c.get(f"/catalog/edging-materials/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/edging-materials/{mid}/image").status_code == 204
    assert c.get(f"/catalog/edging-materials/{mid}").json()["has_image"] is False
    hw = c.post("/catalog/hardware-materials", json={"sku": "hw-i", "description": "H"}).json()["material_id"]
    assert c.put(f"/catalog/hardware-materials/{hw}/image", files={"file": ("p.png", PNG)}).status_code == 404


def test_edging_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/edging-materials/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/edging-materials/{mid}").status_code == 404
    assert b.patch(f"/catalog/edging-materials/{mid}", json={"colour": "x"}).status_code == 404
    assert b.get(f"/catalog/edging-materials/{mid}/image").status_code == 404
    assert b.put(f"/catalog/edging-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/edging-materials/{mid}/image").status_code == 404
    assert b.get("/catalog/edging-materials").json()["rows"] == []


def test_the_edging_type_tab_lists_edging_rows_from_its_own_table():
    c, _, _ = login("drafter")
    _mk(c, "ed-t", product_type="Edging")
    c.post("/catalog/hardware-materials", json={"sku": "hw-t", "description": "Hinge", "product_type": "Edging"})
    body = c.get("/catalog/by-type", params={"product_type": "edging"}).json()
    assert sorted((g["type"], len(g["rows"])) for g in body["groups"]) == [("edging", 1), ("hardware", 1)]
    assert c.get("/catalog/product-types").json()["types"] == [{"product_type": "Edging", "count": 2}]


def test_an_edging_item_can_be_added_to_a_project_catalog_and_a_hardware_line():
    c, wid, uid = login("manager")
    mid = _mk(c, "ed-h", edge_type="PVC")["material_id"]
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="ED-1")
        iid = db.execute(text(
            "INSERT INTO items(project_id, num, status) VALUES (:p, 1, 'CLEAR') RETURNING item_id"),
            {"p": pid}).scalar()
        db.commit()
    finally:
        db.close()
    r = c.post(f"/projects/{pid}/hardware_catalog", json={"source_table": "edging_materials", "source_id": mid})
    assert r.status_code in (200, 201), r.text
    rows = c.get(f"/projects/{pid}/hardware_catalog").json()["rows"]
    assert [(x["source_table"], x["source_id"], x["name"]) for x in rows] == [("edging_materials", mid, "Edge ed-h")]
    line = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": rows[0]["catalog_id"], "qty": 3})
    assert line.status_code in (200, 201), line.text
    assert (line.json()["catalog_description"], line.json()["catalog_source_table"]) == ("Edge ed-h", "EDGING")
    src = c.get("/source_catalog/edging_materials").json()
    assert [(r["source_id"], r["sku"]) for r in src["rows"]] == [(mid, "ed-h")]


def test_a_cv_code_can_be_mapped_to_an_edging_item():
    c, _, _ = login("drafter")
    mid = _mk(c, "ed-cv")["material_id"]
    r = c.post("/catalog/cv-mappings", json={"cv_code": "EDGE-1", "target_material_table": "edging_materials",
                                             "target_material_id": mid})
    assert r.status_code == 201, r.text
    rows = c.get("/catalog/cv-mappings").json()["rows"]
    assert rows[0]["target_description"] == "Edge ed-cv"
    assert c.post("/catalog/cv-mappings", json={"cv_code": "EDGE-2", "target_material_table": "edging_materials",
                                                "target_material_id": mid + 999}).status_code == 404


def test_a_procurement_batch_can_name_an_edging_item():
    c, wid, uid = login("manager")
    mid = _mk(c, "ed-b")["material_id"]
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="ED-2")
    finally:
        db.close()
    r = c.post("/batches", json={"project_id": pid, "material_type": "EDGING", "material_id": mid,
                                 "supplier": "Acme", "po_ref": "P1", "qty_ordered": 4})
    assert r.status_code == 201, r.text
    ghost = c.post("/batches", json={"project_id": pid, "material_type": "EDGING", "material_id": mid + 999,
                                     "qty_ordered": 1})
    assert ghost.status_code == 404


def test_a_quote_line_can_use_edging_and_generate_orders_orders_it():
    ctx = _bootstrap()
    c = ctx["client"]
    s = SessionLocal()
    try:
        mid = s.execute(text(
            "INSERT INTO edging_materials (workspace_id, sku, description, cost_per_unit, default_supplier_id)"
            " VALUES (:w, 'ED-Q', 'Quote edge', 2.50, :v) RETURNING material_id"),
            {"w": ctx["wid"], "v": ctx["vendor_a"]}).scalar()
        s.commit()
    finally:
        s.close()
    cust = c.post("/customers", json={"name": "Edge Co"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Edge"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "Edged", "qty": 1}).json()
    r = c.post(f"/lines/{line['line_id']}/hardware", json={"material_type": "EDGING", "material_id": mid, "qty": 6})
    assert r.status_code in (200, 201), r.text
    assert r.json()["sku_snapshot"] == "ED-Q"
    preview = c.get(f"/revisions/{rid}/order-preview")
    assert preview.status_code == 200, preview.text
    lines = [l for g in preview.json()["groups"] for l in g["lines"]]
    assert [(l["material_type"], l["material_id"], float(l["qty"])) for l in lines] == [("EDGING", mid, 6.0)]
