"""`GET /orders/unmatched`: orders of a material type with no catalog row behind their product code.

Those orders drop out of the Material Summary's Ordered figures and a catalog row's purchase history
(both match on product code = SKU), so the Orderbook lists them for fixing.
"""
import pytest

from .conftest import truncate_fixture
from .helpers import login_same_workspace
from .helpers_po import _order, _sql, make_ws

_cleanup = truncate_fixture()


@pytest.fixture
def ws():
    w = make_ws()
    w["cat"], _ = login_same_workspace(w["wid"], "manager")
    return w


def _unmatched(c):
    r = c.get("/orders/unmatched")
    assert r.status_code == 200, r.text
    return r.json()


def _mk(c, slug, sku, **extra):
    r = c.post(f"/catalog/{slug}", json={"sku": sku, "description": f"Desc {sku}", **extra})
    assert r.status_code == 201, r.text


def test_lists_material_orders_whose_code_is_blank_or_not_a_catalog_sku(ws):
    _mk(ws["cat"], "board-materials", "UM-1", code="UM-1")
    _mk(ws["cat"], "hardware-materials", "UM-HW")
    matched = _order(ws, category="Board", product_code="  um-1 ")          # trimmed, case-insensitive
    hw = _order(ws, category="Hardware", product_code="UM-HW")              # another table
    blank = _order(ws, category="Board")
    typo = _order(ws, category="Board", product_code="UM-11")
    spaces = _order(ws, category="Hardware", product_code="   ")
    got = _unmatched(ws["buyer"])
    assert set(got["po_ids"]) == {blank, typo, spaces} and got["count"] == 3
    assert not {matched, hw} & set(got["po_ids"])


def test_other_order_types_and_closed_orders_are_left_out(ws):
    _order(ws, category="Delivery", product_code="NO-SUCH")                 # not a catalog material
    _order(ws, category="Wages")
    cancelled = _order(ws, category="Board", product_code="NO-SUCH-2")
    rejected = _order(ws, category="Board", product_code="NO-SUCH-3")
    _sql("UPDATE purchase_orders SET status = 'Cancelled' WHERE po_id = :o", o=cancelled)
    _sql("UPDATE purchase_orders SET status = 'Rejected' WHERE po_id = :o", o=rejected)
    delivered = _order(ws, category="Board", product_code="NO-SUCH-4")
    _sql("UPDATE purchase_orders SET status = 'Delivered' WHERE po_id = :o", o=delivered)
    assert _unmatched(ws["buyer"])["po_ids"] == [delivered]                 # a Delivered one is still worth fixing


def test_an_archived_row_still_matches(ws):
    _mk(ws["cat"], "glass-materials", "UM-GL")
    mid = ws["cat"].get("/catalog/glass-materials").json()["rows"][0]["material_id"]
    assert ws["cat"].post(f"/catalog/glass-materials/{mid}/archive").status_code == 200
    _order(ws, category="Glass", product_code="UM-GL")
    assert _unmatched(ws["buyer"]) == {"count": 0, "po_ids": []}


def test_an_equipment_hire_row_matches_only_its_own_projects_orders(ws):
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('UA', 'UM A', :w) RETURNING project_id", w=ws["wid"])
    other = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('UB', 'UM B', :w) RETURNING project_id", w=ws["wid"])
    r = ws["cat"].post("/catalog/equipment-hire", json={"sku": "UM-HIRE", "description": "Lift", "project_id": pid, "contract_ref": "C"})
    assert r.status_code == 201, r.text
    mine = _order(ws, category="Hire", product_code="UM-HIRE", project_id=pid)
    elsewhere = _order(ws, category="Hire", product_code="UM-HIRE", project_id=other)
    got = _unmatched(ws["buyer"])["po_ids"]
    assert elsewhere in got and mine not in got


def test_another_workspaces_catalog_does_not_match(ws):
    other = make_ws()
    other["cat"], _ = login_same_workspace(other["wid"], "manager")
    _mk(other["cat"], "board-materials", "UM-X", code="UM-X")
    mine = _order(ws, category="Board", product_code="UM-X")
    assert _unmatched(ws["buyer"])["po_ids"] == [mine]
    assert _unmatched(other["buyer"])["po_ids"] == []                       # and mine are not theirs


def test_it_needs_orderbook_read(ws, monkeypatch):
    from app.auth import rbac_engine

    matrix = {**rbac_engine.MATRIX, "viewer": {**rbac_engine.MATRIX["viewer"], "orderbook": set()}}
    monkeypatch.setattr(rbac_engine, "MATRIX", matrix)
    assert ws["viewer"].get("/orders/unmatched").status_code == 403
