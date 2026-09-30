"""Lock checks on PATCH /items/{id}/status, POST /items/bulk-status and
PATCH /items/{id}/lifecycle/{stage_key} (Plan V1 §12 follow-up).

The rule is `assert_item_content_unlocked` with the Approval Lock left out:
Hard Lock refuses everyone, a Controlled Lock refuses anyone but its owner and
managers/admins.  The Approval Lock (`status = 'APPROVED'`) must NOT apply here —
changing status is how an approved item is unlocked, and production dates follow
approval.  A refusal changes and logs nothing.
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import TRUNCATE_TABLES
from .test_hardware_lines_routes import (
    _create_project,
    _login,
    _login_same_workspace,
    _seed_status,
    _set_item,
)

_EXTRA_TABLES = (
    "status_options",
    "item_stages",
    "item_edit_log",
    "item_status_log",
    "item_lock_request",
    "items",
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


def _fixture():
    """A drafter, their workspace, a project."""
    c, wid, uid = _login(role="drafter")
    db = SessionLocal()
    try:
        pid = _create_project(db, uid=uid, code=f"SL-{uuid.uuid4().hex[:6]}")
        _seed_status(db)
        db.execute(text("INSERT INTO status_options(status_key, sort_order)"
                        " VALUES ('APPROVED', 5) ON CONFLICT DO NOTHING"))
        db.commit()
    finally:
        db.close()
    return c, wid, uid, pid


def _item(pid: int, num: int, status: str = "CLEAR") -> int:
    db = SessionLocal()
    try:
        iid = db.execute(
            text("INSERT INTO items(project_id, num, status) VALUES (:p, :n, :s) RETURNING item_id"),
            {"p": pid, "n": num, "s": status},
        ).scalar()
        db.commit()
        return iid
    finally:
        db.close()


def _state(iid: int, wid: int) -> tuple:
    """Everything a refused write must leave alone."""
    db = SessionLocal()
    try:
        return (
            db.execute(text("SELECT status FROM items WHERE item_id = :i"), {"i": iid}).scalar(),
            db.execute(text("SELECT count(*) FROM item_status_log WHERE item_id = :i"), {"i": iid}).scalar(),
            db.execute(text("SELECT count(*) FROM item_stages WHERE item_id = :i"), {"i": iid}).scalar(),
            db.execute(text("SELECT count(*) FROM item_edit_log WHERE item_id = :i"), {"i": iid}).scalar(),
            db.execute(
                text("SELECT count(*) FROM audit_log WHERE workspace_id = :w AND target = :t"
                     " AND event LIKE 'item.%'"),
                {"w": wid, "t": str(iid)},
            ).scalar(),
        )
    finally:
        db.close()


def _status(client, iid: int, status: str = "LIVE"):
    return client.patch(f"/items/{iid}/status", json={"status": status, "note": "n"})


def _lifecycle(client, iid: int, stage: str = "REQ"):
    return client.patch(f"/items/{iid}/lifecycle/{stage}", json={"done_date": "2026-09-01"})


_ROUTES = {"status": _status, "lifecycle": _lifecycle}
_NAMES = ["status", "lifecycle"]


def _hard_lock(iid: int, uid: int) -> None:
    _set_item(iid, "hard_locked_at = now(), hard_locked_by = :u", u=uid)


@pytest.mark.parametrize("name", _NAMES)
def test_a_hard_lock_refuses_everyone(name):
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1)
    _hard_lock(iid, uid)
    admin, _ = _login_same_workspace(wid, "admin")

    before = _state(iid, wid)
    for client in (c, admin):
        r = _ROUTES[name](client, iid)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == {"code": "HARD_LOCKED", "locked_by": uid}
    assert _state(iid, wid) == before, "a refused write must change and log nothing"

    _set_item(iid, "hard_locked_at = NULL, hard_locked_by = NULL")
    assert _ROUTES[name](c, iid).status_code == 200      # the same request goes through once cleared


@pytest.mark.parametrize("name", _NAMES)
def test_a_controlled_lock_refuses_a_non_owner_but_not_the_owner_or_a_manager(name):
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1)
    owner, owner_id = _login_same_workspace(wid, "drafter", name="Olive Owner")
    foreman, _ = _login_same_workspace(wid, "editor")
    manager, _ = _login_same_workspace(wid, "manager")
    _set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)

    before = _state(iid, wid)
    for client in (c, foreman):
        r = _ROUTES[name](client, iid)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == {
            "code": "ITEM_LOCKED", "owner_id": owner_id, "owner_name": "Olive Owner",
        }
    assert _state(iid, wid) == before

    assert _ROUTES[name](owner, iid).status_code == 200
    assert _ROUTES[name](manager, iid, *(["HOLD"] if name == "status" else ["CNC"])).status_code == 200


@pytest.mark.parametrize("name", _NAMES)
def test_an_unlocked_item_and_a_sticky_owner_do_not_block(name):
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1)
    _other, owner_id = _login_same_workspace(wid, "drafter")
    # cutlist_owner_id survives an Unlock; only an active item_locked counts
    _set_item(iid, "item_locked = false, cutlist_owner_id = :o", o=owner_id)
    assert _ROUTES[name](c, iid).status_code == 200


def test_the_approval_lock_does_not_stop_a_status_change_it_is_how_you_unlock():
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1, status="APPROVED")
    r = _status(c, iid, "CLEAR")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CLEAR"
    db = SessionLocal()
    try:
        assert db.execute(
            text("SELECT count(*) FROM audit_log WHERE event = 'item.approval_unlock'"
                 " AND target = :t"), {"t": str(iid)},
        ).scalar() == 1
    finally:
        db.close()


def test_the_approval_lock_does_not_stop_a_lifecycle_date():
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1, status="APPROVED")
    r = _lifecycle(c, iid, "DOWN")
    assert r.status_code == 200, r.text
    assert r.json()["stages"]["DOWN"]["done_date"] == "2026-09-01"


def test_a_hard_lock_wins_over_an_approved_item_and_names_hard_not_approval():
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1, status="APPROVED")
    _hard_lock(iid, uid)
    for name in _NAMES:
        r = _ROUTES[name](c, iid)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "HARD_LOCKED"


def test_unknown_item_and_bad_stage_key_are_not_lock_answers():
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1)
    _hard_lock(iid, uid)
    assert _status(c, 99999999).status_code == 404
    assert _lifecycle(c, 99999999).status_code == 404
    assert _lifecycle(c, iid, "NOPE").status_code == 400     # validated before any lock


# ── bulk ───────────────────────────────────────────────────────────────────────


def test_bulk_status_skips_locked_items_and_lists_them():
    c, wid, uid, pid = _fixture()
    free = _item(pid, 1)
    approved = _item(pid, 2, status="APPROVED")          # the Approval Lock does not skip
    hard = _item(pid, 3)
    controlled = _item(pid, 4)
    _hard_lock(hard, uid)
    _other, owner_id = _login_same_workspace(wid, "drafter", name="Olive Owner")
    _set_item(controlled, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    foreman, _ = _login_same_workspace(wid, "editor")

    before = {i: _state(i, wid) for i in (hard, controlled)}
    r = foreman.post(
        "/items/bulk-status",
        json={"item_ids": [free, approved, hard, controlled], "status": "HOLD", "note": "bulk"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2
    assert body["not_found"] == [] and body["cross_workspace"] == []
    assert sorted(body["locked"], key=lambda x: x["item_id"]) == [
        {"item_id": hard, "code": "HARD_LOCKED", "owner_name": None},
        {"item_id": controlled, "code": "ITEM_LOCKED", "owner_name": "Olive Owner"},
    ]
    assert {i: _state(i, wid) for i in (hard, controlled)} == before, "skipped items change and log nothing"
    assert _state(free, wid)[0] == "HOLD" and _state(approved, wid)[0] == "HOLD"


def test_bulk_status_a_manager_and_the_owner_pass_a_controlled_lock():
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1)
    owner, owner_id = _login_same_workspace(wid, "drafter")
    manager, _ = _login_same_workspace(wid, "manager")
    _set_item(iid, "item_locked = true, cutlist_owner_id = :o", o=owner_id)
    for client, status in ((owner, "LIVE"), (manager, "HOLD")):
        r = client.post("/items/bulk-status", json={"item_ids": [iid], "status": status, "note": "n"})
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 1 and r.json()["locked"] == []


def test_bulk_status_with_nothing_locked_reports_an_empty_locked_list():
    c, wid, uid, pid = _fixture()
    iid = _item(pid, 1)
    r = c.post("/items/bulk-status", json={"item_ids": [iid], "status": "LIVE", "note": "n"})
    assert r.status_code == 200
    assert r.json() == {"updated": 1, "not_found": [], "cross_workspace": [], "locked": []}
