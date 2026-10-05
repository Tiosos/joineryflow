"""Tests for GET /projects/{pid}/hardware_catalog.

Uses the autouse-TRUNCATE pattern from test_items_routes.py.
Raw SQL inserts bypass the route layer (no catalog-write API exists in T13).

Schema notes carried forward from queries.py:
- project_hardware_catalog has no workspace_id; scoped via projects.pm_id chain.
- project_hardware_catalog has no qty column; endpoint returns 1.0 for all rows.
- equipment_hire PK is hire_id; custom_made uses vendor, not supplier.
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login, login_same_workspace, set_item
from .conftest import truncate_fixture

# Source tables beyond the base TRUNCATE_TABLES list that we insert into
_EXTRA_TABLES = (
    "status_options",
    "item_stages",
    "item_edit_log",
    "item_status_log",
    "item_hardware_lines",
    "items",
    "project_hardware_catalog_log",
    "project_hardware_catalog",
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
)


_cleanup = truncate_fixture(*_EXTRA_TABLES)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _login(role: str = "manager"):
    return login(role, prefix="hw")






def _insert_board(
    db,
    *,
    wid: int,
    code: str = "BRD-001",
    description: str = "Oak Board",
    sku: str = "SKU-BRD",
    unit_cost: float = 12.50,
) -> int:
    mid = db.execute(
        text(
            """
            INSERT INTO board_materials(code, description, workspace_id, sku, unit_cost)
            VALUES (:code, :desc, :wid, :sku, :cost)
            RETURNING material_id
            """
        ),
        {"code": code, "desc": description, "wid": wid, "sku": sku, "cost": unit_cost},
    ).scalar()
    db.commit()
    return mid


def _insert_hardware(
    db,
    *,
    wid: int,
    sku: str = "HW-001",
    description: str = "Hinge",
    unit_cost: float = 3.75,
) -> int:
    mid = db.execute(
        text(
            """
            INSERT INTO hardware_materials(sku, description, workspace_id, unit_cost)
            VALUES (:sku, :desc, :wid, :cost)
            RETURNING material_id
            """
        ),
        {"sku": sku, "desc": description, "wid": wid, "cost": unit_cost},
    ).scalar()
    db.commit()
    return mid


def _add_to_catalog(
    db,
    *,
    project_id: int,
    material_type: str,
    material_id: int,
    added_by: int,
) -> int:
    cid = db.execute(
        text(
            """
            INSERT INTO project_hardware_catalog(project_id, material_type, material_id, added_by)
            VALUES (:pid, :mtype, :mid, :by)
            RETURNING catalog_id
            """
        ),
        {
            "pid": project_id,
            "mtype": material_type,
            "mid": material_id,
            "by": added_by,
        },
    ).scalar()
    db.commit()
    return cid


# ── Test cases ─────────────────────────────────────────────────────────────────

def test_catalog_empty_for_new_project():
    """A project with no catalog rows returns project_id and an empty rows list."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid)
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["rows"] == []


def test_catalog_resolves_two_source_tables():
    """Catalog rows from BOARD and HARDWARE types surface with correct source_table strings."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid)
        board_mid = _insert_board(
            db, wid=wid, code="BRD-A", sku="SKU-A", description="Oak Board"
        )
        hw_mid = _insert_hardware(db, wid=wid, sku="HW-A", description="Hinge")
        _add_to_catalog(
            db, project_id=pid, material_type="BOARD",
            material_id=board_mid, added_by=uid,
        )
        _add_to_catalog(
            db, project_id=pid, material_type="HARDWARE",
            material_id=hw_mid, added_by=uid,
        )
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 2
    source_tables = {row["source_table"] for row in rows}
    assert "board_materials" in source_tables
    assert "hardware_materials" in source_tables


def test_catalog_404_for_other_workspace():
    """A user from workspace B cannot access workspace A's project catalog."""
    c_a, wid_a, uid_a = _login()
    c_b, _wid_b, _uid_b = _login()

    db = SessionLocal()
    try:
        pid_a = create_project(db, uid=uid_a, code="HJ-WA1")
    finally:
        db.close()

    r = c_b.get(f"/projects/{pid_a}/hardware_catalog")
    assert r.status_code == 404, r.text


def test_catalog_includes_qty_and_unit_cost():
    """Catalog row echoes unit_cost from the source table; qty is always 1.0."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid)
        board_mid = _insert_board(
            db, wid=wid, code="BRD-B", sku="SKU-B",
            description="Walnut Sheet", unit_cost=24.99,
        )
        _add_to_catalog(
            db, project_id=pid, material_type="BOARD",
            material_id=board_mid, added_by=uid,
        )
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert abs(row["unit_cost"] - 24.99) < 0.01
    assert row["qty"] == 1.0


def test_catalog_supplier_falls_back_to_default_supplier():
    """The six catalog tables' free-text `supplier` is mostly empty — `0017` put
    the real value in `default_supplier`, which is why the query coalesces.

    Reading `supplier` alone showed "no supplier" on every seeded row while a
    supplier was plainly recorded (custom_made via its `vendor` column).
    """
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid)
        hw_mid = db.execute(
            text(
                """INSERT INTO hardware_materials(workspace_id, sku, description,
                                                   supplier, default_supplier)
                   VALUES(:wid, 'HW-SUP', 'Damper', NULL, 'Hettich Australia')
                   RETURNING material_id"""
            ),
            {"wid": wid},
        ).scalar()
        cm_mid = db.execute(
            text(
                """INSERT INTO custom_made(workspace_id, internal_ref, description,
                                           vendor, default_supplier, cost)
                   VALUES(:wid, 'CM-SUP', 'Signbox', NULL, 'Metalform', 100)
                   RETURNING material_id"""
            ),
            {"wid": wid},
        ).scalar()
        _add_to_catalog(
            db, project_id=pid, material_type="HARDWARE",
            material_id=hw_mid, added_by=uid,
        )
        _add_to_catalog(
            db, project_id=pid, material_type="CUSTOM",
            material_id=cm_mid, added_by=uid,
        )
    finally:
        db.close()

    r = c.get(f"/projects/{pid}/hardware_catalog")
    assert r.status_code == 200, r.text
    suppliers = {row["source_table"]: row["supplier"] for row in r.json()["rows"]}
    assert suppliers["hardware_materials"] == "Hettich Australia"
    assert suppliers["custom_made"] == "Metalform"


def test_source_catalog_supplier_falls_back_to_default_supplier():
    """GET /source_catalog/{table} carries the same default_supplier fallback."""
    c, wid, _uid = _login()
    db = SessionLocal()
    try:
        db.execute(
            text(
                """INSERT INTO board_materials(workspace_id, code, sku, description,
                                               supplier, default_supplier)
                   VALUES(:wid, 'BRD-SUP', 'SKU-SUP', 'Ply', NULL, 'Big River Group')"""
            ),
            {"wid": wid},
        )
        db.execute(
            text(
                """INSERT INTO custom_made(workspace_id, internal_ref, description,
                                           vendor, default_supplier, cost)
                   VALUES(:wid, 'CM-SUP2', 'Signbox 2', NULL, 'Metalform', 100)"""
            ),
            {"wid": wid},
        )
        db.commit()
    finally:
        db.close()

    board_rows = c.get("/source_catalog/board_materials").json()["rows"]
    assert board_rows[0]["supplier"] == "Big River Group"

    custom_rows = c.get("/source_catalog/custom_made").json()["rows"]
    assert custom_rows[0]["supplier"] == "Metalform"


# ── T18 tests ──────────────────────────────────────────────────────────────────


def _seed_status(db) -> None:
    """Seed status_options reference rows (FK target for items.status)."""
    for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order) "
                "VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    db.commit()


def _create_item(db, *, project_id: int, uid: int, code: str = "ITEM-001") -> int:
    """Insert an item under a project and return item_id."""
    _seed_status(db)
    iid = db.execute(
        text(
            """
            INSERT INTO items(project_id, num, status)
            VALUES (:pid, 1, 'CLEAR')
            RETURNING item_id
            """
        ),
        {"pid": project_id},
    ).scalar()
    db.commit()
    return iid


def _add_hardware_line(db, *, item_id: int, catalog_id: int, qty: int = 1) -> int:
    """Raw insert an item_hardware_lines row and return line_id."""
    lid = db.execute(
        text(
            """
            INSERT INTO item_hardware_lines(item_id, catalog_id, qty)
            VALUES (:iid, :cid, :qty)
            RETURNING line_id
            """
        ),
        {"iid": item_id, "cid": catalog_id, "qty": qty},
    ).scalar()
    db.commit()
    return lid


def test_adding_a_material_already_in_the_catalog_is_a_409():
    """The catalog holds a material once per project. A second add is refused with a
    stable code (it used to hit the unique constraint and answer a raw 500), and writes
    neither a second row nor a second ADD log entry."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-DUP")
        board_mid = _insert_board(db, wid=wid, code="BRD-DUP", sku="SKU-DUP", description="Oak DUP")
    finally:
        db.close()
    body = {"source_table": "board_materials", "source_id": board_mid}

    first = c.post(f"/projects/{pid}/hardware_catalog", json=body)
    assert first.status_code == 201, first.text
    second = c.post(f"/projects/{pid}/hardware_catalog", json=body)
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == {
        "code": "ALREADY_IN_CATALOG", "catalog_id": first.json()["catalog_id"]}

    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT COUNT(*) FROM project_hardware_catalog WHERE project_id = :p"),
                          {"p": pid}).scalar()
        adds = db.execute(text("SELECT COUNT(*) FROM project_hardware_catalog_log"
                               " WHERE project_id = :p AND action = 'ADD'"), {"p": pid}).scalar()
    finally:
        db.close()
    assert (rows, adds) == (1, 1)


def test_add_catalog_writes_log_in_same_txn():
    """POST hardware_catalog inserts both catalog row and log row."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-A1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18A", sku="SKU-T18A", description="Oak T18A")
    finally:
        db.close()

    r = c.post(
        f"/projects/{pid}/hardware_catalog",
        json={"source_table": "board_materials", "source_id": board_mid},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["catalog_id"]

    db = SessionLocal()
    try:
        cat_count = db.execute(
            text("SELECT COUNT(*) FROM project_hardware_catalog WHERE catalog_id = :cid"),
            {"cid": cid},
        ).scalar()
        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM project_hardware_catalog_log "
                "WHERE project_id = :pid AND action = 'ADD'"
            ),
            {"pid": pid},
        ).scalar()
    finally:
        db.close()

    assert cat_count == 1
    assert log_count == 1


def test_add_catalog_invalid_source_404():
    """POST hardware_catalog with non-existent source_id returns 404."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-A2")
    finally:
        db.close()

    r = c.post(
        f"/projects/{pid}/hardware_catalog",
        json={"source_table": "board_materials", "source_id": 999999},
    )
    assert r.status_code == 404, r.text


def test_remove_catalog_409_when_referenced():
    """DELETE hardware_catalog returns 409 when a hardware_line references it."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-B1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18B", sku="SKU-T18B", description="Walnut T18B")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
        _add_hardware_line(db, item_id=iid, catalog_id=cid)
    finally:
        db.close()

    r = c.delete(f"/projects/{pid}/hardware_catalog/{cid}")
    assert r.status_code == 409, r.text


def test_remove_catalog_writes_remove_log_row():
    """DELETE hardware_catalog inserts a REMOVE log row."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-B2")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18C", sku="SKU-T18C", description="Birch T18C")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
    finally:
        db.close()

    r = c.delete(f"/projects/{pid}/hardware_catalog/{cid}")
    assert r.status_code == 204, r.text

    db = SessionLocal()
    try:
        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM project_hardware_catalog_log "
                "WHERE project_id = :pid AND action = 'REMOVE'"
            ),
            {"pid": pid},
        ).scalar()
    finally:
        db.close()

    assert log_count == 1


def test_create_hardware_line_validates_catalog_belongs_to_project():
    """POST hardware_line with catalog_id from a different project returns 404."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid_a = create_project(db, uid=uid, code="T18-C1A")
        pid_b = create_project(db, uid=uid, code="T18-C1B")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18D", sku="SKU-T18D", description="Maple T18D")
        # Add catalog row to project B
        cid_b = _add_to_catalog(db, project_id=pid_b, material_type="BOARD", material_id=board_mid, added_by=uid)
        # Create item in project A
        iid_a = _create_item(db, project_id=pid_a, uid=uid)
    finally:
        db.close()

    # Try to create hardware line for item in project A using catalog from project B
    r = c.post(
        f"/items/{iid_a}/hardware_lines",
        json={"catalog_id": cid_b, "qty": 1},
    )
    assert r.status_code == 404, r.text


def test_patch_hardware_line_qty_writes_edit_log():
    """PATCH qty writes one item_edit_log row with field='hardware_lines.qty'."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-D1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18E", sku="SKU-T18E", description="Pine T18E")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
        lid = _add_hardware_line(db, item_id=iid, catalog_id=cid, qty=1)
    finally:
        db.close()

    r = c.patch(f"/hardware_lines/{lid}", json={"qty": 5})
    assert r.status_code == 200, r.text
    assert r.json()["qty"] == 5

    db = SessionLocal()
    try:
        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM item_edit_log "
                "WHERE item_id = :iid AND field = 'hardware_lines.qty'"
            ),
            {"iid": iid},
        ).scalar()
    finally:
        db.close()

    assert log_count == 1


def test_editor_403_on_hardware_line_create():
    """A user with auth_role='editor' gets 403 when POSTing a hardware line."""
    c, wid, uid = _login(role="editor")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-E1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18F", sku="SKU-T18F", description="Cedar T18F")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
    finally:
        db.close()

    r = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": cid, "qty": 1})
    assert r.status_code == 403, r.text


def test_availability_endpoint_reflects_new_line():
    """After POSTing a hardware_line, GET /items/{id}/availability shows it as 'none'."""
    c, wid, uid = _login()
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="T18-F1")
        board_mid = _insert_board(db, wid=wid, code="BRD-T18G", sku="SKU-T18G", description="Ash T18G")
        cid = _add_to_catalog(db, project_id=pid, material_type="BOARD", material_id=board_mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
    finally:
        db.close()

    r = c.post(f"/items/{iid}/hardware_lines", json={"catalog_id": cid, "qty": 2})
    assert r.status_code == 201, r.text
    lid = r.json()["id"]

    r = c.get(f"/items/{iid}/availability")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_id"] == iid
    lines = body["lines"]
    assert len(lines) == 1
    assert lines[0]["line_id"] == lid
    assert lines[0]["status"] == "none"


# ── Lock checks on hardware line writes ────────────────────────────────────────






def _hw_fixture():
    """A drafter, their workspace, and an item with one hardware line."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code=f"HL-{uuid.uuid4().hex[:6]}")
        mid = _insert_hardware(db, wid=wid, sku=f"HW-{uuid.uuid4().hex[:6]}")
        cid = _add_to_catalog(db, project_id=pid, material_type="HARDWARE", material_id=mid, added_by=uid)
        iid = _create_item(db, project_id=pid, uid=uid)
        lid = _add_hardware_line(db, item_id=iid, catalog_id=cid, qty=2)
    finally:
        db.close()
    return c, wid, uid, iid, cid, lid


def _hw_routes(iid: int, cid: int, lid: int) -> dict:
    """The three hardware line writes: name -> (method, path, json, ok status)."""
    return {
        "create": ("post", f"/items/{iid}/hardware_lines", {"catalog_id": cid, "qty": 1}, 201),
        "patch": ("patch", f"/hardware_lines/{lid}", {"qty": 9}, 200),
        "delete": ("delete", f"/hardware_lines/{lid}", None, 204),
    }


_HW_ROUTE_NAMES = ["create", "patch", "delete"]


def _send(client, route: tuple):
    method, path, body, _ok = route
    return getattr(client, method)(path, **({"json": body} if body is not None else {}))


def _hw_state(iid: int, wid: int) -> tuple:
    """Everything a refused write must leave alone."""
    db = SessionLocal()
    try:
        return (
            db.execute(text("SELECT count(*), coalesce(sum(qty), 0) FROM item_hardware_lines"
                            " WHERE item_id = :i"), {"i": iid}).one(),
            db.execute(text("SELECT count(*) FROM item_edit_log WHERE item_id = :i"), {"i": iid}).scalar(),
            db.execute(text("SELECT count(*) FROM audit_log WHERE workspace_id = :w"
                            " AND event LIKE 'hardware_line.%'"), {"w": wid}).scalar(),
        )
    finally:
        db.close()


@pytest.mark.parametrize("name", _HW_ROUTE_NAMES)
@pytest.mark.parametrize("lock", ["hard", "approval"])
def test_locked_item_refuses_every_hardware_line_write(name, lock):
    c, wid, uid, iid, cid, lid = _hw_fixture()
    route = _hw_routes(iid, cid, lid)[name]
    if lock == "hard":
        set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
        expected = {"code": "HARD_LOCKED", "locked_by": uid}
    else:
        db = SessionLocal()
        try:
            db.execute(text("INSERT INTO status_options(status_key, sort_order)"
                            " VALUES ('APPROVED', 5) ON CONFLICT DO NOTHING"))
            db.commit()
        finally:
            db.close()
        set_item(iid, "status = 'APPROVED'")
        expected = {"code": "APPROVAL_LOCKED"}
    admin, _ = login_same_workspace(wid, "admin")

    before = _hw_state(iid, wid)
    for client in (c, admin):                       # a Hard / Approval Lock has no way round
        r = _send(client, route)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == expected
    assert _hw_state(iid, wid) == before, "a refused write must change and log nothing"

    set_item(iid, "hard_locked_at = NULL, hard_locked_by = NULL, status = 'CLEAR'")
    assert _send(c, route).status_code == route[3]   # the same request goes through once cleared


@pytest.mark.parametrize("name", _HW_ROUTE_NAMES)
def test_controlled_lock_refuses_a_non_owner_on_every_hardware_line_write(name):
    c, wid, uid, iid, cid, lid = _hw_fixture()
    routes = _hw_routes(iid, cid, lid)
    owner_client, owner_id = login_same_workspace(wid, "drafter", name="Olive Owner")
    set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)

    before = _hw_state(iid, wid)
    r = _send(c, routes[name])
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {
        "code": "ITEM_LOCKED", "owner_id": owner_id, "owner_name": "Olive Owner",
    }
    assert _hw_state(iid, wid) == before
    assert _send(owner_client, routes[name]).status_code == routes[name][3]   # the owner passes


@pytest.mark.parametrize("name", _HW_ROUTE_NAMES)
def test_a_manager_passes_a_controlled_lock_on_every_hardware_line_write(name):
    c, wid, uid, iid, cid, lid = _hw_fixture()
    routes = _hw_routes(iid, cid, lid)
    _other, owner_id = login_same_workspace(wid, "drafter")
    set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    manager, _ = login_same_workspace(wid, "manager")
    assert _send(manager, routes[name]).status_code == routes[name][3]


def test_an_unlocked_item_and_a_sticky_owner_do_not_block_hardware_line_writes():
    c, wid, uid, iid, cid, lid = _hw_fixture()
    _other, owner_id = login_same_workspace(wid, "drafter")
    # cutlist_owner_id survives an Unlock; only an active item_locked counts
    set_item(iid, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    for name, route in _hw_routes(iid, cid, lid).items():
        assert _send(c, route).status_code == route[3], name


def test_unknown_ids_are_still_404_not_lock_answers_for_hardware_lines():
    c, wid, uid, iid, cid, lid = _hw_fixture()
    set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
    assert c.post("/items/99999999/hardware_lines", json={"catalog_id": cid, "qty": 1}).status_code == 404
    assert c.patch("/hardware_lines/99999999", json={"qty": 1}).status_code == 404
    assert c.delete("/hardware_lines/99999999").status_code == 404


def test_project_catalog_writes_are_not_governed_by_an_items_lock():
    """The catalog belongs to the project, not to an item, so no item's lock
    governs it; removing a row still 409s while a line references it."""
    c, wid, uid, iid, cid, lid = _hw_fixture()
    set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)
    db = SessionLocal()
    try:
        pid = db.execute(text("SELECT project_id FROM items WHERE item_id = :i"), {"i": iid}).scalar()
        new_mid = _insert_hardware(db, wid=wid, sku=f"HW-{uuid.uuid4().hex[:6]}", description="Handle")
    finally:
        db.close()
    r = c.post(f"/projects/{pid}/hardware_catalog", json={"source_table": "hardware_materials", "source_id": new_mid})
    assert r.status_code == 201, r.text
    assert c.delete(f"/projects/{pid}/hardware_catalog/{cid}").status_code == 409   # still in use, not locked
