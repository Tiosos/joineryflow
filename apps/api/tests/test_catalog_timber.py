"""Solid Timber has a catalog table of its own (migration 0074) and works wherever a material is picked."""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login
from .helpers_estimating_orders import _bootstrap
from .conftest import truncate_fixture

_cleanup = truncate_fixture(
    "batch_allocations", "procurement_batches", "project_hardware_catalog_log", "project_hardware_catalog",
    "timber_materials", "hardware_materials",
)
pytestmark = pytest.mark.usefixtures("_cleanup")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
FIELDS = {"colour": "Natural", "finish": "Oiled", "grain": "Straight", "rating": "A", "um": "m",
          "product_website": "https://e.test/x", "thickness_mm": 32, "width_mm": 140, "length_mm": 2400}


def _mk(c, sku="tb-1", **extra):
    r = c.post("/catalog/timber-materials", json={"sku": sku, "description": f"Oak {sku}", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_timber_fields_are_created_listed_patched_and_cleared():
    c, _, _ = login("drafter")
    row = _mk(c, **FIELDS)
    mid = row["material_id"]
    assert row["type"] == "timber" and row["has_image"] is False
    text_keys = ("colour", "finish", "grain", "rating", "um", "product_website")
    assert {k: row[k] for k in text_keys} == {k: FIELDS[k] for k in text_keys}
    assert (row["thickness_mm"], row["width_mm"], row["length_mm"]) == (32, 140, 2400)      # JSON numbers
    assert "shaped" not in row and "grain_locked" not in row                                # not Glass, not Board
    assert [x["material_id"] for x in c.get("/catalog/timber-materials").json()["rows"]] == [mid]

    r = c.patch(f"/catalog/timber-materials/{mid}", json={"colour": "Dark", "width_mm": 90.5, "um": None})
    assert r.status_code == 200 and r.json()["colour"] == "Dark" and r.json()["width_mm"] == 90.5
    assert r.json()["um"] is None and r.json()["grain"] == "Straight"                       # null clears only what it names
    r = c.patch(f"/catalog/timber-materials/{mid}", json={"length_mm": None, "rating": None})
    assert r.json()["length_mm"] is None and r.json()["rating"] is None
    assert c.patch(f"/catalog/timber-materials/{mid}", json={"thickness_mm": -1}).status_code == 422
    assert c.post("/catalog/timber-materials", json={"sku": "t-x", "description": "x", "length_mm": -5}).status_code == 422


def test_other_tables_do_not_take_timber_fields():
    c, _, _ = login("drafter")
    mid = c.post("/catalog/hardware-materials", json={"sku": "hw-t", "description": "Hinge"}).json()["material_id"]
    r = c.patch(f"/catalog/hardware-materials/{mid}", json={"grain": "Straight"})
    assert r.status_code == 200 and "grain" not in r.json()


def test_timber_image_is_stored_served_and_removed_and_appliances_have_none():
    c, _, _ = login("drafter")
    mid = _mk(c)["material_id"]
    assert c.get(f"/catalog/timber-materials/{mid}/image").status_code == 404
    assert c.put(f"/catalog/timber-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    got = c.get(f"/catalog/timber-materials/{mid}/image")
    assert got.content == PNG and c.get(f"/catalog/timber-materials/{mid}").json()["has_image"] is True
    assert c.delete(f"/catalog/timber-materials/{mid}/image").status_code == 204
    assert c.get(f"/catalog/timber-materials/{mid}").json()["has_image"] is False
    ap = c.post("/catalog/appliances", json={"model_number": "ap-t", "sku": "ap-t", "description": "H"}).json()["material_id"]
    assert c.put(f"/catalog/appliances/{ap}/image", files={"file": ("p.png", PNG)}).status_code == 404


def test_timber_of_another_workspace_is_a_404():
    a, _, _ = login("drafter")
    mid = _mk(a)["material_id"]
    a.put(f"/catalog/timber-materials/{mid}/image", files={"file": ("p.png", PNG)})
    b, _, _ = login("admin")
    assert b.get(f"/catalog/timber-materials/{mid}").status_code == 404
    assert b.patch(f"/catalog/timber-materials/{mid}", json={"colour": "x"}).status_code == 404
    assert b.get(f"/catalog/timber-materials/{mid}/image").status_code == 404
    assert b.put(f"/catalog/timber-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 404
    assert b.delete(f"/catalog/timber-materials/{mid}/image").status_code == 404
    assert b.get("/catalog/timber-materials").json()["rows"] == []


def test_the_solid_timber_type_tab_lists_timber_rows_from_its_own_table():
    c, _, _ = login("drafter")
    _mk(c, "tb-t", product_type="Solid Timber")
    c.post("/catalog/hardware-materials", json={"sku": "hw-s", "description": "Hinge", "product_type": "Solid Timber"})
    body = c.get("/catalog/by-type", params={"product_type": "solid timber"}).json()
    assert sorted((g["type"], len(g["rows"])) for g in body["groups"]) == [("hardware", 1), ("timber", 1)]
    assert c.get("/catalog/product-types").json()["types"] == [{"product_type": "Solid Timber", "count": 2}]


def test_a_timber_item_can_be_added_to_a_project_catalog_and_a_hardware_line():
    c, wid, uid = login("manager")
    mid = _mk(c, "tb-h", grain="Straight")["material_id"]
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="TB-1")
        iid = db.execute(text(
            "INSERT INTO items(project_id, num, status) VALUES (:p, 1, 'CLEAR') RETURNING item_id"),
            {"p": pid}).scalar()
        db.commit()
    finally:
        db.close()
    r = c.post(f"/projects/{pid}/hardware_catalog", json={"source_table": "timber_materials", "source_id": mid})
    assert r.status_code in (200, 201), r.text
    rows = c.get(f"/projects/{pid}/hardware_catalog").json()["rows"]
    assert [(x["source_table"], x["source_id"], x["name"]) for x in rows] == [("timber_materials", mid, "Oak tb-h")]
    line = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": rows[0]["catalog_id"], "qty": 3})
    assert line.status_code in (200, 201), line.text
    assert (line.json()["catalog_description"], line.json()["catalog_source_table"]) == ("Oak tb-h", "TIMBER")
    src = c.get("/source_catalog/timber_materials").json()
    assert [(r["source_id"], r["sku"]) for r in src["rows"]] == [(mid, "tb-h")]


def test_a_cv_code_can_be_mapped_to_a_timber_item():
    c, _, _ = login("drafter")
    mid = _mk(c, "tb-cv")["material_id"]
    r = c.post("/catalog/cv-mappings", json={"cv_code": "OAK-1", "target_material_table": "timber_materials",
                                             "target_material_id": mid})
    assert r.status_code == 201, r.text
    rows = c.get("/catalog/cv-mappings").json()["rows"]
    assert rows[0]["target_description"] == "Oak tb-cv"
    assert c.post("/catalog/cv-mappings", json={"cv_code": "OAK-2", "target_material_table": "timber_materials",
                                                "target_material_id": mid + 999}).status_code == 404


def test_a_procurement_batch_can_name_a_timber_item():
    c, wid, uid = login("manager")
    mid = _mk(c, "tb-b")["material_id"]
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="TB-2")
    finally:
        db.close()
    r = c.post("/batches", json={"project_id": pid, "material_type": "TIMBER", "material_id": mid,
                                 "supplier": "Acme", "po_ref": "P1", "qty_ordered": 4})
    assert r.status_code == 201, r.text
    ghost = c.post("/batches", json={"project_id": pid, "material_type": "TIMBER", "material_id": mid + 999,
                                     "qty_ordered": 1})
    assert ghost.status_code == 404


def test_a_quote_line_can_use_timber_as_a_part_and_generate_orders_orders_it():
    ctx = _bootstrap()
    c = ctx["client"]
    s = SessionLocal()
    try:
        mid = s.execute(text(
            "INSERT INTO timber_materials (workspace_id, sku, description, cost_per_unit, default_supplier_id)"
            " VALUES (:w, 'TB-Q', 'Quote oak', 2.50, :v) RETURNING material_id"),
            {"w": ctx["wid"], "v": ctx["vendor_a"]}).scalar()
        s.commit()
    finally:
        s.close()
    cust = c.post("/customers", json={"name": "Oak Co"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "Oak"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "Table", "qty": 1}).json()
    r = c.post(f"/lines/{line['line_id']}/parts", json={"material_type": "TIMBER", "material_id": mid, "qty": 6})
    assert r.status_code in (200, 201), r.text
    assert r.json()["sku_snapshot"] == "TB-Q"
    preview = c.get(f"/revisions/{rid}/order-preview")
    assert preview.status_code == 200, preview.text
    lines = [l for g in preview.json()["groups"] for l in g["lines"]]
    assert [(l["material_type"], l["material_id"], float(l["qty"])) for l in lines] == [("TIMBER", mid, 6.0)]
