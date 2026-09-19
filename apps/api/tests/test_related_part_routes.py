"""Related parts (Plan V1 Q416-Q424, Q447-Q453, migration 0028).

What these pin down:

  Q423  the Drafter or PM may create; an editor may not
  Q416  a related part shares its PARENT's Group ID
  Q449  one level only — a related part cannot be a parent
  Q450  it carries its own status, independent of the parent's
  Q419  it gets NO item_stages rows, ever
  Q417  it gets no cutlist
  Q452  reparenting moves the Group ID AND re-points linked orders (Q431)
  Q448  the type list is a lookup, and an unknown type is refused
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


def _login(slug, email, pw):
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": pw})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def ctx():
    suffix = uuid.uuid4().hex[:8]
    slug = f"rp-{suffix}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1),('HOLD',2) ON CONFLICT DO NOTHING"))
        wid = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES(:s,'RP WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        users = {}
        for role in ("drafter", "editor"):
            email = f"{role}-{suffix}@x.test"
            s.execute(
                text("INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)"
                     " VALUES (:w,:e,:r,:p,:r2)"),
                {"w": wid, "e": email, "r": role.title(), "p": hash_password("pw"), "r2": role},
            )
            users[role] = email
        pid = s.execute(
            text("INSERT INTO projects(project_code,name,workspace_id)"
                 " VALUES(:c,'RP Project',:w) RETURNING project_id"),
            {"c": f"RP-{suffix}", "w": wid},
        ).scalar()
        parents = []
        for label in ("unit A", "unit B"):
            parents.append(s.execute(
                text("""INSERT INTO items(num, project_id, description, status)
                        VALUES (nextval('joinery_number_seq'), :p, :d, 'CLEAR')
                        RETURNING item_id"""),
                {"p": pid, "d": label},
            ).scalar())
        vendor = s.execute(
            text("INSERT INTO vendors(name,category,workspace_id)"
                 " VALUES('Metalworks','Metal',:w) RETURNING vendor_id"),
            {"w": wid},
        ).scalar()
        s.commit()
    finally:
        s.close()
    return {
        "slug": slug, "wid": wid, "pid": pid,
        "parent_a": parents[0], "parent_b": parents[1], "vendor": vendor,
        "drafter": _login(slug, users["drafter"], "pw"),
        "editor": _login(slug, users["editor"], "pw"),
    }


def _num(item_id: int) -> int:
    s = SessionLocal()
    try:
        return s.execute(text("SELECT num FROM items WHERE item_id = :i"),
                         {"i": item_id}).scalar()
    finally:
        s.close()


def _create(ctx, parent=None, type_key="metal", **kw):
    body = {"related_part_type_key": type_key, "description": "brass rail", **kw}
    return ctx["drafter"].post(
        f"/items/{parent or ctx['parent_a']}/related-parts", json=body
    )


def test_drafter_may_create_but_editor_may_not(ctx):
    """Q423 — Drafter or PM only."""
    assert _create(ctx).status_code == 201
    denied = ctx["editor"].post(
        f"/items/{ctx['parent_a']}/related-parts",
        json={"related_part_type_key": "metal", "description": "x"},
    )
    assert denied.status_code == 403


def test_it_shares_the_parents_group_id(ctx):
    """Q416/Q453."""
    part = _create(ctx).json()
    assert part["group_id"] == str(_num(ctx["parent_a"]))
    assert part["parent_item_id"] == ctx["parent_a"]
    assert part["item_number"] != _num(ctx["parent_a"])   # its own Item ID


def test_a_related_part_cannot_be_a_parent(ctx):
    """Q449 — one level only."""
    part = _create(ctx).json()
    r = ctx["drafter"].post(
        f"/items/{part['item_id']}/related-parts",
        json={"related_part_type_key": "metal", "description": "nested"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "PARENT_IS_RELATED_PART"


def test_it_carries_its_own_status(ctx):
    """Q450 — a stuck supplier order is flagged without touching the parent."""
    part = _create(ctx).json()
    assert part["status"] == "CLEAR"

    r = ctx["drafter"].patch(f"/related-parts/{part['item_id']}", json={"status": "HOLD"})
    assert r.status_code == 200
    assert r.json()["status"] == "HOLD"

    s = SessionLocal()
    try:
        parent_status = s.execute(
            text("SELECT status FROM items WHERE item_id = :i"), {"i": ctx["parent_a"]}
        ).scalar()
    finally:
        s.close()
    assert parent_status == "CLEAR"      # untouched


def test_it_gets_no_stages_and_no_cutlist(ctx):
    """Q419 + Q417."""
    part = _create(ctx).json()
    s = SessionLocal()
    try:
        stages = s.execute(
            text("SELECT COUNT(*) FROM item_stages WHERE item_id = :i"),
            {"i": part["item_id"]},
        ).scalar()
        cutlist = s.execute(
            text("SELECT cutlist_id FROM items WHERE item_id = :i"),
            {"i": part["item_id"]},
        ).scalar()
    finally:
        s.close()
    assert stages == 0
    assert cutlist is None


def test_unknown_type_is_refused(ctx):
    """Q448 — the lookup is the authority."""
    r = _create(ctx, type_key="unobtainium")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_TYPE"

    types = ctx["drafter"].get("/related-part-types").json()
    assert {t["type_key"] for t in types} == {"metal", "benchtop", "cushion"}


def test_reparent_moves_group_id_and_order_reference(ctx):
    """Q452 -> Q431: the Group ID and every linked order follow the new parent."""
    # give each parent its own cutlist so the reference actually changes
    s = SessionLocal()
    try:
        nos = {}
        for key, iid in (("a", ctx["parent_a"]), ("b", ctx["parent_b"])):
            cid = s.execute(
                text("INSERT INTO cutlist(project_id,cutlist_no)"
                     " VALUES (:p, nextval('joinery_number_seq')) RETURNING cutlist_id"),
                {"p": ctx["pid"]},
            ).scalar()
            s.execute(text("UPDATE items SET cutlist_id = :c WHERE item_id = :i"),
                      {"c": cid, "i": iid})
            nos[key] = s.execute(
                text("SELECT cutlist_no FROM cutlist WHERE cutlist_id = :c"), {"c": cid}
            ).scalar()
        s.commit()
    finally:
        s.close()

    part = _create(ctx).json()
    po = ctx["drafter"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "rail", "category": "Metal",
        "item_id": part["item_id"],
    })
    assert po.status_code == 201, po.text
    assert po.json()["cutlist_no"] == str(nos["a"])

    moved = ctx["drafter"].post(
        f"/related-parts/{part['item_id']}/reparent",
        json={"new_parent_item_id": ctx["parent_b"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_item_id"] == ctx["parent_b"]
    assert moved.json()["group_id"] == str(_num(ctx["parent_b"]))

    s = SessionLocal()
    try:
        ref = s.execute(
            text("SELECT cutlist_no FROM purchase_orders WHERE po_id = :o"),
            {"o": po.json()["po_id"]},
        ).scalar()
    finally:
        s.close()
    assert ref == str(nos["b"])          # Q431: followed the new parent


def test_reparent_refuses_a_related_part_and_the_same_parent(ctx):
    part = _create(ctx).json()
    other = _create(ctx, parent=ctx["parent_b"]).json()

    same = ctx["drafter"].post(f"/related-parts/{part['item_id']}/reparent",
                               json={"new_parent_item_id": ctx["parent_a"]})
    assert same.status_code == 409
    assert same.json()["detail"]["code"] == "SAME_PARENT"

    nested = ctx["drafter"].post(f"/related-parts/{part['item_id']}/reparent",
                                 json={"new_parent_item_id": other["item_id"]})
    assert nested.status_code == 409
    assert nested.json()["detail"]["code"] == "PARENT_IS_RELATED_PART"


def test_list_under_a_parent(ctx):
    _create(ctx, type_key="metal")
    _create(ctx, type_key="benchtop")
    _create(ctx, parent=ctx["parent_b"], type_key="cushion")

    a = ctx["drafter"].get(f"/items/{ctx['parent_a']}/related-parts").json()
    b = ctx["drafter"].get(f"/items/{ctx['parent_b']}/related-parts").json()
    assert len(a["related_parts"]) == 2
    assert len(b["related_parts"]) == 1
    assert a["related_parts"][0]["related_part_type_label"] in {"Metal", "Benchtop"}


def test_delete_keeps_an_issued_order(ctx):
    """0029 made purchase_orders.item_id ON DELETE SET NULL: an order already
    sent to a supplier outlives the row it was raised for."""
    part = _create(ctx).json()
    po_id = ctx["drafter"].post("/orders", json={
        "vendor_id": ctx["vendor"], "description": "rail", "category": "Metal",
        "item_id": part["item_id"],
    }).json()["po_id"]

    assert ctx["drafter"].delete(f"/related-parts/{part['item_id']}").status_code == 204
    assert ctx["drafter"].get(f"/related-parts/{part['item_id']}").status_code == 404

    s = SessionLocal()
    try:
        row = s.execute(
            text("SELECT item_id, status FROM purchase_orders WHERE po_id = :o"),
            {"o": po_id},
        ).mappings().first()
    finally:
        s.close()
    assert row is not None
    assert row["item_id"] is None
