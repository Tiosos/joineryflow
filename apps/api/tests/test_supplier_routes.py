"""Suppliers (Plan V1 Q506, Q556, Q565).

`vendors` IS the supplier entity — there is no separate `supplier` table — and
since Q565 this is its only surface. These cover what the retired legacy
endpoints never did: workspace isolation, a workspace_id on insert (the
omission 0029 turned into a hard break), and the catalog repoint.
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
        s.execute(text(
            "TRUNCATE vendors, board_materials, hardware_materials, custom_made,"
            " benchtop_materials, appliances, equipment_hire, "
            + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"
        ))
        s.commit()
    finally:
        s.close()


def _mk_workspace(slug_prefix: str):
    """A workspace + an orderbook-capable user, returning a logged-in client."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"{slug_prefix}-{suffix}"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug,name) VALUES(:s,'Sup WS') RETURNING id"),
            {"s": slug},
        ).scalar()
        email = f"po-{suffix}@x.test"
        s.execute(
            text("INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)"
                 " VALUES (:w,:e,'Buyer',:p,'purchase_officer')"),
            {"w": wid, "e": email, "p": hash_password("pw")},
        )
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c, wid


@pytest.fixture
def ctx():
    client, wid = _mk_workspace("sup")
    s = SessionLocal()
    try:
        board = s.execute(
            text("INSERT INTO board_materials(workspace_id, code, description, supplier)"
                 " VALUES (:w,'BM-T1','Test board','Briggs Veneer') RETURNING material_id"),
            {"w": wid},
        ).scalar()
        hire = s.execute(
            text("INSERT INTO projects(project_code,name,workspace_id)"
                 " VALUES('SUPP','Supp Project',:w) RETURNING project_id"),
            {"w": wid},
        ).scalar()
        hire_id = s.execute(
            text("INSERT INTO equipment_hire(workspace_id, contract_ref, description, project_id)"
                 " VALUES (:w,'EH-T1','Scissor lift',:p) RETURNING hire_id"),
            {"w": wid, "p": hire},
        ).scalar()
        s.commit()
    finally:
        s.close()
    return {"client": client, "wid": wid, "board": board, "hire_id": hire_id}


def _create(ctx, name="Briggs Veneer", category="Board"):
    return ctx["client"].post("/suppliers", json={"name": name, "category": category})


def test_create_sets_workspace_id(ctx):
    """The omission that broke the legacy insert once 0029 made it NOT NULL."""
    r = _create(ctx)
    assert r.status_code == 201, r.text
    s = SessionLocal()
    try:
        wid = s.execute(
            text("SELECT workspace_id FROM vendors WHERE vendor_id = :v"),
            {"v": r.json()["vendor_id"]},
        ).scalar()
    finally:
        s.close()
    assert wid == ctx["wid"]


def test_a_joinery_category_is_accepted(ctx):
    """0031 replaced the frozen CHECK with the order_category lookup."""
    assert _create(ctx, category="Board").status_code == 201
    bad = _create(ctx, name="Other Co", category="Nonsense")
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "UNKNOWN_CATEGORY"


def test_suppliers_are_workspace_isolated(ctx):
    """What the legacy endpoints never did — `workspace` appeared zero times
    in procurement/queries.py."""
    mine = _create(ctx).json()

    other_client, other_wid = _mk_workspace("other")
    other = other_client.post("/suppliers", json={"name": "Foreign Co", "category": "Other"})
    assert other.status_code == 201

    names = {s["name"] for s in ctx["client"].get("/suppliers").json()["suppliers"]}
    assert names == {"Briggs Veneer"}
    assert other_client.get(f"/suppliers/{mine['vendor_id']}").status_code == 404


def test_linking_a_material_keeps_the_free_text(ctx):
    """Q506 repoints; Q435 keeps the name already there."""
    vendor_id = _create(ctx).json()["vendor_id"]
    r = ctx["client"].post(f"/suppliers/{vendor_id}/materials", json={
        "material_table": "board_materials", "material_id": ctx["board"],
    })
    assert r.status_code == 204, r.text

    s = SessionLocal()
    try:
        row = s.execute(
            text("SELECT supplier, supplier_id FROM board_materials WHERE material_id = :m"),
            {"m": ctx["board"]},
        ).mappings().first()
    finally:
        s.close()
    assert row["supplier_id"] == vendor_id
    assert row["supplier"] == "Briggs Veneer"        # additive, not replaced


def test_equipment_hire_links_on_its_own_pk(ctx):
    """`equipment_hire` keys on hire_id, not material_id."""
    vendor_id = _create(ctx).json()["vendor_id"]
    r = ctx["client"].post(f"/suppliers/{vendor_id}/materials", json={
        "material_table": "equipment_hire", "material_id": ctx["hire_id"],
        "field": "default_supplier_id",
    })
    assert r.status_code == 204, r.text

    s = SessionLocal()
    try:
        linked = s.execute(
            text("SELECT default_supplier_id FROM equipment_hire WHERE hire_id = :h"),
            {"h": ctx["hire_id"]},
        ).scalar()
    finally:
        s.close()
    assert linked == vendor_id


def test_linked_count_and_listing(ctx):
    vendor_id = _create(ctx).json()["vendor_id"]
    assert ctx["client"].get(f"/suppliers/{vendor_id}").json()["linked_material_count"] == 0

    for table, mid, field in (
        ("board_materials", ctx["board"], "supplier_id"),
        ("equipment_hire", ctx["hire_id"], "default_supplier_id"),
    ):
        ctx["client"].post(f"/suppliers/{vendor_id}/materials", json={
            "material_table": table, "material_id": mid, "field": field,
        })

    assert ctx["client"].get(f"/suppliers/{vendor_id}").json()["linked_material_count"] == 2
    mats = ctx["client"].get(f"/suppliers/{vendor_id}/materials").json()["materials"]
    assert {m["material_table"] for m in mats} == {"board_materials", "equipment_hire"}


def test_bad_table_and_field_are_refused(ctx):
    vendor_id = _create(ctx).json()["vendor_id"]
    bad_table = ctx["client"].post(f"/suppliers/{vendor_id}/materials", json={
        "material_table": "items", "material_id": 1,
    })
    assert bad_table.status_code == 422
    assert bad_table.json()["detail"]["code"] == "UNKNOWN_TABLE"

    bad_field = ctx["client"].post(f"/suppliers/{vendor_id}/materials", json={
        "material_table": "board_materials", "material_id": ctx["board"],
        "field": "name",
    })
    assert bad_field.status_code == 422
    assert bad_field.json()["detail"]["code"] == "UNKNOWN_FIELD"

    missing = ctx["client"].post(f"/suppliers/{vendor_id}/materials", json={
        "material_table": "board_materials", "material_id": 999999,
    })
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "MATERIAL_NOT_FOUND"


def test_patch_updates_and_validates(ctx):
    vendor_id = _create(ctx).json()["vendor_id"]
    r = ctx["client"].patch(f"/suppliers/{vendor_id}",
                            json={"status": "Under Review", "rating": 4.5})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Under Review"
    assert float(r.json()["rating"]) == 4.5

    bad = ctx["client"].patch(f"/suppliers/{vendor_id}", json={"category": "Nonsense"})
    assert bad.status_code == 422


def test_legacy_vendor_endpoints_are_gone(ctx):
    """Q565 — guard against the duplicate surface returning."""
    for method, path in (
        ("get", "/procurement/vendors"),
        ("post", "/procurement/vendors"),
        ("get", "/procurement/inventory"),          # Q544 dropped the table
        ("get", "/procurement/inventory/low-stock"),
    ):
        r = getattr(ctx["client"], method)(path, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 404, f"{method} {path} still mounted: {r.status_code}"
