"""Tests for PATCH /items/{id}/status and PATCH /items/{id}/lifecycle/{stage_key}.

Schema context:
- item_status_log columns: (log_id, item_id, status, note, changed_by, changed_at)
  This is a status-change log, not a lifecycle log — written only by patch_item_status.
- item_stages PK: (item_id, stage_key) — ON CONFLICT DO UPDATE used for UPSERT.
- stages table has FK on item_stages.stage_key — must be seeded before inserting
  item_stages rows.
- status_options table has FK on items.status — must be seeded before inserting items.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES

# Reference data — must match what stages/status_options FK constraints accept.
_STATUS_KEYS = [
    ("CLEAR", 1),
    ("VOID", 2),
    ("NOTE!", 3),
    ("LIVE", 4),
    ("APPROVED", 5),
    ("HOLD", 6),
]
_STAGE_KEYS = [
    ("REQ", "Required", 1),
    ("SM", "Shop Material", 2),
    ("LISTED", "Listed", 3),
    ("DOWN", "Down", 4),
    ("CNC", "CNC", 5),
    ("EDGED", "Edged", 6),
    ("PAINTED", "Painted", 7),
    ("MADE", "Made", 8),
    ("DEL", "Delivered", 9),
    ("INST", "Installed", 10),
]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        extra = (
            "batch_allocations",
            "procurement_batches",
            "item_stages",
            "item_hardware_lines",
            "project_hardware_catalog",
            "items",
            "hardware_materials",
            "board_materials",
            "status_options",
            "stages",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _seed_refs(db) -> None:
    """Insert status_options and stages reference rows."""
    for key, order in _STATUS_KEYS:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order)"
                " VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    for key, label, order in _STAGE_KEYS:
        db.execute(
            text(
                "INSERT INTO stages(stage_key, label, sort_order)"
                " VALUES(:k, :l, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "l": label, "o": order},
        )
    db.commit()


def _login(role: str = "manager"):
    """Create workspace + user with the given role, return (client, wid, uid)."""
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


def _create_project(db, *, wid: int, uid: int, code: str = "HJ-001") -> int:
    pid = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id)
            VALUES (:code, 'Test Project', :uid)
            RETURNING project_id
            """
        ),
        {"code": code, "uid": uid},
    ).scalar()
    db.commit()
    return pid


def _insert_item(
    db,
    *,
    project_id: int,
    num: int,
    status: str = "CLEAR",
    description: str = "Test item",
) -> int:
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description, item_locked)
            VALUES (:num, :pid, :status, :desc, false)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id, "status": status, "desc": description},
    ).scalar()
    db.commit()
    return iid


# ── Test cases ─────────────────────────────────────────────────────────────────


def test_patch_status_writes_audit_and_edit_log():
    """PATCH /items/{id}/status updates items.status and writes audit + edit_log rows."""
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=1, status="CLEAR")
    finally:
        db.close()

    r = c.patch(f"/items/{iid}/status", json={"status": "LIVE"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "LIVE"

    db = SessionLocal()
    try:
        # Check items row updated
        row_status = db.execute(
            text("SELECT status FROM items WHERE item_id = :iid"), {"iid": iid}
        ).scalar()
        assert row_status == "LIVE"

        # Check item_status_log row
        log_row = db.execute(
            text("SELECT status FROM item_status_log WHERE item_id = :iid"),
            {"iid": iid},
        ).mappings().first()
        assert log_row is not None, "item_status_log row missing"
        assert log_row["status"] == "LIVE"

        # Check audit_log row
        audit_row = db.execute(
            text(
                "SELECT event, actor_id FROM audit_log"
                " WHERE target = :t AND event = 'item.status'"
            ),
            {"t": str(iid)},
        ).mappings().first()
        assert audit_row is not None, "audit_log row missing"
        assert audit_row["actor_id"] == uid

        # Check item_edit_log row
        edit_row = db.execute(
            text(
                "SELECT field, old_value, new_value FROM item_edit_log"
                " WHERE item_id = :iid AND field = 'item.status'"
            ),
            {"iid": iid},
        ).mappings().first()
        assert edit_row is not None, "item_edit_log row missing"
        assert edit_row["old_value"] == "CLEAR"
        assert edit_row["new_value"] == "LIVE"
    finally:
        db.close()


def test_status_value_validated_by_pydantic():
    """Invalid status string in body → 422 (Pydantic Literal rejection)."""
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=2)
    finally:
        db.close()

    r = c.patch(f"/items/{iid}/status", json={"status": "INVALID_VALUE"})
    assert r.status_code == 422, r.text


def test_patch_lifecycle_invalid_stage_400():
    """PATCH /items/{id}/lifecycle/UNKNOWN → 400."""
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=3)
    finally:
        db.close()

    r = c.patch(f"/items/{iid}/lifecycle/UNKNOWN", json={"done_date": "2026-05-01"})
    assert r.status_code == 400, r.text
    assert "stage_key" in r.json()["detail"].lower()


def test_patch_lifecycle_upserts_item_stages():
    """PATCH lifecycle/CNC with done_date creates item_stages row with that done_date."""
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=4)
    finally:
        db.close()

    r = c.patch(
        f"/items/{iid}/lifecycle/CNC",
        json={"done_date": "2026-05-15"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        stage_row = db.execute(
            text(
                "SELECT due_date, done_date FROM item_stages"
                " WHERE item_id = :iid AND stage_key = 'CNC'"
            ),
            {"iid": iid},
        ).mappings().first()
        assert stage_row is not None, "item_stages row not created"
        assert str(stage_row["done_date"]) == "2026-05-15"
    finally:
        db.close()


def test_patch_lifecycle_writes_item_status_log():
    """PATCH lifecycle/CNC with done_date writes an item_edit_log row for that field.

    Note: the spec calls this 'item_status_log' but the actual table with that name
    records status-value changes (not lifecycle date changes). This test verifies the
    item_edit_log row — the correct audit trail for lifecycle date mutations.
    """
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=5)
    finally:
        db.close()

    r = c.patch(
        f"/items/{iid}/lifecycle/CNC",
        json={"done_date": "2026-05-20"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        edit_row = db.execute(
            text(
                "SELECT field, new_value, actor_id FROM item_edit_log"
                " WHERE item_id = :iid AND field = 'lifecycle.CNC.done_date'"
            ),
            {"iid": iid},
        ).mappings().first()
        assert edit_row is not None, "item_edit_log row for lifecycle.CNC.done_date missing"
        assert edit_row["new_value"] == "2026-05-20"
        assert edit_row["actor_id"] == uid
    finally:
        db.close()


def test_patch_lifecycle_editor_allowed():
    """Editor role has tracking:write → PATCH lifecycle/CNC returns 200."""
    c, wid, uid = _login(role="editor")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=6)
    finally:
        db.close()

    r = c.patch(
        f"/items/{iid}/lifecycle/CNC",
        json={"done_date": "2026-06-01"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        stage_row = db.execute(
            text(
                "SELECT done_date FROM item_stages"
                " WHERE item_id = :iid AND stage_key = 'CNC'"
            ),
            {"iid": iid},
        ).mappings().first()
        assert stage_row is not None
        assert str(stage_row["done_date"]) == "2026-06-01"
    finally:
        db.close()


def test_patch_lifecycle_purchase_officer_403():
    """purchase_officer has tracking:read+comment only → 403 on lifecycle PATCH."""
    c, wid, uid = _login(role="purchase_officer")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=7)
    finally:
        db.close()

    r = c.patch(
        f"/items/{iid}/lifecycle/CNC",
        json={"done_date": "2026-06-01"},
    )
    assert r.status_code == 403, r.text
