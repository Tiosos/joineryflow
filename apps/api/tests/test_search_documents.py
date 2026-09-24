"""Document builders (plan task C1; spec §3.1, §3.3)."""
import json

import pytest
from sqlalchemy import text

from app.search import documents as D

from .search_helpers import make_order, make_tree, make_vendor

KEYS = {"id", "type", "entity_id", "workspace_id", "project_id", "project_code",
        "codes", "title", "subtitle", "body", "status", "archived", "updated_at", "url"}


def _one(db, sql, **p):
    return db.execute(text(sql), p).scalar()


@pytest.fixture
def tree(db, workspace_id):
    return make_tree(db, workspace_id)


def test_item_document(db, tree):
    d = D.load(db, "item", [tree["item"]])[tree["item"]]
    assert set(d) == KEYS
    assert d["id"] == f"item-{tree['item']}" and d["type"] == "item"
    assert d["workspace_id"] == tree["w"] and d["project_code"] == "SRCH-1"
    assert d["subtitle"] == "SRCH-1 · Level 2 · 2.04 Kitchen"
    assert d["url"] == f"/items/{tree['item']}"
    num, cno = db.execute(text(
        "SELECT i.num, c.cutlist_no FROM items i JOIN cutlist c USING (cutlist_id)"
        " WHERE i.item_id = :i"), {"i": tree["item"]}).one()
    assert d["codes"] == [str(num), str(cno)]


def test_codes_are_distinct(db, tree):
    num = _one(db, "SELECT num FROM items WHERE item_id = :i", i=tree["item"])
    db.execute(text("UPDATE items SET code = :c WHERE item_id = :i"),
               {"c": str(num), "i": tree["item"]})
    codes = D.load(db, "item", [tree["item"]])[tree["item"]]["codes"]
    assert len(codes) == len(set(codes))


def test_soft_deleted_item_has_no_document(db, tree):
    db.execute(text("UPDATE items SET deleted = true WHERE item_id = :i"), {"i": tree["item"]})
    assert D.load(db, "item", [tree["item"]]) == {}


def test_void_item_is_archived(db, tree):
    db.execute(text("UPDATE items SET void_flag = true WHERE item_id = :i"), {"i": tree["item"]})
    assert D.load(db, "item", [tree["item"]])[tree["item"]]["archived"] is True


def test_related_part_document(db, tree):
    rp = _one(db, """
        INSERT INTO items(num, project_id, description, status, row_type,
                          parent_item_id, related_part_type_key)
        VALUES (nextval('joinery_number_seq'), :p, 'Steel frame', 'LIVE', 'related_part',
                :parent, 'metal') RETURNING item_id""", p=tree["project"], parent=tree["item"])
    d = D.load(db, "item", [rp])[rp]
    assert d["id"] == f"related_part-{rp}" and d["type"] == "related_part"
    assert d["url"] == f"/tracking?project_id={tree['project']}"
    assert D.doc_ids("item", rp) == [f"item-{rp}", f"related_part-{rp}"]


def test_orphan_order_reaches_workspace_through_vendor(db, workspace_id):
    """Q554: an order with no project is still indexed in its workspace."""
    vid = make_vendor(db, workspace_id, "Solo")
    po = make_order(db, workspace_id, vid, "PO-TEST-DOC1")
    d = D.load(db, "order", [po])[po]
    assert d["workspace_id"] == workspace_id and d["project_id"] is None
    assert d["url"] == "/orderbook?order=PO-TEST-DOC1"


def test_secrets_and_money_never_indexed(db, tree):
    """Spec §3.3: the allow-list, pinned by planting sentinel values."""
    vid = make_vendor(db, tree["w"], "Acme")
    db.execute(text("""UPDATE vendors SET bank_account = 'SENTINEL-BANK',
                       tax_id = 'SENTINEL-TAX', payment_terms = 'SENTINEL-TERMS'
                       WHERE vendor_id = :v"""), {"v": vid})
    po = make_order(db, tree["w"], vid, "PO-TEST-DOC2", tree["project"])
    # grand_total is generated from total_amount; assert the sentinel is really
    # in the row, or the check below would pass vacuously.
    db.execute(text("UPDATE purchase_orders SET unit_cost = 98765.43, quantity = 1,"
                    " total_amount = 98765.43 WHERE po_id = :p"), {"p": po})
    money = [str(v) for v in db.execute(text(
        "SELECT unit_cost, total_amount, gst_amount, grand_total FROM purchase_orders"
        " WHERE po_id = :p"), {"p": po}).one()]
    assert all(v not in ("None", "0") for v in money)
    cu = _one(db, """INSERT INTO customer(workspace_id, name, abn)
                     VALUES (:w, 'Client', 'SENTINEL-ABN') RETURNING customer_id""", w=tree["w"])
    blob = json.dumps([
        D.load(db, "supplier", [vid])[vid],
        D.load(db, "order", [po])[po],
        D.load(db, "customer", [cu])[cu],
    ])
    for sentinel in ("SENTINEL-BANK", "SENTINEL-TAX", "SENTINEL-TERMS",
                     "SENTINEL-ABN", *money):
        assert sentinel not in blob


def test_supplier_has_no_link(db, workspace_id):
    vid = make_vendor(db, workspace_id, "Acme")
    assert D.load(db, "supplier", [vid])[vid]["url"] is None  # Q579


def test_material_ids_carry_their_table(db, workspace_id):
    mid = _one(db, """INSERT INTO board_materials(code, description, sku, workspace_id)
                      VALUES ('DOC-BM', 'Oak board', NULL, :w) RETURNING material_id""",
               w=workspace_id)
    d = D.load(db, "board_materials", [mid])[mid]
    assert d["id"] == f"material-board_materials-{mid}" and d["type"] == "material"
    assert d["codes"] == ["DOC-BM"]
    assert d["url"] == "/catalog?tab=board&q=Oak%20board"  # no sku → description
    assert D.doc_ids("board_materials", mid) == [d["id"]]


def test_archived_catalog_row(db, workspace_id):
    mid = _one(db, """INSERT INTO board_materials(code, description, sku, workspace_id, archived_at)
                      VALUES ('DOC-BM2', 'Old', 'DOC-BM2', :w, now()) RETURNING material_id""",
               w=workspace_id)
    assert D.load(db, "board_materials", [mid])[mid]["archived"] is True


def test_every_kind_has_a_loader():
    assert set(D.LOADERS) == set(D.KINDS)


def test_missing_ids_are_absent(db):
    for kind in D.KINDS:
        assert D.load(db, kind, [987654321]) == {}
