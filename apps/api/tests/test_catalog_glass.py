"""Glass has a catalog table of its own (migration 0069) and works wherever a material is picked."""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login
from .helpers_estimating_orders import _bootstrap
from .conftest import truncate_fixture

_cleanup = truncate_fixture(
    "batch_allocations", "procurement_batches", "project_hardware_catalog_log", "project_hardware_catalog",
    "glass_materials", "hardware_materials",
)
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"colour": "Silver", "edge_finish": "FPAR", "glass_type": "Float", "power_point": "0", "um": "Tot",
          "product_website": "https://e.test/x", "length_mm": 1264, "width_mm": 474, "thickness_mm": 4, "shaped": True}


def _mk(c, sku="ed-1", **extra):
    r = c.post("/catalog/glass-materials", json={"sku": sku, "description": f"Edge {sku}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_glass_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **FIELDS)
    mid = row["material_id"]
    assert row["type"] == "glass" and row["has_image"] is False
    text_keys = ("colour", "edge_finish", "glass_type", "power_point", "um", "product_website", "shaped")
    assert {k: row[k] for k in text_keys} == {k: FIELDS[k] for k in text_keys}
    assert (row["length_mm"], row["width_mm"], row["thickness_mm"]) == (1264, 474, 4)       # JSON numbers
    assert [x["material_id"] for x in c.get("/catalog/glass-materials").json()["rows"]] == [mid]

    r = c.patch(f"/catalog/glass-materials/{mid}", json={"colour": "Clear", "width_mm": 500.5, "um": None})
    assert r.status_code == 200 and r.json()["colour"] == "Clear" and r.json()["width_mm"] == 500.5
    assert r.json()["um"] is None and r.json()["glass_type"] == "Float"             # null clears only what it names
    r = c.patch(f"/catalog/glass-materials/{mid}", json={"length_mm": None, "shaped": False})
    assert r.json()["length_mm"] is None and r.json()["shaped"] is False
    assert c.patch(f"/catalog/glass-materials/{mid}", json={"shaped": None}).json()["shaped"] is False   # NOT NULL: dropped
    assert c.patch(f"/catalog/glass-materials/{mid}", json={"thickness_mm": -1}).status_code == 422
    assert c.post("/catalog/glass-materials", json={"sku": "g-x", "description": "x", "length_mm": -5}).status_code == 422


def test_other_tables_do_not_take_glass_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/hardware-materials", json={"sku": "hw-e", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"glass_type": "Float"})
    assert r.status_code == 200 and "glass_type" not in r.json()


def test_glass_image_is_stored_served_and_removed_and_hardware_has_none():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/glass-materials/{mid}/image").status_code == 404
    assert c.put(f"/catalog/glass-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    got = c.get(f"/catalog/glass-materials/{mid}/image")
    assert got.content == PNG and c.get(f"/catalog/glass-materials/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/glass-materials/{mid}/image").status_code == 204
    assert c.get(f"/catalog/glass-materials/{mid}").json()["has_image"] is False
    hw = c.post("/catalog/hardware-materials", json={"sku": "hw-i", "description": "H"}).json()["material_id"]
    assert c.put(f"/catalog/hardware-materials/{hw}/image", files={"file": ("p.png", PNG)}).status_code == 404


def test_glass_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/glass-materials/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/glass-materials/{mid}").status_code == 404
    assert b.patch(f"/catalog/glass-materials/{mid}", json={"colour": "x"}).status_code == 404
    assert b.get(f"/catalog/glass-materials/{mid}/image").status_code == 404
    assert b.put(f"/catalog/glass-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/glass-materials/{mid}/image").status_code == 404
    assert b.get("/catalog/glass-materials").json()["rows"] == []


def test_the_glass_type_tab_lists_glass_rows_from_its_own_table():
    c, _, _ = login("drafter")
    _mk(c, "ed-t", product_type="Glass")
    c.post("/catalog/hardware-materials", json={"sku": "hw-t", "description": "Hinge", "product_type": "Glass"})
    body = c.get("/catalog/by-type", params={"product_type": "glass"}).json()
    assert sorted((g["type"], len(g["rows"])) for g in body["groups"]) == [("glass", 1), ("hardware", 1)]
    assert c.get("/catalog/product-types").json()["types"] == [{"product_type": "Glass", "count": 2}]


def test_an_glass_item_can_be_added_to_a_project_catalog_and_a_hardware_line():
    c, wid, uid = login("manager")
    mid = _mk(c, "ed-h", glass_type="Float")["material_id"]
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="ED-1")
        iid = db.execute(text(
            "INSERT INTO items(project_id, num, status) VALUES (:p, 1, 'CLEAR') RETURNING item_id"),
            {"p": pid}).scalar()
        db.commit()
    finally:
        db.close()
    r = c.post(f"/projects/{pid}/hardware_catalog", json={"source_table": "glass_materials", "source_id": mid})
    assert r.status_code in (200, 201), r.text
    rows = c.get(f"/projects/{pid}/hardware_catalog").json()["rows"]
    assert [(x["source_table"], x["source_id"], x["name"]) for x in rows] == [("glass_materials", mid, "Edge ed-h")]
    line = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": rows[0]["catalog_id"], "qty": 3})
    assert line.status_code in (200, 201), line.text
    assert (line.json()["catalog_description"], line.json()["catalog_source_table"]) == ("Edge ed-h", "GLASS")
    src = c.get("/source_catalog/glass_materials").json()
    assert [(r["source_id"], r["sku"]) for r in src["rows"]] == [(mid, "ed-h")]


def test_a_cv_code_can_be_mapped_to_an_glass_item():
    c, _, _ = login("drafter")
    mid = _mk(c, "ed-cv")["material_id"]
    r = c.post("/catalog/cv-mappings", json={"cv_code": "EDGE-1", "target_material_table": "glass_materials",
                                             "target_material_id": mid})
    assert r.status_code == 201, r.text
    rows = c.get("/catalog/cv-mappings").json()["rows"]
    assert rows[0]["target_description"] == "Edge ed-cv"
    assert c.post("/catalog/cv-mappings", json={"cv_code": "EDGE-2", "target_material_table": "glass_materials",
                                                "target_material_id": mid + 999}).status_code == 404


def test_a_procurement_batch_can_name_an_glass_item():
    c, wid, uid = login("manager")
    mid = _mk(c, "ed-b")["material_id"]
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="ED-2")
    finally:
        db.close()
    r = c.post("/batches", json={"project_id": pid, "material_type": "GLASS", "material_id": mid,
                                 "supplier": "Acme", "po_ref": "P1", "qty_ordered": 4})
    assert r.status_code == 201, r.text
    ghost = c.post("/batches", json={"project_id": pid, "material_type": "GLASS", "material_id": mid + 999,
                                     "qty_ordered": 1})
    assert ghost.status_code == 404


def test_a_quote_line_can_use_glass_as_a_part_and_generate_orders_orders_it():
    ctx = _bootstrap()
    c = ctx["client"]
    s = SessionLocal()
    try:
        mid = s.execute(text(
            "INSERT INTO glass_materials (workspace_id, sku, description, cost_per_unit, default_supplier_id)"
            " VALUES (:w, 'GL-Q', 'Quote glass', 2.50, :v) RETURNING material_id"),
            {"w": ctx["wid"], "v": ctx["vendor_a"]}).scalar()
        s.commit()
    finally:
        s.close()
    cust = c.post("/customers", json={"name": "Edge Co"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Edge"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "Edged", "qty": 1}).json()
    r = c.post(f"/lines/{line['line_id']}/parts", json={"material_type": "GLASS", "material_id": mid, "qty": 6})
    assert r.status_code in (200, 201), r.text
    assert r.json()["sku_snapshot"] == "GL-Q"
    preview = c.get(f"/revisions/{rid}/order-preview")
    assert preview.status_code == 200, preview.text
    lines = [l for g in preview.json()["groups"] for l in g["lines"]]
    assert [(l["material_type"], l["material_id"], float(l["qty"])) for l in lines] == [("GLASS", mid, 6.0)]
