"""Supplier orders (Plan V1 Q425-Q432, migrations 0029 + 0031).

The chain these tests pin down is the one the plan calls out:

  Q427/Q428  creating an order against a row carries PROJECT, LOCATION and
             CUTLIST NO. across — and for a related part the cutlist number
             comes from its PARENT, because a related part never has one
  Q429       an order may be created before the parent has a cutlist at all
  Q430       when the parent later gains one, blank references fill in
  Q431       when the parent's cutlist is replaced, linked orders follow, and
             the previous reference stays traceable in the audit row
  Q563/Q564  an order needs no cost centre, and its number is allocated, not
             typed
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
        s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


@pytest.fixture
def ctx():
    suffix = uuid.uuid4().hex[:8]
    slug = f"ord-{suffix}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR', 1) ON CONFLICT DO NOTHING"))
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s,'Orders WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        email, pw = f"po-{suffix}@x.test", "pw"
        s.execute(
            text("INSERT INTO app_user(workspace_id, email, full_name, password_hash,"
                 " auth_role) VALUES (:w, :e, 'Buyer', :p, 'purchase_officer')"),
            {"w": wid, "e": email, "p": hash_password(pw)},
        )
        pid = s.execute(
            text("INSERT INTO projects(project_code, name, workspace_id)"
                 " VALUES(:c, 'Orders Project', :w) RETURNING project_id"),
            {"c": f"ORD-{suffix}", "w": wid},
        ).scalar()
        vendor = s.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Briggs Veneer', 'Board', :w) RETURNING vendor_id"),
            {"w": wid},
        ).scalar()
        parent = s.execute(
            text("""INSERT INTO items(num, project_id, description, status, stage)
                    VALUES (nextval('joinery_number_seq'), :p, 'parent unit',
                            'CLEAR', 'Block B') RETURNING item_id"""),
            {"p": pid},
        ).scalar()
        related = s.execute(
            text("""INSERT INTO items(num, project_id, description, status, row_type,
                                      parent_item_id, related_part_type_key)
                    VALUES (nextval('joinery_number_seq'), :p, 'brass rail', 'CLEAR',
                            'related_part', :par, 'metal') RETURNING item_id"""),
            {"p": pid, "par": parent},
        ).scalar()
        s.commit()
    finally:
        s.close()

    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"client": c, "pid": pid, "vendor": vendor,
            "parent": parent, "related": related, "wid": wid}


def _mint_cutlist(client, pid: int, name="run") -> dict:
    # cutlists are drafter+; the buyer fixture is purchase_officer, so go direct
    s = SessionLocal()
    try:
        cid = s.execute(
            text("INSERT INTO cutlist(project_id, cutlist_no, name)"
                 " VALUES (:p, nextval('joinery_number_seq'), :n) RETURNING cutlist_id"),
            {"p": pid, "n": name},
        ).scalar()
        no = s.execute(
            text("SELECT cutlist_no FROM cutlist WHERE cutlist_id = :c"), {"c": cid}
        ).scalar()
        s.commit()
        return {"cutlist_id": cid, "cutlist_no": no}
    finally:
        s.close()


def _link(item_id: int, cutlist_id: int | None, wid: int):
    """Link/unlink through the cutlist query layer, which is what fires the sync."""
    from app.cutlists import queries as cq
    s = SessionLocal()
    try:
        if cutlist_id is None:
            row = s.execute(text("SELECT cutlist_id FROM items WHERE item_id = :i"),
                            {"i": item_id}).scalar()
            cq.unlink_item(s, cutlist_id=row, item_id=item_id,
                           workspace_id=wid, actor_id=1)
        else:
            cq.link_item(s, cutlist_id=cutlist_id, item_id=item_id,
                         workspace_id=wid, actor_id=1)
        s.commit()
    finally:
        s.close()


def _order_cutlist_no(po_id: int) -> str | None:
    s = SessionLocal()
    try:
        return s.execute(
            text("SELECT cutlist_no FROM purchase_orders WHERE po_id = :o"), {"o": po_id}
        ).scalar()
    finally:
        s.close()


def test_number_is_allocated_and_no_cost_centre_is_needed(ctx):
    """Q564 allocates PO-<year>-0001; Q563 drops the cost-centre requirement."""
    r = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "20 sheets", "category": "Board",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["category"] == "Board"       # a joinery category, not 'Other'

    # Assert the FORMAT and that numbers advance — never an absolute value.
    # `po_number_seq` has no owning table, so `TRUNCATE ... RESTART IDENTITY`
    # does not reset it (the same property `joinery_number_seq` has, recorded
    # in CLAUDE.md): whichever tests ran first have already consumed numbers.
    import re
    m = re.fullmatch(r"PO-(\d{4})-(\d{4,})", body["po_number"])
    assert m, body["po_number"]

    second = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "more", "category": "Hardware",
    }).json()
    m2 = re.fullmatch(r"PO-(\d{4})-(\d{4,})", second["po_number"])
    assert m2, second["po_number"]
    assert int(m2.group(2)) == int(m.group(2)) + 1


def test_creating_against_an_item_prefills_project_and_location(ctx):
    """Q427: PROJECT and LOCATION carry over without being asked for."""
    r = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "panel", "category": "Board",
        "item_id": ctx["parent"],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == ctx["pid"]
    assert body["project_name"] == "Orders Project"
    assert body["location"] == "Block B"


def test_related_part_order_takes_its_parents_cutlist(ctx):
    """Q428: the reference comes from the parent, never the related part."""
    cl = _mint_cutlist(ctx["client"], ctx["pid"])
    _link(ctx["parent"], cl["cutlist_id"], ctx["wid"])

    r = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "brass rail", "category": "Metal",
        "item_id": ctx["related"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["cutlist_no"] == str(cl["cutlist_no"])

    # and the related part still holds no cutlist of its own (Q417)
    s = SessionLocal()
    try:
        own = s.execute(text("SELECT cutlist_id FROM items WHERE item_id = :i"),
                        {"i": ctx["related"]}).scalar()
    finally:
        s.close()
    assert own is None


def test_order_can_be_created_before_any_cutlist_exists(ctx):
    """Q429: blank is legal."""
    r = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "early order", "category": "Metal",
        "item_id": ctx["related"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["cutlist_no"] is None


def test_blank_reference_fills_in_when_the_parent_gains_a_cutlist(ctx):
    """Q430."""
    po_id = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "early order", "category": "Metal",
        "item_id": ctx["related"],
    }).json()["po_id"]
    assert _order_cutlist_no(po_id) is None

    cl = _mint_cutlist(ctx["client"], ctx["pid"])
    _link(ctx["parent"], cl["cutlist_id"], ctx["wid"])

    assert _order_cutlist_no(po_id) == str(cl["cutlist_no"])


def test_replacing_the_parents_cutlist_updates_linked_orders(ctx):
    """Q431 — and the previous reference stays traceable."""
    first = _mint_cutlist(ctx["client"], ctx["pid"], "first")
    _link(ctx["parent"], first["cutlist_id"], ctx["wid"])

    po_id = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "rail", "category": "Metal",
        "item_id": ctx["related"],
    }).json()["po_id"]
    assert _order_cutlist_no(po_id) == str(first["cutlist_no"])

    # replace: unlink, then link to a different cutlist
    second = _mint_cutlist(ctx["client"], ctx["pid"], "second")
    _link(ctx["parent"], None, ctx["wid"])
    _link(ctx["parent"], second["cutlist_id"], ctx["wid"])

    assert _order_cutlist_no(po_id) == str(second["cutlist_no"])

    s = SessionLocal()
    try:
        rows = s.execute(
            text("SELECT payload FROM audit_log WHERE event = 'order.cutlist_sync'"
                 " ORDER BY id")
        ).scalars().all()
    finally:
        s.close()
    olds = [r.get("old_cutlist_no") for r in rows]
    assert str(first["cutlist_no"]) in [o for o in olds if o is not None]


def test_item_orders_endpoint_backs_the_obook_subtab(ctx):
    """Q425's subtab reads this."""
    ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "one", "category": "Metal",
        "item_id": ctx["related"],
    })
    ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "two", "category": "Metal",
        "item_id": ctx["related"],
    })
    r = ctx["client"].get(f"/items/{ctx['related']}/orders")
    assert r.status_code == 200
    assert len(r.json()["orders"]) == 2


def test_cancel_is_soft_and_not_repeatable(ctx):
    po_id = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "x", "category": "Other",
    }).json()["po_id"]

    assert ctx["client"].delete(f"/orders/{po_id}").status_code == 204
    assert ctx["client"].get(f"/orders/{po_id}").json()["status"] == "Cancelled"
    again = ctx["client"].delete(f"/orders/{po_id}")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "ALREADY_CANCELLED"


def test_unknown_vendor_and_item_are_404(ctx):
    r = ctx["client"].post("/orders", json={
        "vendor_id": 999999, "description": "x", "category": "Other",
    })
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "VENDOR_NOT_FOUND"

    r2 = ctx["client"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "x", "category": "Other",
        "item_id": 999999,
    })
    assert r2.status_code == 404
    assert r2.json()["detail"]["code"] == "ITEM_NOT_FOUND"


def test_categories_include_joinery_values(ctx):
    r = ctx["client"].get("/order-categories")
    assert r.status_code == 200
    keys = {c["category_key"] for c in r.json()}
    assert {"Board", "Hardware", "Benchtop", "Metal"} <= keys   # 0031's additions
    assert "Other" in keys                                       # legacy preserved


# ---------------------------------------------------------------------------
# GET /orders — the workspace-wide list behind the Orderbook page (Q418/Q504)
# ---------------------------------------------------------------------------

def test_workspace_list_spans_projects_and_is_newest_first(ctx):
    """Orderbook has always been the CROSS-project surface, so this is not
    `/projects/{pid}/orders` with a loop around it."""
    c = ctx["client"]
    other_pid = None
    s = SessionLocal()
    try:
        other_pid = s.execute(
            text("INSERT INTO projects(project_code, name, workspace_id)"
                 " VALUES('ORD-OTHER', 'Second Project', :w) RETURNING project_id"),
            {"w": ctx["wid"]},
        ).scalar()
        s.commit()
    finally:
        s.close()

    first = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "edge tape",
        "category": "Board", "project_id": ctx["pid"],
    }).json()
    second = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "brass rail",
        "category": "Metal", "project_id": other_pid,
    }).json()

    r = c.get("/orders")
    assert r.status_code == 200, r.text
    rows = r.json()["orders"]
    assert [o["po_id"] for o in rows] == [second["po_id"], first["po_id"]]
    assert {o["project_id"] for o in rows} == {ctx["pid"], other_pid}


def test_workspace_list_includes_an_order_with_no_project(ctx):
    """Q554: such an order reaches its workspace through its VENDOR. No project
    page can show it, so if Orderbook dropped it too it would be invisible."""
    c = ctx["client"]
    made = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "office consumables",
        "category": "Office", "project_name": "Workshop stock",
    }).json()
    assert made["project_id"] is None

    rows = c.get("/orders").json()["orders"]
    assert made["po_id"] in [o["po_id"] for o in rows]


def test_workspace_list_filters_by_status_supplier_and_search(ctx):
    c = ctx["client"]
    s2 = SessionLocal()
    try:
        other_vendor = s2.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Plyco', 'Board', :w) RETURNING vendor_id"),
            {"w": ctx["wid"]},
        ).scalar()
        s2.commit()
    finally:
        s2.close()

    a = c.post("/orders", json={"vendor_id": ctx["vendor"],
                                "description": "walnut veneer",
                                "category": "Board"}).json()
    b = c.post("/orders", json={"vendor_id": other_vendor,
                                "description": "birch ply",
                                "category": "Board"}).json()
    c.patch(f"/orders/{b['po_id']}", json={"status": "Approved"})

    approved = c.get("/orders", params={"status": "Approved"}).json()["orders"]
    assert [o["po_id"] for o in approved] == [b["po_id"]]

    plyco = c.get("/orders", params={"supplier": "Plyco"}).json()["orders"]
    assert [o["po_id"] for o in plyco] == [b["po_id"]]

    # Q418 arrives with a PO number; the description is the other useful key.
    by_number = c.get("/orders", params={"search": a["po_number"]}).json()["orders"]
    assert [o["po_id"] for o in by_number] == [a["po_id"]]
    by_text = c.get("/orders", params={"search": "walnut"}).json()["orders"]
    assert [o["po_id"] for o in by_text] == [a["po_id"]]


def test_workspace_list_is_isolated_from_other_workspaces(ctx):
    """The literal /orders path must also not be swallowed by /orders/{po_id}."""
    c = ctx["client"]
    mine = c.post("/orders", json={"vendor_id": ctx["vendor"],
                                   "description": "mine",
                                   "category": "Board",
                                   "project_id": ctx["pid"]}).json()

    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        other_ws = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s,'Other WS') RETURNING id"),
            {"s": f"ord-other-{suffix}"},
        ).scalar()
        other_vendor = s.execute(
            text("INSERT INTO vendors(name, category, workspace_id)"
                 " VALUES('Foreign Supplier', 'Board', :w) RETURNING vendor_id"),
            {"w": other_ws},
        ).scalar()
        foreign_po = s.execute(
            text("""INSERT INTO purchase_orders
                      (po_number, vendor_id, requester_id, description, category)
                    VALUES ('PO-FOREIGN-1', :v,
                            (SELECT id FROM app_user WHERE workspace_id = :w2 LIMIT 1),
                            'not yours', 'Board')
                    RETURNING po_id"""),
            {"v": other_vendor, "w2": ctx["wid"]},
        ).scalar()
        s.commit()
    finally:
        s.close()

    rows = c.get("/orders").json()["orders"]
    ids = [o["po_id"] for o in rows]
    assert mine["po_id"] in ids
    assert foreign_po not in ids


# Line CRUD ----------------------------------------------------------------
# PATCH/DELETE on an individual po_line_items row — the gap left after PO
# generation (#13) started creating real multi-line orders with nothing to
# edit them with; add_line() (POST) already existed but had no HTTP-level
# test of its own either.

def _make_order_with_line(ctx: dict) -> dict:
    c = ctx["client"]
    po = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "materials", "category": "Board",
    }).json()
    line = c.post(f"/orders/{po['po_id']}/lines", json={
        "item_description": "18mm MDF", "quantity": "3", "unit_price": "45.00",
        "sku": "BM-001", "unit": "sheet",
    }).json()
    line_id = line["lines"][0]["line_id"]
    return {"po_id": po["po_id"], "line_id": line_id}


def test_add_line_returns_the_order_with_the_new_line(ctx):
    c = ctx["client"]
    po = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "materials", "category": "Board",
    }).json()
    r = c.post(f"/orders/{po['po_id']}/lines", json={
        "item_description": "18mm MDF", "quantity": "3", "unit_price": "45.00",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["lines"]) == 1
    assert body["lines"][0]["item_description"] == "18mm MDF"
    assert float(body["lines"][0]["line_total"]) == 135.0
    # the rollup's write is a real mutation, matching every other order
    # mutation's own updated_at behavior
    assert body["updated_at"] != po["updated_at"]
    # header total_amount (0.00 by default — create_order never sets it)
    # now reflects the line just added.
    assert float(body["total_amount"]) == 135.0


def test_add_line_sums_multiple_lines_into_header_total(ctx):
    c = ctx["client"]
    po = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "materials", "category": "Board",
    }).json()
    c.post(f"/orders/{po['po_id']}/lines", json={
        "item_description": "18mm MDF", "quantity": "3", "unit_price": "45.00",
    })
    r = c.post(f"/orders/{po['po_id']}/lines", json={
        "item_description": "Hinges", "quantity": "10", "unit_price": "2.50",
    })
    assert float(r.json()["total_amount"]) == 160.0  # 135.00 + 25.00


def test_recomputed_total_amount_bumps_its_field_version(ctx):
    # `add_line`'s rollup must be a real write to `total_amount` (bumping
    # its version), not a bypass — otherwise stale bookkeeping could make a
    # later conflict check on this field lie about what actually changed.
    c = ctx["client"]
    po = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "materials", "category": "Board",
    }).json()
    assert po.get("field_versions", {}).get("total_amount", 0) == 0
    after_line = c.post(f"/orders/{po['po_id']}/lines", json={
        "item_description": "18mm MDF", "quantity": "3", "unit_price": "45.00",
    }).json()
    assert after_line["field_versions"]["total_amount"] == 1


def test_total_amount_is_not_directly_patchable_once_lines_exist(ctx):
    # Two writers for one field (a manual header PATCH and the line rollup)
    # would defeat §L regardless of which one loses, so once an order has
    # lines the rollup is its only writer: a direct PATCH is silently
    # ignored rather than raced against, clobbered, or conflict-checked.
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    before = c.get(f"/orders/{ids['po_id']}").json()
    assert before["total_amount"] == "135.00"
    r = c.patch(f"/orders/{ids['po_id']}", json={"total_amount": "999.00"})
    assert r.status_code == 200, r.text
    assert r.json()["total_amount"] == "135.00"  # unchanged, not 999.00
    # a header-only order (no lines) keeps direct PATCH access
    po2 = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "no lines", "category": "Board",
    }).json()
    r2 = c.patch(f"/orders/{po2['po_id']}", json={"total_amount": "50.00"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["total_amount"] == "50.00"


def test_stale_total_amount_expected_version_does_not_block_an_unrelated_write(ctx):
    # A batch PATCH naming both `status` and `total_amount` (each with its
    # own `expected_versions`, per the documented "read from a prior GET"
    # pattern) must not fail on total_amount's version alone once lines
    # exist and it's no longer a field this PATCH actually writes — that
    # would block the unrelated, legitimate `status` change.
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    before = c.get(f"/orders/{ids['po_id']}").json()
    stale_total_version = before["field_versions"]["total_amount"]
    # move total_amount's version on, so `stale_total_version` really is stale
    c.patch(f"/orders/{ids['po_id']}/lines/{ids['line_id']}", json={"quantity": "9"})
    r = c.patch(f"/orders/{ids['po_id']}", json={
        "status": "Approved",
        "total_amount": "1.00",  # ignored anyway (lines exist), but still sent
        "expected_versions": {"status": 0, "total_amount": stale_total_version},
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Approved"


def test_field_conflict_current_value_serializes_decimal_as_string(ctx):
    # `current_value` must match this API's own Decimal-as-string
    # convention (orders-types.ts) — jsonable_encoder alone would turn it
    # into a JSON number instead.
    c = ctx["client"]
    po = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "materials", "category": "Board",
    }).json()
    assert c.patch(f"/orders/{po['po_id']}", json={"unit_cost": "12.50"}).status_code == 200
    r = c.patch(f"/orders/{po['po_id']}", json={
        "unit_cost": "1.00", "expected_versions": {"unit_cost": 0},
    })
    assert r.status_code == 409
    current_value = r.json()["detail"]["conflicts"]["unit_cost"]["current_value"]
    assert isinstance(current_value, str)
    assert float(current_value) == 12.50


def test_patch_line_updates_editable_fields(ctx):
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    r = c.patch(
        f"/orders/{ids['po_id']}/lines/{ids['line_id']}",
        json={"quantity": "5", "unit_price": "50.00"},
    )
    assert r.status_code == 200, r.text
    line = r.json()["lines"][0]
    assert float(line["quantity"]) == 5.0
    assert float(line["unit_price"]) == 50.0
    assert float(line["line_total"]) == 250.0
    # sku/description untouched by a partial patch
    assert line["item_description"] == "18mm MDF"
    assert float(r.json()["total_amount"]) == 250.0


@pytest.mark.parametrize("field", ["item_description", "quantity", "unit_price"])
def test_patch_line_rejects_null_for_not_null_columns(ctx, field):
    # These three are NOT NULL on po_line_items — an explicit null must be a
    # clean 422, not a raw IntegrityError/500 from the UPDATE.
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    r = c.patch(f"/orders/{ids['po_id']}/lines/{ids['line_id']}", json={field: None})
    assert r.status_code == 422


def test_patch_line_404_for_unknown_line(ctx):
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    r = c.patch(f"/orders/{ids['po_id']}/lines/999999", json={"quantity": "1"})
    assert r.status_code == 404


def test_patch_line_404_for_unknown_line_with_no_patchable_fields(ctx):
    # An empty body (or one naming only a non-patchable field, e.g.
    # `line_number`) must still 404 for a line that doesn't exist — the
    # no-op early-return path can't skip the existence check.
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    r = c.patch(f"/orders/{ids['po_id']}/lines/999999", json={})
    assert r.status_code == 404


def test_patch_line_404_when_line_belongs_to_a_different_order(ctx):
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    other_po = c.post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "other", "category": "Board",
    }).json()
    r = c.patch(
        f"/orders/{other_po['po_id']}/lines/{ids['line_id']}",
        json={"quantity": "1"},
    )
    assert r.status_code == 404


def test_remove_line_deletes_it(ctx):
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    r = c.delete(f"/orders/{ids['po_id']}/lines/{ids['line_id']}")
    assert r.status_code == 200, r.text
    assert r.json()["lines"] == []
    # no lines left -> header total drops back to 0.00
    assert float(r.json()["total_amount"]) == 0.0


def test_remove_line_404_for_unknown_line(ctx):
    ids = _make_order_with_line(ctx)
    c = ctx["client"]
    r = c.delete(f"/orders/{ids['po_id']}/lines/999999")
    assert r.status_code == 404


def test_line_routes_require_orderbook_write(ctx):
    ids = _make_order_with_line(ctx)
    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        s.execute(
            text("INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
                 " VALUES (:w, :e, 'Viewer', :p, 'viewer')"),
            {"w": ctx["wid"], "e": f"viewer-{suffix}@x.test", "p": hash_password("pw")},
        )
        s.commit()
    finally:
        s.close()
    c2 = TestClient(app)
    r = c2.post("/auth/login", json={
        "workspace_slug": _workspace_slug(ctx["wid"]), "email": f"viewer-{suffix}@x.test", "password": "pw",
    })
    assert r.status_code == 200, r.text
    assert c2.patch(f"/orders/{ids['po_id']}/lines/{ids['line_id']}",
                    json={"quantity": "1"}).status_code == 403
    assert c2.delete(f"/orders/{ids['po_id']}/lines/{ids['line_id']}").status_code == 403


def test_patch_line_cross_workspace_404(ctx):
    ids = _make_order_with_line(ctx)
    other = _bootstrap_other_workspace_client()
    r = other.patch(f"/orders/{ids['po_id']}/lines/{ids['line_id']}", json={"quantity": "1"})
    assert r.status_code == 404


def _workspace_slug(wid: int) -> str:
    s = SessionLocal()
    try:
        return s.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": wid}).scalar()
    finally:
        s.close()


def _bootstrap_other_workspace_client() -> TestClient:
    suffix = uuid.uuid4().hex[:8]
    slug = f"ord-line-other-{suffix}"
    email = f"buyer-{suffix}@x.test"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s,'Other Line WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        s.execute(
            text("INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
                 " VALUES (:w, :e, 'Buyer', :p, 'purchase_officer')"),
            {"w": wid, "e": email, "p": hash_password("pw")},
        )
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c
