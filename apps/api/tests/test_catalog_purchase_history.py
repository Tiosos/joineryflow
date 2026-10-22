"""Purchase history of a catalog row: what this workspace has paid for its SKU (read-only).

`GET /catalog/{slug}/{mid}/purchase-history`, gated by `catalog:read` and `orderbook:read`.
Orders are matched on product code = SKU, as the order pop-up's catalog block does.
"""
import pytest
from app.auth import rbac_engine

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace
from .helpers_po import _order, _sql, make_ws

_cleanup = truncate_fixture()


@pytest.fixture
def ws():
    w = make_ws()
    w["cat"], _ = login_same_workspace(w["wid"], "manager")
    return w


def _board(c, sku):
    r = c.post("/catalog/board-materials", json={"sku": sku, "code": sku, "description": f"Desc {sku}"})
    assert r.status_code == 201, r.text
    return r.json()["material_id"]


def _history(c, mid, slug="board-materials"):
    r = c.get(f"/catalog/{slug}/{mid}/purchase-history")
    assert r.status_code == 200, r.text
    return r.json()


def _placed(ws, sku, *, qty, unit, on, status="Approved", **extra):
    oid = _order(ws, product_code=sku, quantity=qty, unit_cost=unit, total_amount=str(float(qty) * float(unit)), **extra)
    _sql("UPDATE purchase_orders SET date_ordered = :d, status = :s WHERE po_id = :o", d=on, s=status, o=oid)
    return oid


def test_lists_placed_orders_for_the_sku_newest_first_with_latest_and_average(ws):
    mid = _board(ws["cat"], "PH-1")
    old = _placed(ws, " ph-1 ", qty=2, unit="40.00", on="2026-01-10")        # trimmed, case-insensitive
    new = _placed(ws, "PH-1", qty=5, unit="50.00", on="2026-03-10", status="Delivered", vendor="v2")
    _placed(ws, "PH-1", qty=1, unit="99.00", on="2026-04-01", status="Cancelled")
    _placed(ws, "PH-1", qty=1, unit="99.00", on="2026-04-02", status="Rejected")
    _order(ws, product_code="PH-1", quantity=1, unit_cost="99.00", total_amount="99.00")   # raised, not placed
    _placed(ws, "PH-OTHER", qty=1, unit="99.00", on="2026-04-03")
    h = _history(ws["cat"], mid)
    assert [o["po_id"] for o in h["orders"]] == [new, old]
    assert h["orders"][0]["vendor_name"] == "Other" and h["orders"][0]["status"] == "Delivered"
    assert float(h["latest_price"]) == 50.0 and float(h["average_price"]) == 45.0


def test_a_delivered_order_with_no_order_date_counts_and_the_price_falls_back_to_total_over_quantity(ws):
    mid = _board(ws["cat"], "PH-2")
    oid = _order(ws, product_code="PH-2", quantity=4, total="100.00")
    _sql("UPDATE purchase_orders SET status = 'Delivered', unit_cost = NULL, date_ordered = NULL WHERE po_id = :o", o=oid)
    h = _history(ws["cat"], mid)
    assert [o["po_id"] for o in h["orders"]] == [oid] and float(h["orders"][0]["unit_price"]) == 25.0


def test_nothing_ordered_is_an_empty_history_not_an_error(ws):
    h = _history(ws["cat"], _board(ws["cat"], "PH-3"))
    assert h == {"orders": [], "latest_price": None, "average_price": None}


def test_another_workspaces_orders_and_rows_stay_out(ws):
    mid = _board(ws["cat"], "PH-4")
    other = make_ws()
    _placed(other, "PH-4", qty=1, unit="10.00", on="2026-02-01")
    mine = _placed(ws, "PH-4", qty=1, unit="20.00", on="2026-02-02")
    assert [o["po_id"] for o in _history(ws["cat"], mid)["orders"]] == [mine]
    stranger, _, _ = login("admin")
    real = stranger.get(f"/catalog/board-materials/{mid}/purchase-history")
    ghost = stranger.get("/catalog/board-materials/999999999/purchase-history")
    assert real.status_code == ghost.status_code == 404 and real.json() == ghost.json()


def test_an_equipment_hire_row_only_sees_its_own_projects_orders(ws):
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('PH', 'PH A', :w) RETURNING project_id", w=ws["wid"])
    other = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('PX', 'PH B', :w) RETURNING project_id", w=ws["wid"])
    r = ws["cat"].post("/catalog/equipment-hire", json={"sku": "PH-HIRE", "description": "Scissor lift", "project_id": pid,
                                                        "contract_ref": "C-1"})
    assert r.status_code == 201, r.text
    hid = r.json()["hire_id"]
    mine = _placed(ws, "PH-HIRE", qty=1, unit="300.00", on="2026-02-02", project_id=pid)
    _placed(ws, "PH-HIRE", qty=1, unit="999.00", on="2026-02-03", project_id=other)
    assert [o["po_id"] for o in _history(ws["cat"], hid, "equipment-hire")["orders"]] == [mine]


def test_it_needs_catalog_read_and_orderbook_read(ws, monkeypatch):
    mid = _board(ws["cat"], "PH-5")
    viewer, _ = login_same_workspace(ws["wid"], "viewer")
    url = f"/catalog/board-materials/{mid}/purchase-history"
    assert viewer.get(url).status_code == 200
    for module in ("catalog", "orderbook"):
        matrix = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], module: set()}}
        monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
        assert viewer.get(url).status_code == 403, module
        monkeypatch.undo()
