"""Tests for modules + parts CRUD endpoints (Task 17).

6 tests covering the happy paths and auth/workspace guards:
  1. test_create_module_writes_create_log
  2. test_create_part_writes_log_with_field_create
  3. test_patch_part_qty_writes_one_edit_log_row
  4. test_delete_part_writes_delete_log
  5. test_module_in_other_workspace_404
  6. test_editor_403_on_part_patch

Uses the autouse-TRUNCATE pattern from test_items_routes.py.
Seed helpers (_seed_module, _seed_part) mirror patterns from test_items_routes.py.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

# ── Cleanup fixture ────────────────────────────────────────────────────────────

_EXTRA_TABLES = (
    "parts",
    "modules",
    "item_edit_log",
    "item_status_log",
    "item_stages",
    "item_hardware_lines",
    "project_hardware_catalog",
    "items",
    "board_materials",
    "status_options",
    "stages",
)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        all_tables = ", ".join(list(_EXTRA_TABLES) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


# ── Seed helpers ───────────────────────────────────────────────────────────────


def _seed_refs(db) -> None:
    """Insert status_options reference rows required for items.status FK."""
    for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order)"
                " VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    db.commit()


def _login(role: str = "drafter") -> tuple:
    """Create a fresh workspace + user, return (client, workspace_id, user_id)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        _seed_refs(db)
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'H') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r)
                RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        db.commit()
    finally:
        db.close()

    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid


def _create_project(db, *, wid: int, uid: int) -> int:
    code = f"HJ-{uuid.uuid4().hex[:8]}"
    pid = db.execute(
        text(
            "INSERT INTO projects(project_code, name, pm_id)"
            " VALUES (:code, 'Test Project', :uid)"
            " RETURNING project_id"
        ),
        {"code": code, "uid": uid},
    ).scalar()
    db.commit()
    return pid


def _insert_item(db, *, project_id: int, num: int) -> int:
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, code, item_locked)
            VALUES (:num, :pid, 'CLEAR', 'Test item', 'CAB-01', false)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id},
    ).scalar()
    db.commit()
    return iid


def _seed_module(db, *, item_id: int, module_no: str = "M1", name: str = "Carcass") -> int:
    mid = db.execute(
        text(
            "INSERT INTO modules(item_id, module_no, name)"
            " VALUES (:iid, :mno, :name)"
            " RETURNING module_id"
        ),
        {"iid": item_id, "mno": module_no, "name": name},
    ).scalar()
    db.commit()
    return mid


def _seed_part(db, *, module_id: int, part_name: str = "Side Panel", qty: int = 2) -> int:
    pid = db.execute(
        text(
            "INSERT INTO parts(module_id, qty, part_name)"
            " VALUES (:mid, :qty, :pname)"
            " RETURNING part_id"
        ),
        {"mid": module_id, "qty": qty, "pname": part_name},
    ).scalar()
    db.commit()
    return pid


# ── Test cases ─────────────────────────────────────────────────────────────────


def test_create_module_writes_create_log():
    """POST /items/{id}/modules creates module and writes item_edit_log field='_create_module'."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=1)
    finally:
        db.close()

    r = c.post(
        f"/items/{iid}/modules",
        json={"module_no": "M1", "name": "Carcass"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Carcass"

    db = SessionLocal()
    try:
        logs = db.execute(
            text("SELECT field, actor_id FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    create_logs = [l for l in logs if l["field"] == "_create_module"]
    assert len(create_logs) == 1, f"Expected 1 _create_module log row, got {logs}"
    assert create_logs[0]["actor_id"] == uid


def test_create_part_writes_log_with_field_create():
    """POST /modules/{mid}/parts creates part and writes item_edit_log field='_create_part'."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=2)
        mid = _seed_module(db, item_id=iid, module_no="M1")
    finally:
        db.close()

    r = c.post(
        f"/modules/{mid}/parts",
        json={"qty": 1, "part_name": "Top Panel", "len_mm": 600, "wid_mm": 400},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["part_name"] == "Top Panel"
    assert body["qty"] == 1
    assert body["is_rev_c"] is False

    db = SessionLocal()
    try:
        logs = db.execute(
            text("SELECT field FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    fields = [l["field"] for l in logs]
    assert "_create_part" in fields, f"Expected _create_part in edit log, got {fields}"


def test_patch_part_qty_writes_one_edit_log_row():
    """PATCH /parts/{pid} with qty=5 writes exactly 1 new edit_log row with field='parts.qty'."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid_proj = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid_proj, num=3)
        mid = _seed_module(db, item_id=iid, module_no="M1")
        part_id = _seed_part(db, module_id=mid, part_name="Side Panel", qty=2)
    finally:
        db.close()

    db = SessionLocal()
    try:
        before_count = db.execute(
            text("SELECT COUNT(*) FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).scalar()
    finally:
        db.close()

    r = c.patch(f"/parts/{part_id}", json={"qty": 5})
    assert r.status_code == 200, r.text
    assert r.json()["qty"] == 5

    db = SessionLocal()
    try:
        after_count = db.execute(
            text("SELECT COUNT(*) FROM item_edit_log WHERE item_id = :iid"),
            {"iid": iid},
        ).scalar()
        qty_logs = db.execute(
            text(
                "SELECT field FROM item_edit_log"
                " WHERE item_id = :iid AND field = 'parts.qty'"
            ),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    new_rows = after_count - before_count
    assert new_rows == 1, f"Expected exactly 1 new log row, got {new_rows}"
    assert len(qty_logs) == 1, f"Expected 1 parts.qty log row, got {qty_logs}"


def test_delete_part_writes_delete_log():
    """DELETE /parts/{pid} writes _delete_part log row before delete; row persists after."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid_proj = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid_proj, num=4)
        mid = _seed_module(db, item_id=iid, module_no="M1")
        part_id = _seed_part(db, module_id=mid, part_name="Bottom Panel", qty=1)
    finally:
        db.close()

    r = c.delete(f"/parts/{part_id}")
    assert r.status_code == 204, r.text

    db = SessionLocal()
    try:
        part_row = db.execute(
            text("SELECT 1 FROM parts WHERE part_id = :pid"),
            {"pid": part_id},
        ).first()
        delete_logs = db.execute(
            text(
                "SELECT field FROM item_edit_log"
                " WHERE item_id = :iid AND field = '_delete_part'"
            ),
            {"iid": iid},
        ).mappings().all()
    finally:
        db.close()

    assert part_row is None, "Part should have been deleted"
    assert len(delete_logs) == 1, f"Expected 1 _delete_part log row, got {delete_logs}"


def test_module_in_other_workspace_404():
    """Workspace B cannot PATCH workspace A's module — must get 404."""
    c_a, wid_a, uid_a = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid_a, uid=uid_a)
        iid = _insert_item(db, project_id=pid, num=5)
        mid = _seed_module(db, item_id=iid, module_no="M1", name="Original")
    finally:
        db.close()

    c_b, _wid_b, _uid_b = _login(role="drafter")
    r = c_b.patch(f"/modules/{mid}", json={"name": "Hijacked"})
    assert r.status_code == 404, r.text


def test_editor_403_on_part_patch():
    """An editor (not drafter/manager/admin) cannot PATCH a part — must get 403."""
    c_drafter, wid, uid_drafter = _login(role="drafter")
    db = SessionLocal()
    try:
        pid_proj = _create_project(db, wid=wid, uid=uid_drafter)
        iid = _insert_item(db, project_id=pid_proj, num=6)
        mid = _seed_module(db, item_id=iid, module_no="M1")
        part_id = _seed_part(db, module_id=mid, part_name="Door", qty=1)
        slug_row = db.execute(
            text("SELECT slug FROM workspace WHERE id = :wid"),
            {"wid": wid},
        ).mappings().first()
        slug = slug_row["slug"]
    finally:
        db.close()

    suffix = uuid.uuid4().hex[:8]
    editor_email = f"editor-{suffix}@example.com"
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'Editor', :p, 'editor')
                """
            ),
            {"w": wid, "e": editor_email, "p": hash_password("pw")},
        )
        db.commit()
    finally:
        db.close()

    c_editor = TestClient(app)
    login_r = c_editor.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": editor_email, "password": "pw"},
    )
    assert login_r.status_code == 200, login_r.text

    r = c_editor.patch(f"/parts/{part_id}", json={"qty": 99})
    assert r.status_code == 403, r.text
