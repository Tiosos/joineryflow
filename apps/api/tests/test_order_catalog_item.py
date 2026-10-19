"""The order pop-up shows the catalog row whose SKU is the order's product code (read-only, nothing stored on the order).

`GET /orders/{id}/catalog-item` and its picture route `GET /orders/{id}/catalog-item/image?n=`, gated by `orderbook`.
"""
import pytest

from app.auth import rbac_engine
from app.catalog.queries import REGISTRY
from app.order_tabs.queries import CATALOG_MATCH_ORDER

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace
from .helpers_po import _order, _sql, make_ws

_cleanup = truncate_fixture()

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

# slug, body (besides sku/description), a field the type adds, its expected value
CASES = {
    "board": ("board-materials", lambda s: {"code": s, "colour": "White", "um": "sht", "product_website": "https://b.test/x"},
              "colour", "White"),
    "benchtop": ("benchtop-materials", lambda s: {"slab_id": s, "underside": "Bal", "pieces": 2}, "pieces", 2),
    "hardware": ("hardware-materials", lambda s: {"brand": "Blum", "hardware_type": "Hinge"}, "brand", "Blum"),
    "edging": ("edging-materials", lambda s: {"colour": "Oak", "roll_length_m": 50, "glued": True}, "roll_length_m", 50.0),
    "glass": ("glass-materials", lambda s: {"glass_type": "Low-E", "thickness_mm": 6, "shaped": True}, "glass_type", "Low-E"),
    "timber": ("timber-materials", lambda s: {"grain": "Straight", "length_mm": 2400}, "grain", "Straight"),
    "custom_made": ("custom-made", lambda s: {"internal_ref": s, "um": "ea"}, None, None),
    "appliance": ("appliances", lambda s: {"model_number": s, "um": "ea"}, None, None),
}


@pytest.fixture
def ws():
    w = make_ws()
    w["cat"], _ = login_same_workspace(w["wid"], "manager")
    return w


def _mk(c, slug, sku, **extra):
    r = c.post(f"/catalog/{slug}", json={"sku": sku, "description": f"Desc {sku}", **extra})
    assert r.status_code == 201, r.text
    body = r.json()
    return body.get("material_id") or body["hire_id"]


def _items(c, oid):
    r = c.get(f"/orders/{oid}/catalog-item")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_match_order_covers_every_catalog_table():
    assert set(CATALOG_MATCH_ORDER) == set(REGISTRY) and len(CATALOG_MATCH_ORDER) == len(REGISTRY)


@pytest.mark.parametrize("type_", list(CASES))
def test_each_table_is_matched_by_sku_ignoring_case_and_spaces(ws, type_):
    slug, body, field, value = CASES[type_]
    sku = f"Zq-{type_}-1"
    mid = _mk(ws["cat"], slug, sku, **body(sku))
    oid = _order(ws, product_code=f"  {sku.upper()} ")
    [it] = _items(ws["buyer"], oid)
    assert it["type"] == type_ and it["id"] == mid and it["sku"] == sku and it["description"] == f"Desc {sku}"
    assert it["archived"] is False and it["has_image"] is False
    if field:
        assert it["fields"][field] == value
    assert "um" not in it["fields"] and "product_website" not in it["fields"]
    # the catalog row's own fields, not copied onto the order
    o = ws["buyer"].get(f"/orders/{oid}").json()
    assert o["product_code"].strip() == sku.upper()


def test_hire_matches_only_the_orders_own_project(ws):
    c, wid = ws["cat"], ws["wid"]
    _, _, uid = login("manager", wid=wid)
    p1 = _sql("INSERT INTO projects(project_code, name, pm_id, workspace_id) VALUES ('H1','H1',:u,:w) RETURNING project_id",
              u=uid, w=wid)
    p2 = _sql("INSERT INTO projects(project_code, name, pm_id, workspace_id) VALUES ('H2','H2',:u,:w) RETURNING project_id",
              u=uid, w=wid)
    r = c.post("/catalog/equipment-hire", json={"contract_ref": "eh-q", "sku": "EH-Q", "description": "Scissor lift",
                                                "project_id": p1, "um": "day", "product_website": "https://h.test"})
    assert r.status_code == 201, r.text
    hid = r.json()["hire_id"]
    on_p1 = _order(ws, product_code="eh-q", project_id=p1)
    [it] = _items(ws["buyer"], on_p1)
    assert it["type"] == "hire" and it["id"] == hid and it["um"] == "day" and it["product_website"] == "https://h.test"
    assert _items(ws["buyer"], _order(ws, product_code="eh-q", project_id=p2)) == []
    assert _items(ws["buyer"], _order(ws, product_code="eh-q")) == []


def test_no_match_and_empty_code_are_an_empty_list_not_a_404(ws):
    _mk(ws["cat"], "hardware-materials", "hw-real")
    assert _items(ws["buyer"], _order(ws, product_code="nope")) == []
    assert _items(ws["buyer"], _order(ws)) == []
    assert _items(ws["buyer"], _order(ws, product_code="   ")) == []


def test_live_rows_win_over_archived_and_a_code_in_several_tables_lists_all(ws):
    c = ws["cat"]
    old = _mk(c, "board-materials", "dup-1", code="DUP-OLD")
    assert c.post(f"/catalog/board-materials/{old}/archive").status_code in (200, 204)
    live_hw = _mk(c, "hardware-materials", "DUP-1")
    live_board = _mk(c, "board-materials", "DUP-1", code="DUP-NEW")  # sku is unique per table, case-sensitively
    oid = _order(ws, product_code="dup-1")
    got = _items(ws["buyer"], oid)
    assert [(i["type"], i["id"], i["archived"]) for i in got] == [
        ("board", live_board, False), ("hardware", live_hw, False), ("board", old, True)]


def test_money_notes_and_supplier_columns_are_not_in_the_reply(ws):
    _mk(ws["cat"], "hardware-materials", "hw-money", unit_cost=12.5, notes="internal", default_supplier="Acme")
    [it] = _items(ws["buyer"], _order(ws, product_code="hw-money"))
    assert set(it) == {"type", "id", "sku", "description", "product_type", "um", "product_website", "archived",
                       "has_image", "fields"}
    assert set(it["fields"]) == {"brand", "hardware_type"}


def test_another_workspaces_order_and_catalog_rows(ws):
    mid = _mk(ws["cat"], "hardware-materials", "x-shared")
    oid = _order(ws, product_code="x-shared")
    other, _, _ = login("admin", prefix="oc-b")
    ghost = other.get("/orders/99999999/catalog-item")
    foreign = other.get(f"/orders/{oid}/catalog-item")
    assert foreign.status_code == 404 and (foreign.status_code, foreign.json()) == (ghost.status_code, ghost.json())
    assert other.get(f"/orders/{oid}/catalog-item/image").status_code == 404
    # another workspace's catalog row is never matched by this workspace's order
    ob = make_ws()
    assert _items(ob["buyer"], _order(ob, product_code="x-shared")) == []
    assert mid


def test_picture_is_served_through_orderbook_and_only_for_a_matching_row(ws):
    c = ws["cat"]
    mid = _mk(c, "glass-materials", "gl-pic")
    oid = _order(ws, product_code="gl-pic")
    buyer = ws["buyer"]
    assert buyer.get(f"/orders/{oid}/catalog-item/image").status_code == 404        # row has no picture
    assert c.put(f"/catalog/glass-materials/{mid}/image", files={"file": ("p.png", PNG)}).status_code == 204
    [it] = _items(buyer, oid)
    assert it["has_image"] is True
    got = buyer.get(f"/orders/{oid}/catalog-item/image")
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert buyer.get(f"/orders/{oid}/catalog-item/image", params={"n": 1}).status_code == 404   # no second match
    # an order whose code matches nothing cannot reach that picture
    assert buyer.get(f"/orders/{_order(ws, product_code='other')}/catalog-item/image").status_code == 404


def test_picture_needs_orderbook_read_not_catalog_read(ws, monkeypatch):
    c = ws["cat"]
    mid = _mk(c, "glass-materials", "gl-perm")
    c.put(f"/catalog/glass-materials/{mid}/image", files={"file": ("p.png", PNG)})
    oid = _order(ws, product_code="gl-perm")
    viewer, _ = login_same_workspace(ws["wid"], "viewer", "NoCat")
    nocat = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], "catalog": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", nocat)
    assert viewer.get(f"/catalog/glass-materials/{mid}/image").status_code == 403
    assert viewer.get(f"/orders/{oid}/catalog-item/image").status_code == 200
    noorders = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], "orderbook": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", noorders)
    assert viewer.get(f"/orders/{oid}/catalog-item").status_code == 403
    assert viewer.get(f"/orders/{oid}/catalog-item/image").status_code == 403


def test_cancelled_order_still_shows_the_item(ws):
    _mk(ws["cat"], "hardware-materials", "hw-cancel")
    oid = _order(ws, product_code="hw-cancel")
    assert ws["buyer"].delete(f"/orders/{oid}").status_code == 204
    assert len(_items(ws["buyer"], oid)) == 1


def test_board_reply_carries_sheet_size_and_thickness_as_json_numbers(ws):
    _mk(ws["cat"], "board-materials", "bd-size", code="BD-SIZE", colour="White",
        sheet_len_mm=3600, sheet_wid_mm=1200, thickness_mm=0.7)
    _mk(ws["cat"], "board-materials", "bd-none", code="BD-NONE")
    [it] = _items(ws["buyer"], _order(ws, product_code="bd-size"))
    assert set(it["fields"]) == {"colour", "substrate", "finish", "sided", "grain", "rating", "hmr",
                                 "sheet_len_mm", "sheet_wid_mm", "thickness_mm"}
    assert (it["fields"]["sheet_len_mm"], it["fields"]["sheet_wid_mm"], it["fields"]["thickness_mm"]) == (3600, 1200, 0.7)
    [none] = _items(ws["buyer"], _order(ws, product_code="bd-none"))
    assert (none["fields"]["sheet_len_mm"], none["fields"]["thickness_mm"]) == (None, None)
