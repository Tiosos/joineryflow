"""Tracking's All projects scope (Q633): `GET /tracking/items?filter=` returns exactly the items a
dashboard card counted, because both read `items/card_filters.py`."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login, login_same_workspace

pytestmark = pytest.mark.usefixtures("truncate_after")

YESTERDAY = date.today() - timedelta(days=1)
TODAY = date.today()
FILTERS = ("overdue", "in_optimisation", "awaiting_install")


def _item(pid: int, num: int, *, owner: int | None = None, status: str = "CLEAR",
         deleted: bool = False, stages: dict[str, tuple[date | None, date | None]] | None = None) -> int:
    """A Joinery Item with `stages` = {stage_key: (due, done)}."""
    db = SessionLocal()
    try:
        iid = db.execute(
            text("INSERT INTO items(num, project_id, status, description, item_locked, cutlist_owner_id, deleted)"
                 " VALUES (:n, :p, :s, :d, false, :o, :x) RETURNING item_id"),
            {"n": num, "p": pid, "s": status, "d": f"Item {num}", "o": owner, "x": deleted},
        ).scalar()
        for key, (due, done) in (stages or {}).items():
            db.execute(
                text("INSERT INTO item_stages(item_id, stage_key, due_date, done_date)"
                     " VALUES (:i, :k, :due, :done)"
                     " ON CONFLICT (item_id, stage_key) DO UPDATE"
                     " SET due_date = EXCLUDED.due_date, done_date = EXCLUDED.done_date"),
                {"i": iid, "k": key, "due": due, "done": done},
            )
        db.commit()
        return iid
    finally:
        db.close()


def _seed_two_projects(uid: int):
    """Projects A and B, each with one item per card, plus items no card counts."""
    db = SessionLocal()
    try:
        a = create_project(db, uid=uid, code="TA-001")
        b = create_project(db, uid=uid, code="TB-001")
    finally:
        db.close()
    n = iter(range(9000, 9100))
    ids = {}
    for pid, tag in ((a, "a"), (b, "b")):
        ids[f"overdue_{tag}"] = _item(pid, next(n), stages={"REQ": (YESTERDAY, None)})
        ids[f"opt_{tag}"] = _item(pid, next(n), stages={"DOWN": (YESTERDAY, YESTERDAY), "CNC": (TODAY, None)})
        ids[f"install_{tag}"] = _item(pid, next(n), stages={"DEL": (YESTERDAY, YESTERDAY), "INST": (TODAY, None)})
        _item(pid, next(n), stages={"REQ": (TODAY, None)})  # due today is not overdue: no card
    # A soft-deleted overdue item is not counted and must not be listed.
    _item(a, next(n), deleted=True, stages={"REQ": (YESTERDAY, None)})
    return a, b, ids


def _card(c, key: str) -> int:
    return next(m for m in c.get("/home/dashboard").json()["metrics"] if m["key"] == key)["value"]


def _listed(c, flt: str | None = None, **params) -> list[dict]:
    r = c.get("/tracking/items", params={**({"filter": flt} if flt else {}), **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_a_card_opens_exactly_the_rows_it_counted():
    c, wid, uid = login("admin")
    _seed_two_projects(uid)
    for flt in FILTERS:
        rows = _listed(c, flt)
        assert len(rows) == 2, flt                   # one in each project
        assert _card(c, flt) == len(rows), flt       # the number on the card is the rows shown
    # every link on the dashboard points at the All projects scope with that filter
    hrefs = {m["key"]: m["href"] for m in c.get("/home/dashboard").json()["metrics"]}
    for flt in FILTERS:
        assert hrefs[flt] == f"/tracking?scope=all&filter={flt}"


def test_rows_say_which_project_they_are_in():
    c, wid, uid = login("admin")
    a, b, ids = _seed_two_projects(uid)
    rows = _listed(c, "overdue")
    assert {(r["project_id"], r["project_code"]) for r in rows} == {(a, "TA-001"), (b, "TB-001")}
    assert {r["id"] for r in rows} == {ids["overdue_a"], ids["overdue_b"]}


def test_a_manager_sees_the_items_of_the_projects_they_manage():
    c, wid, uid = login("manager")
    db = SessionLocal()
    try:
        mine = create_project(db, uid=uid, code="MY-001")
    finally:
        db.close()
    _, other_uid = login_same_workspace(wid, "manager")
    db = SessionLocal()
    try:
        theirs = create_project(db, uid=other_uid, code="TH-001")
    finally:
        db.close()
    keep = _item(mine, 9200, stages={"REQ": (YESTERDAY, None)})
    _item(theirs, 9201, stages={"REQ": (YESTERDAY, None)})
    assert [r["id"] for r in _listed(c, "overdue")] == [keep]
    assert _card(c, "overdue") == 1


def test_a_drafter_sees_the_items_on_their_cutlists():
    c, wid, uid = login("drafter")
    _, mgr = login_same_workspace(wid, "manager")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=mgr, code="DR-001")
    finally:
        db.close()
    mine = _item(pid, 9300, owner=uid, stages={"REQ": (YESTERDAY, None)})
    _item(pid, 9301, owner=None, stages={"REQ": (YESTERDAY, None)})
    assert [r["id"] for r in _listed(c, "overdue")] == [mine]
    assert _card(c, "overdue") == 1


def test_another_workspaces_items_are_not_listed():
    c, wid, uid = login("admin")
    _seed_two_projects(uid)
    other, _, other_uid = login("admin", prefix="zz")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=other_uid, code="ZZ-001")
    finally:
        db.close()
    zz = _item(pid, 9400, stages={"REQ": (YESTERDAY, None)})
    assert [r["id"] for r in _listed(other, "overdue")] == [zz]


def test_status_and_stage_keep_their_meaning_in_the_all_projects_scope():
    c, wid, uid = login("admin")
    a, b, ids = _seed_two_projects(uid)
    void = _item(a, 9500, status="VOID", stages={"REQ": (YESTERDAY, None)})
    assert [r["id"] for r in _listed(c, status="VOID")] == [void]            # a record state
    at_cnc = {r["id"] for r in _listed(c, stage="CNC")}                      # items at a stage key
    assert at_cnc == {ids["opt_a"], ids["opt_b"]}
    assert {r["id"] for r in _listed(c, "overdue", status="VOID")} == {void}


def test_an_unknown_filter_is_refused_and_no_filter_lists_every_live_item():
    c, wid, uid = login("admin")
    _seed_two_projects(uid)
    assert c.get("/tracking/items", params={"filter": "late"}).status_code == 422
    assert len(_listed(c)) == 8      # 4 per project; the soft-deleted one is not listed
