"""The order pop-up's tabs, part 1 (0064): ADMIN (cancel stamp), Delivery log, Stock, Tracking, Cutlists, Product image, supplier card."""
import uuid

import pytest

from .conftest import truncate_fixture
from .helpers import login
from .helpers_po import _code, _order, _sql, make_ws

_cleanup = truncate_fixture("order_delivery", "po_document")

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def ws():
    return make_ws()


def _get(c, oid):
    r = c.get(f"/orders/{oid}")
    assert r.status_code == 200, r.text
    return r.json()


# ── ADMIN ───────────────────────────────────────────────────────────────────────────────────────

def test_cancelling_stamps_when_who_and_why(ws):
    c = ws["buyer"]
    a = _order(ws)
    assert c.delete(f"/orders/{a}", params={"reason": " Wrong supplier "}).status_code == 204
    o = _get(c, a)
    assert o["status"] == "Cancelled" and o["cancelled_at"] and o["cancelled_by_name"] and o["cancel_reason"] == "Wrong supplier"
    b = _order(ws)
    assert c.patch(f"/orders/{b}", json={"status": "Cancelled", "cancel_reason": "Duplicate"}).status_code == 200
    o = _get(c, b)
    assert o["cancelled_at"] and o["cancel_reason"] == "Duplicate"
    # a reason belongs to a cancellation only; reopening clears all three
    d = _order(ws)
    r = c.patch(f"/orders/{d}", json={"cancel_reason": "x"})
    assert r.status_code == 409 and _code(r) == "CANCEL_REASON_NOT_APPLICABLE"
    assert c.patch(f"/orders/{b}", json={"status": "Pending"}).status_code == 200
    o = _get(c, b)
    assert o["cancelled_at"] is None and o["cancelled_by_name"] is None and o["cancel_reason"] is None
    e = _order(ws)
    c.delete(f"/orders/{e}")
    o = _get(c, e)
    assert o["cancelled_at"] and o["cancel_reason"] is None


# ── Delivery log ────────────────────────────────────────────────────────────────────────────────

def test_delivery_log_sums_and_works_out_what_remains(ws):
    c = ws["buyer"]
    a = _order(ws, quantity=6)
    log = c.get(f"/orders/{a}/deliveries").json()
    assert log["deliveries"] == [] and log["sum_received"] == "0" and log["remaining"] == "6.000"
    r = c.post(f"/orders/{a}/deliveries", json={"qty": "4", "date_received": "2026-09-22", "signed_by": "JOEF"})
    assert r.status_code == 201
    r = c.post(f"/orders/{a}/deliveries", json={"qty": "2", "date_received": "2026-10-13", "notes": "rest"})
    log = r.json()
    assert [d["qty"] for d in log["deliveries"]] == ["4.000", "2.000"]
    assert log["sum_received"] == "6.000" and log["remaining"] == "0.000"
    first = log["deliveries"][0]["delivery_id"]
    assert c.patch(f"/orders/{a}/deliveries/{first}", json={"qty": "3"}).json()["remaining"] == "1.000"
    assert c.patch(f"/orders/{a}/deliveries/{first}", json={"qty": None}).status_code == 422
    assert c.post(f"/orders/{a}/deliveries", json={"qty": "0", "date_received": "2026-10-13"}).status_code == 422
    assert c.delete(f"/orders/{a}/deliveries/{first}").json()["sum_received"] == "2.000"
    assert c.delete(f"/orders/{a}/deliveries/{first}").status_code == 404


def test_delivery_docket_and_frozen_orders(ws):
    c = ws["buyer"]
    a = _order(ws, quantity=2)
    d = c.post(f"/orders/{a}/deliveries", json={"qty": "1", "date_received": "2026-10-13"}).json()["deliveries"][0]["delivery_id"]
    base = f"/orders/{a}/deliveries/{d}/docket"
    assert c.get(base).status_code == 404
    r = c.post(base, files={"file": ("docket.pdf", PDF)})
    assert r.status_code == 201 and r.json()["deliveries"][0]["docket_mime"] == "application/pdf"
    assert c.get(base).content == PDF
    assert c.post(base, files={"file": ("x.skp", b"\xff\xfe\xff\x0e" + b"0" * 20)}).status_code == 415
    assert c.delete(base).json()["deliveries"][0]["has_docket"] is False
    # Delivered / Cancelled orders are read-only for the log
    c.patch(f"/orders/{a}", json={"status": "Delivered"})
    r = c.post(f"/orders/{a}/deliveries", json={"qty": "1", "date_received": "2026-10-14"})
    assert r.status_code == 409 and _code(r) == "ORDER_LOCKED"
    assert c.get(f"/orders/{a}/deliveries").status_code == 200


def test_received_by_is_a_patchable_order_field(ws):
    c = ws["buyer"]
    a = _order(ws)
    assert c.patch(f"/orders/{a}", json={"received_by": "JOEF", "arrived_date": "2026-10-13"}).status_code == 200
    o = _get(c, a)
    assert o["received_by"] == "JOEF" and o["arrived_date"] == "2026-10-13"


# ── Stock ───────────────────────────────────────────────────────────────────────────────────────

def test_stock_lists_stock_tracked_orders_of_the_same_product_code(ws):
    c = ws["buyer"]
    a = _order(ws, product_code="TG_110631", stock_tracked=True, quantity=6)
    _order(ws, product_code="tg_110631", stock_tracked=True, quantity=2)
    _order(ws, product_code="TG_110631", stock_tracked=False)
    _order(ws, product_code="OTHER", stock_tracked=True)
    gone = _order(ws, product_code="TG_110631", stock_tracked=True)
    c.delete(f"/orders/{gone}")
    rows = c.get(f"/orders/{a}/stock").json()["stock"]
    assert sorted(r["quantity"] for r in rows) == ["2.000", "6.000"]
    assert {r["category"] for r in rows} == {"Other"}
    no_code = _order(ws)
    assert c.get(f"/orders/{no_code}/stock").json() == {"stock": []}


# ── Tracking and Cutlists ───────────────────────────────────────────────────────────────────────

def _item_with_material(wid, code):
    suffix = uuid.uuid4().hex[:6]
    pid = _sql("INSERT INTO projects(project_code, name, workspace_id) VALUES ('OT', :n, :w) RETURNING project_id",
               n=f"Tabs {suffix}", w=wid)
    cl = _sql("INSERT INTO cutlist(project_id, cutlist_no) VALUES (:p, nextval('joinery_number_seq')) RETURNING cutlist_id", p=pid)
    iid = _sql("INSERT INTO items(num, project_id, description, status, cutlist_id)"
               " VALUES (nextval('joinery_number_seq'), :p, 'Vanity Top 1570', 'LIVE', :c) RETURNING item_id", p=pid, c=cl)
    bid = _sql("INSERT INTO board_materials(code, description, sku, workspace_id) VALUES (:c, 'Board', :c, :w)"
               " RETURNING material_id", c=code, w=wid)
    mid = _sql("INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    _sql("INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id) VALUES (:m, 1, 100, 100, :b)", m=mid, b=bid)
    _sql("INSERT INTO item_stages(item_id, stage_key, done_date) VALUES (:i, 'MADE', '2026-09-09')", i=iid)
    return {"pid": pid, "item": iid, "cutlist": cl}


def test_tracking_shows_the_linked_item_and_the_orders_own_number(ws):
    c = ws["buyer"]
    made = _item_with_material(ws["wid"], f"TRK-{uuid.uuid4().hex[:6]}")
    a = _order(ws, item_id=made["item"], quantity=1)
    t = c.get(f"/orders/{a}/tracking").json()
    assert t["item"]["item_id"] == made["item"] and t["item"]["date_made"] == "2026-09-09"
    assert t["item"]["description"] == "Vanity Top 1570" and t["order_number"] == _get(c, a)["po_number"]
    assert c.get(f"/orders/{_order(ws)}/tracking").json()["item"] is None
    _sql("UPDATE items SET deleted = true WHERE item_id = :i", i=made["item"])
    assert c.get(f"/orders/{a}/tracking").json()["item"] is None  # a deleted item answers like a missing one


def test_cutlists_list_where_the_product_was_used(ws):
    c = ws["buyer"]
    code = f"CUT-{uuid.uuid4().hex[:6]}"
    made = _item_with_material(ws["wid"], code)
    a = _order(ws, product_code=code.lower())
    out = c.get(f"/orders/{a}/cutlists").json()
    assert out["product_found"] is True and len(out["cutlists"]) == 1
    row = out["cutlists"][0]
    assert row["item_description"] == "Vanity Top 1570" and row["project_name"].startswith("Tabs ")
    assert c.get(f"/orders/{_order(ws, product_code='NOPE-1')}/cutlists").json() == {"product_found": False, "cutlists": []}
    _sql("UPDATE cutlist SET deleted = true WHERE cutlist_id = :c", c=made["cutlist"])
    assert c.get(f"/orders/{a}/cutlists").json()["cutlists"] == []


# ── Product image and the supplier card ─────────────────────────────────────────────────────────

def test_product_image(ws):
    c = ws["buyer"]
    a = _order(ws)
    assert c.get(f"/orders/{a}/image").status_code == 404 and _get(c, a)["has_image"] is False
    assert c.put(f"/orders/{a}/image", files={"file": ("p.pdf", PDF)}).status_code == 415  # pictures only
    assert c.put(f"/orders/{a}/image", files={"file": ("p.png", PNG)}).status_code == 204
    assert _get(c, a)["has_image"] is True
    got = c.get(f"/orders/{a}/image")
    assert got.content == PNG and got.headers["content-type"] == "image/png"
    assert c.delete(f"/orders/{a}/image").status_code == 204 and _get(c, a)["has_image"] is False
    c.put(f"/orders/{a}/image", files={"file": ("p.png", PNG)})
    c.patch(f"/orders/{a}", json={"status": "Cancelled"})
    r = c.put(f"/orders/{a}/image", files={"file": ("q.png", PNG + b"1")})
    assert r.status_code == 409 and _code(r) == "ORDER_LOCKED"
    assert ws["viewer"].put(f"/orders/{a}/image", files={"file": ("p.png", PNG)}).status_code == 403


def test_supplier_card_fields_and_logo(ws):
    c = ws["buyer"]
    v = ws["v1"]
    r = c.patch(f"/suppliers/{v}", json={"website": "https://tg.example", "notes": "Supplier of solid surface", "metadata": "SOLID SURFACE"})
    assert r.status_code == 200
    s = r.json()
    assert (s["website"], s["notes"], s["metadata"], s["has_logo"]) == ("https://tg.example", "Supplier of solid surface", "SOLID SURFACE", False)
    assert c.put(f"/suppliers/{v}/logo", files={"file": ("l.pdf", PDF)}).status_code == 415
    assert c.put(f"/suppliers/{v}/logo", files={"file": ("l.png", PNG)}).status_code == 204
    assert c.get(f"/suppliers/{v}").json()["has_logo"] is True
    assert c.get(f"/suppliers/{v}/logo").content == PNG
    assert c.delete(f"/suppliers/{v}/logo").status_code == 204
    assert c.get(f"/suppliers/{v}/logo").status_code == 404


# ── another workspace ───────────────────────────────────────────────────────────────────────────

def test_other_workspace_is_404(ws):
    c = ws["buyer"]
    a = _order(ws, product_code="X-1", stock_tracked=True)
    d = c.post(f"/orders/{a}/deliveries", json={"qty": "1", "date_received": "2026-10-13"}).json()["deliveries"][0]["delivery_id"]
    c.post(f"/orders/{a}/deliveries/{d}/docket", files={"file": ("d.pdf", PDF)})
    c.put(f"/orders/{a}/image", files={"file": ("p.png", PNG)})
    other, _, _ = login("admin", prefix="tabs-other")
    ghost = 10**9
    for method, tail, kw in [
        ("get", "/deliveries", {}), ("post", "/deliveries", {"json": {"qty": "1", "date_received": "2026-10-13"}}),
        ("patch", f"/deliveries/{d}", {"json": {"qty": "2"}}), ("delete", f"/deliveries/{d}", {}),
        ("get", f"/deliveries/{d}/docket", {}), ("delete", f"/deliveries/{d}/docket", {}),
        ("post", f"/deliveries/{d}/docket", {"files": {"file": ("d.pdf", PDF)}}),
        ("get", "/stock", {}), ("get", "/tracking", {}), ("get", "/cutlists", {}),
        ("get", "/image", {}), ("delete", "/image", {}), ("put", "/image", {"files": {"file": ("p.png", PNG)}}),
    ]:
        real = getattr(other, method)(f"/orders/{a}{tail}", **kw)
        gone = getattr(other, method)(f"/orders/{ghost}{tail.replace(str(d), str(ghost))}", **kw)
        assert real.status_code == gone.status_code == 404, (method, tail, real.status_code, gone.status_code)
    assert other.put(f"/suppliers/{ws['v1']}/logo", files={"file": ("l.png", PNG)}).status_code == 404
    assert other.get(f"/suppliers/{ws['v1']}/logo").status_code == 404
    assert c.get(f"/orders/{a}/deliveries").json()["sum_received"] == "1.000"  # nothing changed
