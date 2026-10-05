"""Tests for POST /items/bulk-status (Tracking 2.0 #10 T04)."""

from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal

from .helpers import login
from .conftest import truncate_fixture

_STATUS_KEYS = [
    ("CLEAR", 1),
    ("VOID", 2),
    ("NOTE!", 3),
    ("LIVE", 4),
    ("APPROVED", 5),
    ("HOLD", 6),
]


_cleanup = truncate_fixture(
    "item_status_log",
    "item_edit_log",
    "item_stages",
    "items",
    "status_options",
)


def _seed_status_options(db):
    for key, order in _STATUS_KEYS:
        db.execute(
            text(
                "INSERT INTO status_options(status_key, sort_order)"
                " VALUES(:k, :o) ON CONFLICT DO NOTHING"
            ),
            {"k": key, "o": order},
        )
    db.commit()


def _login(role: str = "manager"):
    return login(role, prefix="bs")




def _create_project(db, *, wid: int, uid: int, code: str = "BS-001") -> int:
    pid = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES (:c, :n, :uid, :wid)
            RETURNING project_id
            """
        ),
        {"c": code, "n": f"BS Project {code}", "uid": uid, "wid": wid},
    ).scalar()
    db.commit()
    return pid


def _insert_item(db, *, project_id: int, num: int) -> int:
    iid = db.execute(
        text(
            """
            INSERT INTO items(num, project_id, status, description)
            VALUES (:num, :pid, 'CLEAR', 'i' || :num)
            RETURNING item_id
            """
        ),
        {"num": num, "pid": project_id},
    ).scalar()
    db.commit()
    return iid


def test_bulk_status_happy_path():
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        ids = [_insert_item(db, project_id=pid, num=n) for n in (101, 102, 103)]
    finally:
        db.close()

    r = c.post(
        "/items/bulk-status",
        json={"item_ids": ids, "status": "HOLD", "note": "Awaiting client signoff"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["updated"] == 3
    assert payload["not_found"] == []

    db = SessionLocal()
    try:
        statuses = db.execute(
            text("SELECT status FROM items WHERE item_id = ANY(:ids) ORDER BY item_id"),
            {"ids": ids},
        ).scalars().all()
        assert statuses == ["HOLD", "HOLD", "HOLD"]

        log_count = db.execute(
            text(
                "SELECT COUNT(*) FROM item_status_log"
                " WHERE item_id = ANY(:ids) AND note = 'Awaiting client signoff'"
            ),
            {"ids": ids},
        ).scalar()
        assert log_count == 3

        audit_count = db.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE event = 'item.status.bulk'"),
        ).scalar()
        assert audit_count == 3
    finally:
        db.close()


def test_bulk_status_missing_note_422():
    c, wid, uid = _login(role="manager")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=104)
    finally:
        db.close()

    r = c.post("/items/bulk-status", json={"item_ids": [iid], "status": "HOLD", "note": ""})
    assert r.status_code == 422, r.text


def test_bulk_status_reports_another_workspaces_item_as_not_found():
    """An id from another workspace is indistinguishable from one that does not exist:
    both come back in not_found, and the response has no field that tells them apart."""
    c, wid, uid = _login(role="manager")

    db = SessionLocal()
    try:
        _seed_status_options(db)
        other_wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES('bs-other', 'Other') RETURNING id"),
        ).scalar()
        other_uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, 'other@x.test', 'O', :p, 'manager')
                RETURNING id
                """
            ),
            {"w": other_wid, "p": hash_password("pw")},
        ).scalar()
        other_pid = _create_project(db, wid=other_wid, uid=other_uid, code="BS-OTHER")
        other_iid = _insert_item(db, project_id=other_pid, num=999)

        own_pid = _create_project(db, wid=wid, uid=uid)
        own_iid = _insert_item(db, project_id=own_pid, num=105)
    finally:
        db.close()

    missing_iid = 9_999_999
    r = c.post(
        "/items/bulk-status",
        json={
            "item_ids": [own_iid, missing_iid, other_iid],
            "status": "VOID",
            "note": "bulk-mixed test",
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["updated"] == 1
    assert sorted(payload["not_found"]) == sorted([missing_iid, other_iid])
    assert "cross_workspace" not in payload
    # and nothing of the other workspace's item changed
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT status FROM items WHERE item_id = :i"),
                          {"i": other_iid}).scalar() != "VOID"
    finally:
        db.close()


def test_bulk_status_purchase_officer_403():
    c, wid, uid = _login(role="purchase_officer")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=106)
    finally:
        db.close()

    r = c.post(
        "/items/bulk-status",
        json={"item_ids": [iid], "status": "HOLD", "note": "x"},
    )
    assert r.status_code == 403, r.text


def test_bulk_status_viewer_403():
    c, wid, uid = _login(role="viewer")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=107)
    finally:
        db.close()

    r = c.post(
        "/items/bulk-status",
        json={"item_ids": [iid], "status": "HOLD", "note": "x"},
    )
    assert r.status_code == 403, r.text


def test_bulk_status_editor_allowed():
    c, wid, uid = _login(role="editor")
    db = SessionLocal()
    try:
        pid = _create_project(db, wid=wid, uid=uid)
        iid = _insert_item(db, project_id=pid, num=108)
    finally:
        db.close()

    r = c.post(
        "/items/bulk-status",
        json={"item_ids": [iid], "status": "LIVE", "note": "approved on call"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1
