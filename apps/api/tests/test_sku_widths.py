"""A catalog SKU is as long as its `sku` column and every copy of it can hold that (2026-10-20, `0079`).

Seven catalog `sku` columns are `varchar(255)`; the copies on a quote line (`estimate_line_part` /
`estimate_line_hardware.sku_snapshot`) and on an order (`po_line_items.sku`, `purchase_orders.product_code`)
were 64 / 100, so a long Glass SKU on a quote line was a 500 (`StringDataRightTruncation`). The catalog's
Create and PATCH caps of Board, Custom, Benchtop, Appliance and Hire were 64 for the same reason.
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login
from .helpers_estimating_orders import _advance_to_won, _bootstrap, _convert

_cleanup = truncate_fixture("board_materials", "custom_made", "benchtop_materials", "appliances",
                            "equipment_hire", "glass_materials", "timber_materials", "hardware_materials",
                            "edging_materials")
pytestmark = pytest.mark.usefixtures("_cleanup")

# slug -> the table's own code field on Create (a separate column, still 64 wide)
_WIDE = {
    "board-materials": "code", "custom-made": "internal_ref", "benchtop-materials": "slab_id",
    "appliances": "model_number", "equipment-hire": "contract_ref", "glass-materials": None,
    "timber-materials": None,
}


def _create_body(slug, sku, project_id=None):
    body = {"sku": sku, "description": "d"}
    code_field = _WIDE.get(slug)
    if code_field:
        body[code_field] = uuid.uuid4().hex[:12]
    if slug == "equipment-hire":
        body["project_id"] = project_id
    return body


@pytest.mark.parametrize("slug", list(_WIDE))
def test_a_sku_of_100_and_255_characters_is_created_and_patched_and_256_is_a_422(slug):
    c, _, uid = login("admin")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid)
    finally:
        db.close()
    made = c.post(f"/catalog/{slug}", json=_create_body(slug, "a" * 100, pid))
    assert made.status_code == 201, made.text
    row = made.json()
    mid = row.get("material_id") or row["hire_id"]
    assert row["sku"] == "a" * 100
    for n in (100, 255):
        r = c.patch(f"/catalog/{slug}/{mid}", json={"sku": chr(98 + (n % 7)) * n})
        assert r.status_code == 200, (n, r.text)
        assert r.json()["sku"] == chr(98 + (n % 7)) * n
    assert c.patch(f"/catalog/{slug}/{mid}", json={"sku": "y" * 256}).status_code == 422
    assert c.post(f"/catalog/{slug}", json=_create_body(slug, "z" * 256, pid)).status_code == 422
    top = c.post(f"/catalog/{slug}", json=_create_body(slug, "t" * 255, pid))
    assert top.status_code == 201, top.text


@pytest.mark.parametrize("slug", ["hardware-materials", "edging-materials"])
def test_hardware_and_edging_stay_at_their_real_64(slug):
    c, _, _ = login("admin")
    assert c.post(f"/catalog/{slug}", json={"sku": "k" * 65, "description": "d"}).status_code == 422
    mid = c.post(f"/catalog/{slug}", json={"sku": "k" * 64, "description": "d"}).json()["material_id"]
    assert c.patch(f"/catalog/{slug}/{mid}", json={"sku": "y" * 65}).status_code == 422


# kind -> (table, own cost column, the table's separate code column, is a quote part)
_ONTO_A_QUOTE = {
    "BOARD": ("board_materials", "cost_per_sheet", "code", True),
    "CUSTOM": ("custom_made", "cost", "internal_ref", True),
    "BENCHTOP": ("benchtop_materials", "cost_per_slab", "slab_id", True),
    "GLASS": ("glass_materials", "cost_per_unit", None, True),
    "TIMBER": ("timber_materials", "cost_per_unit", None, True),
    "APPLIANCE": ("appliances", "cost_per_unit", "model_number", False),
}


def test_a_150_character_sku_goes_onto_a_quote_line_and_through_generate_orders():
    ctx = _bootstrap()
    c = ctx["client"]
    cust = c.post("/customers", json={"name": "W"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "W"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "Long SKUs", "qty": 1}).json()
    skus: dict[tuple[str, int], str] = {}
    s = SessionLocal()
    try:
        for kind, (table, cost_col, code_col, is_part) in _ONTO_A_QUOTE.items():
            sku = f"{kind}-" + uuid.uuid4().hex * 5          # 6..13 + 160 characters, over 100
            sku = sku[:150]
            cols = ["workspace_id", "sku", "description", "default_supplier_id", cost_col]
            vals = [":w", ":sku", "'long sku'", ":v", "10"]
            if code_col:
                cols.append(code_col)
                vals.append(":code")
            mid = s.execute(
                text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING material_id"),
                {"w": ctx["wid"], "sku": sku, "v": ctx["vendor_a"], "code": uuid.uuid4().hex[:12]},
            ).scalar()
            skus[(kind, mid)] = sku
        s.commit()
    finally:
        s.close()
    for (kind, mid), sku in skus.items():
        is_part = _ONTO_A_QUOTE[kind][3]
        r = c.post(f"/lines/{line['line_id']}/{'parts' if is_part else 'hardware'}",
                   json={"material_type": kind, "material_id": mid, "qty": 1})
        assert r.status_code == 201, (kind, r.text)
        assert r.json()["sku_snapshot"] == sku, kind
    _advance_to_won(c, rid)
    _convert(c, rid)
    gen = c.post(f"/revisions/{rid}/generate-orders")
    assert gen.status_code == 200, gen.text
    s = SessionLocal()
    try:
        for (kind, mid), sku in skus.items():
            table = _ONTO_A_QUOTE[kind][0]
            got = s.execute(text("SELECT sku FROM po_line_items WHERE material_table = :t AND material_id = :m"),
                            {"t": table, "m": mid}).scalar()
            assert got == sku, kind
    finally:
        s.close()


def test_an_order_takes_a_product_code_as_long_as_a_catalog_sku():
    buyer, wid, _ = login("purchase_officer")
    vendor = SessionLocal()
    try:
        vid = vendor.execute(text("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                                  " RETURNING vendor_id"), {"w": wid}).scalar()
        vendor.commit()
    finally:
        vendor.close()
    r = buyer.post("/orders", json={"vendor_id": vid, "description": "o", "total_amount": "10",
                                    "product_code": "p" * 255})
    assert r.status_code == 201, r.text
    oid = r.json()["po_id"]
    assert r.json()["product_code"] == "p" * 255
    assert buyer.patch(f"/orders/{oid}", json={"product_code": "q" * 200}).status_code == 200
    assert buyer.post("/orders", json={"vendor_id": vid, "description": "o", "total_amount": "10",
                                       "product_code": "p" * 256}).status_code == 422
    # the PO summary view (rebuilt by 0079) still reads it
    s = SessionLocal()
    try:
        assert s.execute(text("SELECT product_code FROM v_po_summary WHERE po_id = :o"), {"o": oid}).scalar() \
            == "q" * 200
    finally:
        s.close()


# ---- order lines: the SKU cap is the column's (po_line_items.sku varchar(255)) ----

def _order_with_a_line(buyer, wid):
    s = SessionLocal()
    try:
        vid = s.execute(text("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w)"
                             " RETURNING vendor_id"), {"w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    r = buyer.post("/orders", json={"vendor_id": vid, "description": "o", "total_amount": "10"})
    assert r.status_code == 201, r.text
    return r.json()["po_id"]


def test_an_order_line_sku_is_capped_at_255_on_create_and_patch():
    buyer, wid, _ = login("purchase_officer")
    oid = _order_with_a_line(buyer, wid)
    line = {"item_description": "x", "quantity": "1", "unit_price": "1"}
    ok = buyer.post(f"/orders/{oid}/lines", json={**line, "sku": "s" * 255})
    assert ok.status_code == 201, ok.text
    lid = ok.json()["lines"][0]["line_id"]
    assert buyer.post(f"/orders/{oid}/lines", json={**line, "sku": "s" * 256}).status_code == 422
    assert buyer.patch(f"/orders/{oid}/lines/{lid}", json={"sku": "t" * 255}).status_code == 200
    assert buyer.patch(f"/orders/{oid}/lines/{lid}", json={"sku": "u" * 256}).status_code == 422
    assert buyer.patch(f"/orders/{oid}/lines/{lid}", json={"sku": None}).status_code == 200


def test_an_order_line_description_and_unit_are_capped_at_their_columns():
    buyer, wid, _ = login("purchase_officer")
    oid = _order_with_a_line(buyer, wid)
    line = {"item_description": "d" * 500, "quantity": "1", "unit_price": "1", "unit": "u" * 50}
    ok = buyer.post(f"/orders/{oid}/lines", json=line)
    assert ok.status_code == 201, ok.text
    lid = ok.json()["lines"][0]["line_id"]
    assert buyer.post(f"/orders/{oid}/lines", json={**line, "item_description": "d" * 501}).status_code == 422
    assert buyer.post(f"/orders/{oid}/lines", json={**line, "unit": "u" * 51}).status_code == 422
    assert buyer.patch(f"/orders/{oid}/lines/{lid}", json={"item_description": "e" * 500, "unit": "m" * 50}).status_code == 200
    assert buyer.patch(f"/orders/{oid}/lines/{lid}", json={"item_description": "e" * 501}).status_code == 422
    assert buyer.patch(f"/orders/{oid}/lines/{lid}", json={"unit": "m" * 51}).status_code == 422


# ---- Convert-to-Project: a 255-character catalog description onto parts.part_name (varchar(128)) ----

def test_a_long_catalog_description_converts_to_a_project_and_part_name_is_cut_to_its_column():
    ctx = _bootstrap()
    c = ctx["client"]
    desc = "".join(str(i % 10) for i in range(255))
    ids = {}
    s = SessionLocal()
    try:
        for kind, (table, cost_col, code_col, is_part) in _ONTO_A_QUOTE.items():
            cols = ["workspace_id", "sku", "description", cost_col]
            vals = [":w", ":sku", ":d", "10"]
            if code_col:
                cols.append(code_col)
                vals.append(":code")
            ids[kind] = s.execute(
                text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)}) RETURNING material_id"),
                {"w": ctx["wid"], "sku": f"{kind}-{uuid.uuid4().hex[:8]}", "d": desc,
                 "code": uuid.uuid4().hex[:12]},
            ).scalar()
        s.commit()
    finally:
        s.close()
    cust = c.post("/customers", json={"name": "W"}).json()
    est = c.post("/estimates", json={"customer_id": cust["customer_id"], "title": "W"}).json()
    rid = est["current_revision_id"]
    line = c.post(f"/revisions/{rid}/lines", json={"description": "d" * 255, "qty": 1}).json()
    for kind, mid in ids.items():
        is_part = _ONTO_A_QUOTE[kind][3]
        r = c.post(f"/lines/{line['line_id']}/{'parts' if is_part else 'hardware'}",
                   json={"material_type": kind, "material_id": mid, "qty": 1})
        assert r.status_code == 201, (kind, r.text)
        if is_part:
            assert r.json()["description_snapshot"] == desc, kind     # the snapshot keeps the full text
    _advance_to_won(c, rid)
    pid = _convert(c, rid)
    s = SessionLocal()
    try:
        names = [r[0] for r in s.execute(text(
            "SELECT p.part_name FROM parts p JOIN modules m ON m.module_id = p.module_id"
            " JOIN items i ON i.item_id = m.item_id WHERE i.project_id = :p"), {"p": pid})]
        assert len(names) == 5
        assert all(n == desc[:128] for n in names)
        full = s.execute(text("SELECT count(*) FROM estimate_line_part WHERE description_snapshot = :d"),
                         {"d": desc}).scalar()
        assert full == 5
    finally:
        s.close()
