"""Lock requests waiting for a decision show in the notification list of whoever may decide them.

Decided with the customer: the lock owner, managers and admins are told (the same people
`decide_lock_request` lets decide). Nothing is stored: a request counts while it is `pending` on
a live item and drops out when it is approved, rejected or its item is deleted, so there is
nothing to mark read. Someone whose role the approve / reject routes refuse (an editor) is not
told about what they cannot act on.
"""
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import create_project, login, login_same_workspace, set_item

_cleanup = truncate_fixture(
    "batch_allocations",
    "procurement_batches",
    "item_stages",
    "item_hardware_lines",
    "project_hardware_catalog",
    "item_lock_request",
    "items",
    "hardware_materials",
    "board_materials",
    "status_options",
    "stages",
)


def _item(pid: int) -> int:
    s = SessionLocal()
    try:
        iid = s.execute(
            text(
                "INSERT INTO items(num, project_id, status, description, code, item_locked,"
                " cutlist_owner_id) VALUES (:n, :p, 'CLEAR', 'Lock request item', 'LR-01', false, NULL)"
                " RETURNING item_id"
            ),
            {"n": uuid.uuid4().int % 900_000 + 100_000, "p": pid},
        ).scalar()
        s.commit()
        return iid
    finally:
        s.close()


def _waiting(c, **params):
    """The lock-request part of the bell's attention list: {"rows": [...], "count": total or None (not a recipient)}."""
    r = c.get("/notifications", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    return {"rows": [a for a in body["attention"] if a["kind"] == "lock_request"],
            "count": body["attention_totals"].get("lock_request")}


@pytest.fixture
def ws():
    manager, wid, mid = login("manager", prefix="lk")
    s = SessionLocal()
    try:
        pid = create_project(s, uid=mid, code=f"LK-{uuid.uuid4().hex[:5]}")
    finally:
        s.close()
    owner, owner_id = login_same_workspace(wid, "drafter", name="Owner Drafter")
    asker, asker_id = login_same_workspace(wid, "drafter", name="Asker Drafter")
    other, _ = login_same_workspace(wid, "drafter", name="Unrelated Drafter")
    admin, _ = login_same_workspace(wid, "admin", name="An Admin")
    iid = _item(pid)
    # First save claims the lock for the owner; a second person's save is held as a request.
    assert owner.patch(f"/items/{iid}", json={"description": "Owner edit"}).status_code == 200
    r = asker.patch(f"/items/{iid}", json={"description": "Asker proposal", "qty": 7})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "LOCK_REQUEST_CREATED", r.text
    return {"wid": wid, "pid": pid, "iid": iid, "rid": r.json()["detail"]["request_id"],
            "manager": manager, "owner": owner, "asker": asker, "other": other, "admin": admin,
            "owner_id": owner_id, "asker_id": asker_id}


def test_the_lock_owner_a_manager_and_an_admin_are_told(ws):
    for who in ("owner", "manager", "admin"):
        body = _waiting(ws[who])
        assert body["count"] == 1, who
        row = body["rows"][0]
        assert row["key"] == f"lock_request:{ws['rid']}", who
        assert row["url"] == f"/items/{ws['iid']}"
        assert "Asker Drafter" in row["title"] and "LK-" in row["title"] and row["title"].startswith("#")
        assert row["detail"] in ("Changes description, qty", "Changes qty, description")


def test_nobody_else_is_told(ws):
    # An unrelated drafter, and the person who asked, cannot decide it.
    for who in ("other", "asker"):
        assert _waiting(ws[who]) == {"rows": [], "count": 0}, who
    # Roles the approve / reject routes refuse (or that cannot write at all) get the plain list.
    for role in ("editor", "viewer", "estimator", "purchase_officer"):
        c, _ = login_same_workspace(ws["wid"], role)
        assert _waiting(c) == {"rows": [], "count": None}, role


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_a_decided_request_leaves_the_list(ws, decision):
    assert _waiting(ws["owner"])["count"] == 1
    r = ws["owner"].post(f"/lock-requests/{ws['rid']}/{decision}", json={})
    assert r.status_code == 200, r.text
    for who in ("owner", "manager", "admin"):
        assert _waiting(ws[who]) == {"rows": [], "count": 0}, who


def test_a_new_request_after_a_decision_comes_back(ws):
    ws["owner"].post(f"/lock-requests/{ws['rid']}/reject", json={})
    r = ws["asker"].patch(f"/items/{ws['iid']}", json={"description": "Second try"})
    assert r.status_code == 409
    assert _waiting(ws["manager"])["count"] == 1


def test_a_deleted_items_request_is_hidden(ws):
    set_item(ws["iid"], "deleted = true")
    for who in ("owner", "manager", "admin"):
        assert _waiting(ws[who])["count"] == 0, who


def test_another_workspaces_manager_is_not_told():
    # A second workspace with its own pending request: neither sees the other's.
    def one_workspace():
        manager, wid, mid = login("manager", prefix="lk")
        s = SessionLocal()
        try:
            pid = create_project(s, uid=mid, code=f"LK-{uuid.uuid4().hex[:5]}")
        finally:
            s.close()
        owner, _ = login_same_workspace(wid, "drafter")
        asker, _ = login_same_workspace(wid, "drafter")
        iid = _item(pid)
        owner.patch(f"/items/{iid}", json={"description": "x"})
        assert asker.patch(f"/items/{iid}", json={"description": "y"}).status_code == 409
        return manager, iid

    m1, i1 = one_workspace()
    m2, i2 = one_workspace()
    for m, mine in ((m1, i1), (m2, i2)):
        body = _waiting(m)
        assert body["count"] == 1
        assert [r["url"] for r in body["rows"]] == [f"/items/{mine}"]


def test_a_paged_or_unread_only_call_does_not_carry_the_list(ws):
    for params in ({"offset": 1}, {"unread_only": True}):
        assert _waiting(ws["manager"], **params) == {"rows": [], "count": None}, params
