"""The supplier link on catalog rows: `PATCH /catalog/{slug}/{mid}` with
`default_supplier_id`, and the id + name coming back on reads.

`0029` added `default_supplier_id` (a real FK to `vendors`) beside the free-text
`default_supplier` on all six catalog tables, and Generate Orders reads only the
FK. The only way to set it used to be `POST /suppliers/{id}/materials`; this is
the catalog's own, gated `catalog:write` like every other edit on the grid.
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
        extra = (
            "batch_allocations", "procurement_batches", "equipment_hire",
            "appliances", "benchtop_materials", "custom_made",
            "hardware_materials", "board_materials",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _login(role: str = "drafter", wid: int | None = None):
    """Fresh workspace (or an existing one) + user, logged in -> (client, wid, uid)."""
    suffix = uuid.uuid4().hex[:8]
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        if wid is None:
            slug = f"sl-{suffix}"
            wid = db.execute(
                text("INSERT INTO workspace(slug, name) VALUES(:s, 'SL') RETURNING id"),
                {"s": slug},
            ).scalar()
        else:
            slug = db.execute(
                text("SELECT slug FROM workspace WHERE id = :w"), {"w": wid},
            ).scalar()
        uid = db.execute(
            text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
            """),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
    return c, wid, uid


def _vendor(wid: int, name: str = "Laminex Australia") -> int:
    db = SessionLocal()
    try:
        vid = db.execute(
            text("INSERT INTO vendors(workspace_id, name, category)"
                 " VALUES (:w, :n, 'Board') RETURNING vendor_id"),
            {"w": wid, "n": name},
        ).scalar()
        db.commit()
        return vid
    finally:
        db.close()


def _project(wid: int, uid: int) -> int:
    db = SessionLocal()
    try:
        pid = db.execute(
            text("INSERT INTO projects(project_code, name, pm_id, workspace_id)"
                 " VALUES ('SL-001', 'P', :u, :w) RETURNING project_id"),
            {"u": uid, "w": wid},
        ).scalar()
        db.commit()
        return pid
    finally:
        db.close()


# slug -> (create body factory, id column, table)
TABLES = {
    "board-materials": ({"code": "B1", "sku": "s-b", "description": "Board"}, "material_id", "board_materials"),
    "hardware-materials": ({"sku": "s-h", "description": "Hinge"}, "material_id", "hardware_materials"),
    "custom-made": ({"internal_ref": "C1", "sku": "s-c", "description": "Custom"}, "material_id", "custom_made"),
    "benchtop-materials": ({"slab_id": "S1", "sku": "s-t", "description": "Slab"}, "material_id", "benchtop_materials"),
    "appliances": ({"model_number": "M1", "sku": "s-a", "description": "Oven"}, "material_id", "appliances"),
    "equipment-hire": ({"contract_ref": "H1", "sku": "s-e", "description": "Lift"}, "hire_id", "equipment_hire"),
}


def _row(c, slug: str, *, project_id: int | None = None, **extra) -> int:
    body, id_col, _ = TABLES[slug]
    body = {**body, **extra}
    if slug == "equipment-hire":
        body["project_id"] = project_id
    r = c.post(f"/catalog/{slug}", json=body)
    assert r.status_code == 201, r.text
    return r.json()[id_col]


def _db_link(table: str, id_col: str, mid: int):
    db = SessionLocal()
    try:
        return db.execute(
            text(f"SELECT default_supplier_id FROM {table} WHERE {id_col} = :m"), {"m": mid},
        ).scalar()
    finally:
        db.close()


def _audit_count(wid: int, event_like: str) -> int:
    db = SessionLocal()
    try:
        return db.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE workspace_id = :w AND event LIKE :e"),
            {"w": wid, "e": event_like},
        ).scalar()
    finally:
        db.close()


# ── Reads ─────────────────────────────────────────────────────────────────────

def test_an_unlinked_row_reads_null_id_and_name():
    c, _, _ = _login()
    mid = _row(c, "board-materials")
    row = c.get(f"/catalog/board-materials/{mid}").json()
    assert row["default_supplier_id"] is None
    assert row["default_supplier_name"] is None
    listed = c.get("/catalog/board-materials").json()["rows"][0]
    assert listed["default_supplier_id"] is None and listed["default_supplier_name"] is None


# ── Set / clear, on every table ───────────────────────────────────────────────

@pytest.mark.parametrize("slug", list(TABLES))
def test_patch_links_and_clears_a_supplier_on_every_catalog_table(slug):
    c, wid, uid = _login()
    pid = _project(wid, uid) if slug == "equipment-hire" else None
    _, id_col, table = TABLES[slug]
    mid = _row(c, slug, project_id=pid)
    vid = _vendor(wid)

    r = c.patch(f"/catalog/{slug}/{mid}", json={"default_supplier_id": vid})
    assert r.status_code == 200, r.text
    assert r.json()["default_supplier_id"] == vid
    assert r.json()["default_supplier_name"] == "Laminex Australia"
    assert _db_link(table, id_col, mid) == vid
    # the list reads it too
    listed = {row[id_col]: row for row in c.get(f"/catalog/{slug}").json()["rows"]}
    assert listed[mid]["default_supplier_name"] == "Laminex Australia"

    # an explicit null clears it (everywhere else on this route a null is ignored)
    r = c.patch(f"/catalog/{slug}/{mid}", json={"default_supplier_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["default_supplier_id"] is None
    assert r.json()["default_supplier_name"] is None
    assert _db_link(table, id_col, mid) is None


def test_the_link_can_be_moved_to_another_supplier():
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    a, b = _vendor(wid, "A Co"), _vendor(wid, "B Co")
    c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": a})
    r = c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": b})
    assert r.json()["default_supplier_name"] == "B Co"


def test_omitting_the_link_leaves_it_alone():
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    vid = _vendor(wid)
    c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid})
    r = c.patch(f"/catalog/board-materials/{mid}", json={"description": "Renamed"})
    assert r.status_code == 200
    assert r.json()["description"] == "Renamed"
    assert r.json()["default_supplier_id"] == vid


def test_linking_leaves_the_free_text_supplier_untouched():
    """Q435 — the text column stays exactly as it was; the two may disagree."""
    c, wid, _ = _login()
    mid = _row(c, "board-materials", default_supplier="Some Old Name")
    vid = _vendor(wid)
    r = c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid})
    assert r.json()["default_supplier"] == "Some Old Name"
    assert r.json()["default_supplier_name"] == "Laminex Australia"


def test_a_row_can_be_created_with_a_supplier_link():
    c, wid, _ = _login()
    vid = _vendor(wid)
    r = c.post("/catalog/board-materials", json={
        "code": "B9", "sku": "s-9", "description": "X", "default_supplier_id": vid,
    })
    assert r.status_code == 201, r.text
    assert r.json()["default_supplier_id"] == vid
    assert r.json()["default_supplier_name"] == "Laminex Australia"
    assert _db_link("board_materials", "material_id", r.json()["material_id"]) == vid


@pytest.mark.parametrize("slug", [s for s in TABLES if s != "equipment-hire"])
def test_every_simple_table_takes_a_link_at_create(slug):
    c, wid, _ = _login()
    vid = _vendor(wid)
    mid = _row(c, slug, default_supplier_id=vid)
    _, id_col, table = TABLES[slug]
    assert _db_link(table, id_col, mid) == vid


def test_a_row_created_without_a_link_is_unlinked():
    c, wid, _ = _login()
    _vendor(wid)
    r = c.post("/catalog/board-materials", json={"code": "B9", "sku": "s-9", "description": "X"})
    assert r.status_code == 201, r.text
    assert r.json()["default_supplier_id"] is None


def test_create_refuses_an_unknown_or_foreign_supplier_and_creates_nothing():
    c, wid, _ = _login()
    _, other_wid, _ = _login()
    foreign = _vendor(other_wid, "Plyco")
    for sid in (999999, foreign):
        r = c.post("/catalog/board-materials", json={
            "code": "B9", "sku": "s-9", "description": "X", "default_supplier_id": sid,
        })
        assert r.status_code == 422, r.text
        assert r.json()["detail"]["code"] == "UNKNOWN_SUPPLIER"
        assert "Plyco" not in r.text
    assert c.get("/catalog/board-materials").json()["rows"] == []


# ── Bulk import links by name ─────────────────────────────────────────────────

def _bulk(c, slug, rows):
    r = c.post(f"/catalog/{slug}/bulk", json={"rows": rows})
    assert r.status_code == 200, r.text
    return r.json()


def test_bulk_import_links_a_row_whose_supplier_name_matches_exactly_one_supplier():
    c, wid, _ = _login()
    vid = _vendor(wid, "Laminex Australia")
    out = _bulk(c, "board-materials", [
        {"code": "B1", "sku": "b-1", "description": "One", "default_supplier": "laminex AUSTRALIA"},
    ])
    assert out["created"] == 1 and out["linked"] == 1 and out["unlinked"] == []
    row = c.get("/catalog/board-materials").json()["rows"][0]
    assert row["default_supplier_id"] == vid
    assert row["default_supplier"] == "laminex AUSTRALIA"  # the free text is kept as typed


def test_bulk_import_reports_rows_whose_supplier_name_matches_nobody():
    c, wid, _ = _login()
    _vendor(wid, "Laminex Australia")
    out = _bulk(c, "board-materials", [
        {"code": "B1", "sku": "b-1", "description": "One", "default_supplier": "Nobody Ltd"},
        {"code": "B2", "sku": "b-2", "description": "Two"},
    ])
    assert out["created"] == 2 and out["linked"] == 0
    # only the row that NAMED a supplier is reported; a row naming none has nothing to match
    assert [(u["row_index"], u["default_supplier"]) for u in out["unlinked"]] == [(0, "Nobody Ltd")]
    assert all(r["default_supplier_id"] is None for r in c.get("/catalog/board-materials").json()["rows"])


def test_bulk_import_never_links_a_name_two_suppliers_share():
    c, wid, _ = _login()
    _vendor(wid, "Plyco")
    _vendor(wid, "plyco")
    out = _bulk(c, "board-materials", [
        {"code": "B1", "sku": "b-1", "description": "One", "default_supplier": "Plyco"},
    ])
    assert out["created"] == 1 and out["linked"] == 0
    assert out["unlinked"][0]["reason"] == "more than one supplier has this name"
    assert c.get("/catalog/board-materials").json()["rows"][0]["default_supplier_id"] is None


def test_bulk_import_does_not_match_another_workspaces_supplier():
    c, wid, _ = _login()
    _, other_wid, _ = _login()
    _vendor(other_wid, "Plyco")
    out = _bulk(c, "board-materials", [
        {"code": "B1", "sku": "b-1", "description": "One", "default_supplier": "Plyco"},
    ])
    assert out["linked"] == 0 and len(out["unlinked"]) == 1


def test_bulk_import_ignores_a_supplier_id_in_a_row():
    c, wid, _ = _login()
    vid = _vendor(wid)
    out = _bulk(c, "board-materials", [
        {"code": "B1", "sku": "b-1", "description": "One", "default_supplier_id": vid},
    ])
    assert out["created"] == 1 and out["linked"] == 0
    assert c.get("/catalog/board-materials").json()["rows"][0]["default_supplier_id"] is None


def test_a_failed_bulk_import_links_and_reports_nothing():
    c, wid, _ = _login()
    _vendor(wid)
    out = _bulk(c, "board-materials", [
        {"code": "B1", "sku": "b-1", "description": "One", "default_supplier": "Laminex Australia"},
        {"code": "", "sku": "b-2", "description": "Bad"},
    ])
    assert out["created"] == 0 and out["linked"] == 0 and out["unlinked"] == []
    assert len(out["errors"]) == 1


# ── Clearing the free-text fields ─────────────────────────────────────────────

def test_an_explicit_null_clears_the_free_text_supplier_and_lead_time():
    c, wid, _ = _login()
    mid = _row(c, "board-materials", default_supplier="Old Name", default_lead_time_days=7)
    r = c.patch(f"/catalog/board-materials/{mid}", json={
        "default_supplier": None, "default_lead_time_days": None,
    })
    assert r.status_code == 200, r.text
    assert r.json()["default_supplier"] is None
    assert r.json()["default_lead_time_days"] is None


def test_omitting_the_free_text_fields_leaves_them_alone():
    c, wid, _ = _login()
    mid = _row(c, "board-materials", default_supplier="Old Name", default_lead_time_days=7)
    r = c.patch(f"/catalog/board-materials/{mid}", json={"description": "Renamed"})
    assert r.json()["default_supplier"] == "Old Name"
    assert r.json()["default_lead_time_days"] == 7


def test_a_null_does_not_clear_a_not_null_field():
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    r = c.patch(f"/catalog/board-materials/{mid}", json={"description": None})
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Board"


# ── Refusals ──────────────────────────────────────────────────────────────────

def test_an_unknown_supplier_is_refused_and_nothing_is_written():
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    before = _audit_count(wid, "catalog.board.update")
    r = c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": 999999})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_SUPPLIER"
    assert _db_link("board_materials", "material_id", mid) is None
    assert _audit_count(wid, "catalog.board.update") == before


def test_another_workspaces_supplier_is_refused_and_its_name_never_appears():
    c, wid, _ = _login()
    _, other_wid, _ = _login()
    foreign = _vendor(other_wid, "Secret Supplier Pty")
    mid = _row(c, "board-materials")
    r = c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": foreign})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_SUPPLIER"
    assert "Secret Supplier" not in r.text
    assert _db_link("board_materials", "material_id", mid) is None


def test_a_cross_workspace_link_written_some_other_way_never_leaks_a_name():
    """The column is a plain FK, so a stale cross-workspace id is possible in
    the database; the name read is scoped to the row's own workspace."""
    c, wid, _ = _login()
    _, other_wid, _ = _login()
    foreign = _vendor(other_wid, "Secret Supplier Pty")
    mid = _row(c, "board-materials")
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE board_materials SET default_supplier_id = :v WHERE material_id = :m"),
            {"v": foreign, "m": mid},
        )
        db.commit()
    finally:
        db.close()
    row = c.get(f"/catalog/board-materials/{mid}").json()
    assert row["default_supplier_name"] is None
    assert "Secret Supplier" not in c.get("/catalog/board-materials").text


def test_a_non_integer_supplier_id_is_a_422():
    c, _, _ = _login()
    mid = _row(c, "board-materials")
    r = c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": "abc"})
    assert r.status_code == 422


def test_another_workspaces_row_is_a_404():
    c, wid, _ = _login()
    other_c, other_wid, _ = _login()
    mid = _row(other_c, "board-materials")
    vid = _vendor(wid)
    r = c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid})
    assert r.status_code == 404
    assert _db_link("board_materials", "material_id", mid) is None


@pytest.mark.parametrize("role", ["purchase_officer", "viewer", "estimator"])
def test_a_role_without_catalog_write_cannot_link(role):
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    vid = _vendor(wid)
    ro, _, _ = _login(role=role, wid=wid)
    r = ro.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid})
    assert r.status_code == 403
    assert _db_link("board_materials", "material_id", mid) is None


def test_an_editor_can_link():
    """`catalog:write` is held by editor as well as drafter / manager / admin."""
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    vid = _vendor(wid)
    ed, _, _ = _login(role="editor", wid=wid)
    assert ed.patch(
        f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid},
    ).status_code == 200


# ── Audit and the supplier side ───────────────────────────────────────────────

def test_link_and_clear_are_audited_with_the_id():
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    vid = _vendor(wid)
    c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid})
    c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": None})
    db = SessionLocal()
    try:
        payloads = [
            r[0] for r in db.execute(text(
                "SELECT payload FROM audit_log WHERE workspace_id = :w"
                " AND event = 'catalog.board.update' ORDER BY id"), {"w": wid})
        ]
    finally:
        db.close()
    assert payloads[-2]["default_supplier_id"] == vid
    assert "default_supplier_id" in payloads[-1] and payloads[-1]["default_supplier_id"] is None


def test_the_supplier_side_sees_a_catalog_link():
    c, wid, _ = _login()
    mid = _row(c, "board-materials")
    vid = _vendor(wid)
    c.patch(f"/catalog/board-materials/{mid}", json={"default_supplier_id": vid})
    assert c.get(f"/suppliers/{vid}").json()["linked_material_count"] == 1
    mats = c.get(f"/suppliers/{vid}/materials").json()["materials"]
    assert [(m["material_table"], m["material_id"], m["is_default_supplier"]) for m in mats] == [
        ("board_materials", mid, True)
    ]
