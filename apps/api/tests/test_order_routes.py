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
