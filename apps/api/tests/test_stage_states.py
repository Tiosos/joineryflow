"""Overdue / At risk / Delayed (Q591): one server-side definition per stage.

A stage with a due date and no done date is Overdue when due before today, At risk when due within
the workspace's `at_risk_days` and an earlier stage (in the item's own order) is not done; a stage
done after its due date is Delayed. The item-level lists read the same SQL as the per-stage state.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .helpers import create_project, login, login_same_workspace

pytestmark = pytest.mark.usefixtures("truncate_after")

TODAY = date.today()


def D(n: int) -> date:
    return TODAY + timedelta(days=n)


EARLY = ("REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED")
_num = iter(range(8000, 9000))


def _item(pid: int, stages: dict[str, tuple[date | None, date | None]], *, painting: bool = False,
          paint_last: bool = False) -> int:
    db = SessionLocal()
    try:
        iid = db.execute(
            text("INSERT INTO items(num, project_id, status, description, item_locked, painting_req, paint_after_assembly)"
                 " VALUES (:n, :p, 'CLEAR', 'x', false, :pr, :pl) RETURNING item_id"),
            {"n": next(_num), "p": pid, "pr": painting, "pl": paint_last},
        ).scalar()
        for key, (due, done) in stages.items():
            db.execute(text("INSERT INTO item_stages(item_id, stage_key, due_date, done_date) VALUES (:i, :k, :a, :b)"),
                       {"i": iid, "k": key, "a": due, "b": done})
        db.commit()
        return iid
    finally:
        db.close()


def _done_through(last: str, **extra):
    """Every stage up to and including `last` done yesterday-ish with no due date (nothing late)."""
    order = ["REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED", "MADE", "PACKING", "DEL", "INST"]
    return {k: (None, D(-5)) for k in order[: order.index(last) + 1]} | extra


def _row(c, pid: int, iid: int) -> dict:
    rows = c.get(f"/projects/{pid}/items").json()["items"]
    return next(r for r in rows if r["id"] == iid)


@pytest.fixture()
def world():
    c, wid, uid = login("admin")
    db = SessionLocal()
    try:
        pid = create_project(db, uid=uid, code="SS-001")
    finally:
        db.close()
    return c, wid, pid


def test_overdue_is_past_due_and_not_done(world):
    c, wid, pid = world
    iid = _item(pid, {"CNC": (D(-1), None), "EDGED": (D(0), None)})
    r = _row(c, pid, iid)
    assert r["stages"]["CNC"]["state"] == "overdue"
    assert r["stages"]["EDGED"]["state"] != "overdue"            # due today is not yet overdue
    assert r["is_overdue"] is True and r["is_delayed"] is False


def test_at_risk_needs_a_due_date_inside_the_window_and_an_earlier_stage_not_done(world):
    c, wid, pid = world
    risky = _item(pid, _done_through("DOWN") | {"CNC": (D(1), None), "EDGED": (D(2), None)})
    r = _row(c, pid, risky)
    assert r["stages"]["CNC"]["state"] == "open"                 # everything before CNC is done
    assert r["stages"]["EDGED"]["state"] == "at_risk"            # CNC (earlier) is not done
    assert r["is_at_risk"] is True and r["is_overdue"] is False

    far = _item(pid, _done_through("DOWN") | {"CNC": (D(40), None), "EDGED": (D(41), None)})
    r = _row(c, pid, far)
    assert r["stages"]["EDGED"]["state"] == "open" and r["is_at_risk"] is False   # outside the window

    clear = _item(pid, _done_through("CNC") | {"EDGED": (D(1), None)})
    assert _row(c, pid, clear)["stages"]["EDGED"]["state"] == "open"             # nothing earlier is open


def test_overdue_wins_over_at_risk(world):
    c, wid, pid = world
    iid = _item(pid, _done_through("DOWN") | {"CNC": (D(-2), None), "EDGED": (D(-1), None)})
    r = _row(c, pid, iid)
    assert r["stages"]["EDGED"]["state"] == "overdue"
    assert r["is_at_risk"] is False


def test_the_window_is_the_workspace_setting_and_only_an_admin_changes_it(world):
    c, wid, pid = world
    iid = _item(pid, _done_through("DOWN") | {"CNC": (D(5), None), "EDGED": (D(6), None)})
    assert c.get("/workspace/planning").json() == {"at_risk_days": 3}               # the default
    assert _row(c, pid, iid)["is_at_risk"] is False
    r = c.patch("/workspace/planning", json={"at_risk_days": 7})
    assert r.status_code == 200 and r.json() == {"at_risk_days": 7}
    row = _row(c, pid, iid)
    assert row["stages"]["EDGED"]["state"] == "at_risk" and row["is_at_risk"] is True
    for bad in (-1, 91, "x"):
        assert c.patch("/workspace/planning", json={"at_risk_days": bad}).status_code == 422
    mgr, _ = login_same_workspace(wid, "manager")
    assert mgr.patch("/workspace/planning", json={"at_risk_days": 1}).status_code == 403
    assert mgr.get("/workspace/planning").json() == {"at_risk_days": 7}              # anyone signed in may read it
    db = SessionLocal()
    try:
        assert db.execute(text("SELECT count(*) FROM audit_log WHERE workspace_id = :w AND event = 'workspace.planning'"),
                          {"w": wid}).scalar() == 1
    finally:
        db.close()


def test_another_workspace_keeps_its_own_window(world):
    c, wid, pid = world
    c.patch("/workspace/planning", json={"at_risk_days": 30})
    other, _, _ = login("admin", prefix="zz")
    assert other.get("/workspace/planning").json() == {"at_risk_days": 3}


def test_earlier_means_the_items_own_order_and_a_stage_it_does_not_need_is_skipped(world):
    c, wid, pid = world
    # Not painted (the default): an unfinished PAINTED row does not hold MADE back.
    not_painted = _item(pid, _done_through("EDGED") | {"PAINTED": (None, None), "MADE": (D(1), None)})
    assert _row(c, pid, not_painted)["stages"]["MADE"]["state"] == "open"
    # Painted, paint before assembly: PAINTED is earlier than MADE, so MADE is at risk.
    painted = _item(pid, _done_through("EDGED") | {"PAINTED": (None, None), "MADE": (D(1), None)}, painting=True)
    assert _row(c, pid, painted)["stages"]["MADE"]["state"] == "at_risk"
    # Painted, paint after assembly: PAINTED comes after MADE, so MADE is not held and PAINTED is.
    last = _item(pid, _done_through("EDGED") | {"MADE": (D(1), None), "PAINTED": (D(2), None)},
                 painting=True, paint_last=True)
    r = _row(c, pid, last)
    assert r["stages"]["MADE"]["state"] == "open" and r["stages"]["PAINTED"]["state"] == "at_risk"


def test_delayed_is_a_stage_done_after_its_due_date_and_the_item_list_stops_at_install(world):
    c, wid, pid = world
    late = _item(pid, {"CNC": (D(-3), D(-1)), "EDGED": (D(2), None)})
    r = _row(c, pid, late)
    assert r["stages"]["CNC"]["state"] == "delayed"
    assert r["is_delayed"] is True
    on_time = _item(pid, {"CNC": (D(-1), D(-1))})
    assert _row(c, pid, on_time)["stages"]["CNC"]["state"] == "done"
    installed = _item(pid, {"CNC": (D(-4), D(-2)), "INST": (D(-2), D(-1))})
    r = _row(c, pid, installed)
    assert r["stages"]["CNC"]["state"] == "delayed"          # the record of lateness stays on the stage
    assert r["is_delayed"] is False                          # but a finished job leaves the Delayed list


def test_all_projects_lists_read_the_same_definition(world):
    c, wid, pid = world
    a = _item(pid, _done_through("DOWN") | {"CNC": (D(1), None), "EDGED": (D(2), None)})        # at risk
    b = _item(pid, {"CNC": (D(-3), D(-1))})                                                      # delayed
    o = _item(pid, {"CNC": (D(-1), None)})                                                       # overdue
    assert [r["id"] for r in c.get("/tracking/items", params={"filter": "at_risk"}).json()["items"]] == [a]
    assert [r["id"] for r in c.get("/tracking/items", params={"filter": "delayed"}).json()["items"]] == [b]
    assert [r["id"] for r in c.get("/tracking/items", params={"filter": "overdue"}).json()["items"]] == [o]
    assert c.get("/tracking/items", params={"filter": "soon"}).status_code == 422
