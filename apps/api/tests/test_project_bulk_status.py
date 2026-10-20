"""POST /projects/{pid}/bulk-status: the Status pop-up's "Update Status To All".

One status + note for every live joinery item of the project, in one transaction. Related parts
and deleted items are not touched, a Hard-Locked item is skipped and listed, and there is no
500-item cap (that is the id-list route's limit).
"""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login, login_same_workspace, set_item

_cleanup = truncate_fixture(
    "item_status_log",
    "item_edit_log",
    "item_stages",
    "items",
    "status_options",
)


def _item(db, pid: int, num: int, *, parent: int | None = None) -> int:
    row_type = "related_part" if parent else "joinery_item"
    iid = db.execute(
        text(
            "INSERT INTO items(num, project_id, status, description, row_type, parent_item_id,"
            " related_part_type_key) VALUES (:n, :p, 'CLEAR', 'i' || :n, :rt, :par, :rk)"
            " RETURNING item_id"
        ),
        {"n": num, "p": pid, "rt": row_type, "par": parent, "rk": "benchtop" if parent else None},
    ).scalar()
    db.commit()
    return iid


def _status(iid: int) -> str:
    db = SessionLocal()
    try:
        return db.execute(text("SELECT status FROM items WHERE item_id = :i"), {"i": iid}).scalar()
    finally:
        db.close()


@pytest.fixture
def project():
    c, wid, uid = login(role="manager")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="PB-001")
        items = [_item(db, pid, n) for n in (301, 302, 303)]
        related = _item(db, pid, 399, parent=items[0])
        gone = _item(db, pid, 304)
    finally:
        db.close()
    set_item(gone, "deleted = true")
    return {"c": c, "wid": wid, "pid": pid, "items": items, "related": related, "gone": gone}


def test_every_live_joinery_item_changes_and_nothing_else(project):
    p = project
    r = p["c"].post(f"/projects/{p['pid']}/bulk-status", json={"status": "HOLD", "note": "Client paused the job"})
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 3, "not_found": [], "locked": []}
    assert [_status(i) for i in p["items"]] == ["HOLD"] * 3
    assert _status(p["related"]) == "CLEAR"            # related parts keep their own status
    assert _status(p["gone"]) == "CLEAR"               # a deleted item is not resurrected or touched

    db = SessionLocal()
    try:
        logged = db.execute(
            text("SELECT COUNT(*) FROM item_status_log WHERE note = 'Client paused the job'")
        ).scalar()
        audited = db.execute(text("SELECT COUNT(*) FROM audit_log WHERE event = 'item.status.bulk'")).scalar()
    finally:
        db.close()
    assert (logged, audited) == (3, 3)


def test_a_hard_locked_item_is_skipped_and_listed(project):
    p = project
    set_item(p["items"][1], "hard_locked_at = now()")
    r = p["c"].post(f"/projects/{p['pid']}/bulk-status", json={"status": "LIVE", "note": "Go"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert [x["item_id"] for x in body["locked"]] == [p["items"][1]]
    assert _status(p["items"][1]) == "CLEAR"


def test_there_is_no_500_item_cap(project):
    p = project
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO items(num, project_id, status, description)"
                " SELECT 10000 + g, :p, 'CLEAR', 'bulk' FROM generate_series(1, 520) g"
            ),
            {"p": p["pid"]},
        )
        db.commit()
    finally:
        db.close()
    r = p["c"].post(f"/projects/{p['pid']}/bulk-status", json={"status": "VOID", "note": "Whole job void"})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 523


def test_note_is_required_and_status_must_be_known(project):
    p = project
    assert p["c"].post(f"/projects/{p['pid']}/bulk-status", json={"status": "HOLD", "note": ""}).status_code == 422
    assert p["c"].post(f"/projects/{p['pid']}/bulk-status", json={"status": "HOLD"}).status_code == 422
    assert p["c"].post(f"/projects/{p['pid']}/bulk-status", json={"status": "NOPE", "note": "x"}).status_code == 422
    assert [_status(i) for i in p["items"]] == ["CLEAR"] * 3


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("purchase_officer", 403), ("editor", 200)])
def test_permission_is_tracking_write(project, role, expected):
    p = project
    other, _ = login_same_workspace(p["wid"], role)
    r = other.post(f"/projects/{p['pid']}/bulk-status", json={"status": "HOLD", "note": "x"})
    assert r.status_code == expected, r.text


def test_another_workspaces_project_is_a_404_like_a_missing_one(project):
    p = project
    stranger, _, _ = login(role="admin", prefix="other")
    real = stranger.post(f"/projects/{p['pid']}/bulk-status", json={"status": "HOLD", "note": "x"})
    ghost = stranger.post("/projects/99999999/bulk-status", json={"status": "HOLD", "note": "x"})
    assert (real.status_code, real.json()) == (ghost.status_code, ghost.json()) == (404, {"detail": "project not found"})
    assert [_status(i) for i in p["items"]] == ["CLEAR"] * 3
