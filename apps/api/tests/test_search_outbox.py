"""Migration 0033's triggers feed search_outbox (plan task B2).

Each test runs inside the rollback `db` fixture and reads only outbox rows
written after its own baseline, so seed or earlier-test rows never interfere.
"""
import pytest
from sqlalchemy import text

from app.catalog.queries import create_catalog_row, patch_catalog_row

from .search_helpers import make_order, make_tree, make_vendor


@pytest.fixture
def tree(db, workspace_id):
    return make_tree(db, workspace_id)


@pytest.fixture
def since(db):
    """Returns a function listing (entity_type, entity_id) enqueued since the
    fixture was created, in order."""
    base = db.execute(text("SELECT COALESCE(MAX(outbox_id), 0) FROM search_outbox")).scalar()

    def rows():
        return [tuple(r) for r in db.execute(text(
            "SELECT entity_type, entity_id FROM search_outbox"
            " WHERE outbox_id > :b ORDER BY outbox_id"), {"b": base})]

    def reset():
        nonlocal base
        base = db.execute(text("SELECT COALESCE(MAX(outbox_id), 0) FROM search_outbox")).scalar()

    rows.reset = reset
    return rows


def test_insert_update_delete_each_enqueue_one_row(db, workspace_id, since):
    pid = db.execute(text(
        "INSERT INTO projects(project_code, name, workspace_id)"
        " VALUES ('SRCH-2', 'P', :w) RETURNING project_id"), {"w": workspace_id}).scalar()
    db.execute(text("UPDATE projects SET builder = 'B' WHERE project_id = :p"), {"p": pid})
    db.execute(text("DELETE FROM projects WHERE project_id = :p"), {"p": pid})
    assert since() == [("project", pid)] * 3


def test_tree_inserts_enqueue_their_own_kinds(db, since, tree):
    # `since` is listed before `tree`, so pytest builds it first and the tree's
    # own inserts land after the baseline. Area and room are not indexed
    # types; they only fan out into items (Q579).
    assert since() == [
        ("project", tree["project"]),
        ("cutlist", tree["cutlist"]),
        ("item", tree["item"]),
    ]


def test_item_save_does_not_fan_out(db, tree, since):
    db.execute(text("UPDATE items SET description = 'Island bench v2' WHERE item_id = :i"),
               {"i": tree["item"]})
    assert since() == [("item", tree["item"])]


def test_project_code_rename_fans_out_to_children(db, tree, since):
    db.execute(text("UPDATE projects SET project_code = 'SRCH-1B' WHERE project_id = :p"),
               {"p": tree["project"]})
    got = since()
    assert ("project", tree["project"]) in got
    assert ("item", tree["item"]) in got
    assert ("cutlist", tree["cutlist"]) in got


def test_project_edit_of_unembedded_column_does_not_fan_out(db, tree, since):
    db.execute(text("UPDATE projects SET builder = 'Other' WHERE project_id = :p"),
               {"p": tree["project"]})
    assert since() == [("project", tree["project"])]


@pytest.mark.parametrize("sql,key", [
    ("UPDATE area SET name = 'Level 3' WHERE area_id = :id", "area"),
    ("UPDATE room SET rm_desc = 'Scullery' WHERE room_id = :id", "room"),
    ("UPDATE cutlist SET cutlist_no = nextval('joinery_number_seq') WHERE cutlist_id = :id",
     "cutlist"),
])
def test_embedded_parent_rename_enqueues_item(db, tree, since, sql, key):
    db.execute(text(sql), {"id": tree[key]})
    assert ("item", tree["item"]) in since()


def test_area_sort_order_change_does_not_fan_out(db, tree, since):
    db.execute(text("UPDATE area SET sort_order = 5 WHERE area_id = :a"), {"a": tree["area"]})
    assert since() == []


def test_cutlist_delete_enqueues_unlinked_item(db, tree, since):
    """ON DELETE SET NULL on items.cutlist_id fires the item's own trigger."""
    db.execute(text("DELETE FROM cutlist WHERE cutlist_id = :c"), {"c": tree["cutlist"]})
    got = since()
    assert ("cutlist", tree["cutlist"]) in got
    assert ("item", tree["item"]) in got


def test_catalog_dynamic_sql_path_enqueues(db, workspace_id, since):
    """catalog/queries.py builds table names at runtime — the path a grep for
    `INSERT INTO board_materials` misses and the reason for triggers (Q578)."""
    mid = create_catalog_row(db, type_="board", workspace_id=workspace_id,
                             fields={"code": "SRCH-BM", "description": "Oak", "sku": "SRCH-BM"})
    patch_catalog_row(db, type_="board", mid=mid, workspace_id=workspace_id,
                      fields={"description": "Oak veneer"})
    assert since() == [("board_materials", mid)] * 2


def test_vendor_rename_enqueues_its_orders(db, tree, since):
    vid = make_vendor(db, tree["w"], "Acme")
    po = make_order(db, tree["w"], vid, "PO-TEST-SRCH", tree["project"])
    since.reset()
    db.execute(text("UPDATE vendors SET name = 'Acme Stone' WHERE vendor_id = :v"), {"v": vid})
    assert since() == [("supplier", vid), ("order", po)]


def test_null_parent_id_is_skipped(db, workspace_id, since):
    """An order with no project must not make the project fan-out insert a NULL."""
    vid = make_vendor(db, workspace_id, "Solo")
    po = make_order(db, workspace_id, vid, "PO-TEST-SRCH2")
    assert since() == [("supplier", vid), ("order", po)]


def test_unknown_kind_is_rejected(db):
    with pytest.raises(Exception, match="search_outbox_entity_type_check"):
        db.execute(text("INSERT INTO search_outbox(entity_type, entity_id) VALUES ('nope', 1)"))
