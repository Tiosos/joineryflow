"""Integration tests for shop_floor routes (sub-project #8).

Covers assign / patch / cancel / start / complete / undo + board /
station / RBAC + workspace isolation.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

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
        s.execute(
            text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


def _bootstrap(role: str = "editor", *, with_worker: bool = True):
    """Create workspace + foreman user + 1 worker + project + 2 items
    with item_stages REQ..MADE. Return (client, wid, uid, worker_id,
    pid, item_ids)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"sf-{suffix}"
    email = f"foreman-{suffix}@example.com"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'SF') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, :e, 'Foreman', :p, :r) RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        ).scalar()
        worker_id = None
        if with_worker:
            worker_id = s.execute(
                text(
                    """
                    INSERT INTO app_user(workspace_id, email, full_name,
                                         password_hash, auth_role,
                                         is_shop_worker)
                    VALUES (:w, :e, 'Sam Lee', :p, 'editor', true)
                    RETURNING id
                    """
                ),
                {"w": wid, "e": f"sam-{suffix}@example.com",
                 "p": hash_password("pw")},
            ).scalar()
        pid = s.execute(
            text(
                """
                INSERT INTO projects(project_code, name, pm_id, workspace_id)
                VALUES (:pc, :pn, :u, :w) RETURNING project_id
                """
            ),
            {"pc": f"P-{suffix}", "pn": f"Project {suffix}",
             "w": wid, "u": uid},
        ).scalar()
        item_ids = []
        for i in range(2):
            iid = s.execute(
                text(
                    """
                    INSERT INTO items(num, project_id, code, description,
                                      painting_req, paint_after_assembly,
                                      deleted)
                    VALUES (:n, :p, :c, :d, true, false, false)
                    RETURNING item_id
                    """
                ),
                {"n": wid * 1000 + i + 1, "p": pid,
                 "c": f"ITEM-{i + 1}", "d": f"Demo {i + 1}"},
            ).scalar()
            item_ids.append(iid)
            for stage in ("DOWN", "CNC", "EDGED", "PAINTED", "MADE"):
                s.execute(
                    text(
                        """
                        INSERT INTO item_stages(item_id, stage_key)
                        VALUES (:iid, :sk)
                        ON CONFLICT (item_id, stage_key) DO NOTHING
                        """
                    ),
                    {"iid": iid, "sk": stage},
                )
        s.commit()
    finally:
        s.close()

    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid, worker_id, pid, item_ids


def _assign(c: TestClient, pid: int, iid: int, stage: str, worker_id: int) -> dict:
    r = c.post(
        f"/projects/{pid}/items/{iid}/assignments",
        json={"stage_key": stage, "worker_id": worker_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- Assign / patch / cancel ----------------------------------------------

def test_create_assignment_returns_201():
    c, _w, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "DOWN", worker)
    assert a["status"] == "assigned"
    assert a["worker_id"] == worker


def test_duplicate_active_assignment_returns_409_with_existing_id():
    c, _w, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "DOWN", worker)
    r = c.post(
        f"/projects/{pid}/items/{items[0]}/assignments",
        json={"stage_key": "DOWN", "worker_id": worker},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "ACTIVE_ASSIGNMENT_EXISTS"
    assert detail["assignment_id"] == a["assignment_id"]
    assert detail["worker_id"] == worker


def test_reassign_clears_started_at_and_resets_status():
    c, wid, _u, worker, pid, items = _bootstrap()
    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        worker2 = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role,
                                     is_shop_worker)
                VALUES (:w, :e, 'Worker 2', :p, 'editor', true)
                RETURNING id
                """
            ),
            {"w": wid, "e": f"w2-{suffix}@example.com",
             "p": hash_password("pw")},
        ).scalar()
        s.commit()
    finally:
        s.close()

    a = _assign(c, pid, items[0], "DOWN", worker)
    c.post(f"/assignments/{a['assignment_id']}/start")
    after_start = c.get(f"/projects/{pid}/shop-floor/board").json()
    cell = next(
        cd for col in after_start["columns"].values() for cd in col
        if cd["item_id"] == items[0]
    )
    assert cell["assignment"]["status"] == "in_progress"
    assert cell["assignment"]["started_at"] is not None

    r = c.patch(
        f"/assignments/{a['assignment_id']}", json={"worker_id": worker2}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["worker_id"] == worker2
    assert body["status"] == "assigned"
    assert body["started_at"] is None


def test_cancel_assignment_via_delete():
    c, _w, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "DOWN", worker)
    r = c.delete(f"/assignments/{a['assignment_id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    r2 = c.delete(f"/assignments/{a['assignment_id']}")
    assert r2.status_code == 409


def test_assign_nonworker_returns_422():
    c, wid, _u, _worker, pid, items = _bootstrap(with_worker=False)
    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        non_worker = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role,
                                     is_shop_worker)
                VALUES (:w, :e, 'Plain editor', :p, 'editor', false)
                RETURNING id
                """
            ),
            {"w": wid, "e": f"nw-{suffix}@example.com",
             "p": hash_password("pw")},
        ).scalar()
        s.commit()
    finally:
        s.close()
    r = c.post(
        f"/projects/{pid}/items/{items[0]}/assignments",
        json={"stage_key": "DOWN", "worker_id": non_worker},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NOT_A_SHOP_WORKER"


# --- Start / complete / lifecycle -----------------------------------------

def test_start_then_complete_writes_completion_log_and_done_date():
    c, wid, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "DOWN", worker)
    c.post(f"/assignments/{a['assignment_id']}/start")
    r = c.post(
        f"/assignments/{a['assignment_id']}/complete",
        json={"note": "all good"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["log_id"] > 0

    s = SessionLocal()
    try:
        log_count = s.execute(
            text("SELECT COUNT(*) FROM stage_completion_log WHERE assignment_id = :a"),
            {"a": a["assignment_id"]},
        ).scalar()
        assert log_count == 1
        done_date = s.execute(
            text(
                """
                SELECT done_date FROM item_stages
                WHERE item_id = :iid AND stage_key = 'DOWN'
                """
            ),
            {"iid": items[0]},
        ).scalar()
        assert done_date is not None
    finally:
        s.close()


def test_complete_out_of_order_returns_409_with_missing_priors():
    c, _w, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "CNC", worker)
    c.post(f"/assignments/{a['assignment_id']}/start")
    r = c.post(
        f"/assignments/{a['assignment_id']}/complete", json={}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "STAGE_OUT_OF_ORDER"
    assert "DOWN" in r.json()["detail"]["missing"]


def test_undo_for_supervisor_clears_done_date():
    c, _w, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "DOWN", worker)
    c.post(f"/assignments/{a['assignment_id']}/start")
    completion = c.post(
        f"/assignments/{a['assignment_id']}/complete", json={}
    ).json()
    log_id = completion["log_id"]

    # Foreman (editor role under test) is supervisor — can always undo.
    r = c.post(f"/completions/{log_id}/undo")
    assert r.status_code == 200, r.text

    s = SessionLocal()
    try:
        done_date = s.execute(
            text("SELECT done_date FROM item_stages WHERE item_id = :i AND stage_key = 'DOWN'"),
            {"i": items[0]},
        ).scalar()
        assert done_date is None
        undone_at = s.execute(
            text("SELECT undone_at FROM stage_completion_log WHERE log_id = :l"),
            {"l": log_id},
        ).scalar()
        assert undone_at is not None
    finally:
        s.close()


# --- Board + station ------------------------------------------------------

def test_board_groups_items_into_stage_columns():
    c, _w, _u, worker, pid, items = _bootstrap()
    _assign(c, pid, items[0], "DOWN", worker)
    r = c.get(f"/projects/{pid}/shop-floor/board")
    assert r.status_code == 200
    body = r.json()
    assert set(body["columns"].keys()) == {"DOWN", "CNC", "EDGED", "PAINTED", "MADE"}
    down_items = [c["item_id"] for c in body["columns"]["DOWN"]]
    assert items[0] in down_items


def test_station_queue_orders_in_progress_first():
    c, _w, _u, worker, pid, items = _bootstrap()
    a1 = _assign(c, pid, items[0], "DOWN", worker)
    a2 = _assign(c, pid, items[1], "DOWN", worker)
    c.post(f"/assignments/{a2['assignment_id']}/start")

    r = c.get(f"/workers/{worker}/queue")
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert cards[0]["assignment_id"] == a2["assignment_id"]
    assert cards[0]["status"] == "in_progress"
    assert cards[1]["assignment_id"] == a1["assignment_id"]


# --- RBAC + workspace iso -------------------------------------------------

def test_viewer_cannot_assign():
    c, _w, _u, worker, pid, items = _bootstrap(role="viewer", with_worker=True)
    r = c.post(
        f"/projects/{pid}/items/{items[0]}/assignments",
        json={"stage_key": "DOWN", "worker_id": worker},
    )
    assert r.status_code == 403


def test_cross_workspace_get_returns_404():
    c1, _w1, _u1, worker, pid, items = _bootstrap()
    a = _assign(c1, pid, items[0], "DOWN", worker)
    c2, _w2, _u2, _w2_worker, _pid2, _items2 = _bootstrap()
    r = c2.get(f"/projects/{pid}/shop-floor/board")
    assert r.status_code == 404
    r2 = c2.patch(
        f"/assignments/{a['assignment_id']}", json={"note": "x"}
    )
    assert r2.status_code == 404


# --- Worker toggle (admin /it surface) ------------------------------------

def test_admin_can_toggle_is_shop_worker():
    c, wid, _u, _worker, _pid, _items = _bootstrap(role="admin")
    suffix = uuid.uuid4().hex[:8]
    s = SessionLocal()
    try:
        target = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, :e, 'Promote Me', :p, 'editor')
                RETURNING id
                """
            ),
            {"w": wid, "e": f"target-{suffix}@example.com",
             "p": hash_password("pw")},
        ).scalar()
        s.commit()
    finally:
        s.close()
    r = c.patch(
        f"/users/{target}/shop-worker", json={"is_shop_worker": True}
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_shop_worker"] is True


def test_non_admin_cannot_toggle():
    c, _w, _u, worker, _pid, _items = _bootstrap(role="editor")
    r = c.patch(
        f"/users/{worker}/shop-worker", json={"is_shop_worker": False}
    )
    assert r.status_code == 403


# --- Board: items missing item_stages rows (regression) -------------------
#
# create_item inserts ZERO item_stages rows, and the seed inserts only
# REQ..CNC. The board must derive the next open stage from the canonical
# lifecycle order — treating a missing row as open, exactly as
# next_open_stage() does — not only from item_stages rows that happen to
# exist. Otherwise items silently drop off the Foreman board and can never
# be assigned the later stages. The _bootstrap fixture masks this by
# pre-inserting all five rows.

def _add_item(
    wid: int,
    pid: int,
    *,
    code: str,
    stages: dict[str, bool],
    painting_req: bool = True,
    paint_after_assembly: bool = False,
) -> int:
    """Insert an item carrying ONLY the item_stages rows named in `stages`
    (stage_key -> done?). Stages omitted from the dict get no row at all,
    mirroring create_item (none) and the seed (REQ..CNC only)."""
    s = SessionLocal()
    try:
        iid = s.execute(
            text(
                """
                INSERT INTO items(num, project_id, code, description,
                                  painting_req, paint_after_assembly, deleted)
                VALUES (nextval('items_item_id_seq') + 100000, :p, :c, :d,
                        :pr, :paa, false)
                RETURNING item_id
                """
            ),
            {"p": pid, "c": code, "d": code,
             "pr": painting_req, "paa": paint_after_assembly},
        ).scalar()
        for sk, done in stages.items():
            s.execute(
                text(
                    """
                    INSERT INTO item_stages(item_id, stage_key, done_date)
                    VALUES (:i, :s, :d)
                    """
                ),
                {"i": iid, "s": sk, "d": date.today() if done else None},
            )
        s.commit()
        return iid
    finally:
        s.close()


def _board_column(c: TestClient, pid: int, stage: str) -> list[int]:
    r = c.get(f"/projects/{pid}/shop-floor/board")
    assert r.status_code == 200, r.text
    return [card["item_id"] for card in r.json()["columns"][stage]]


def test_board_includes_item_with_no_stage_rows():
    """A UI-created item (zero item_stages rows) must show at DOWN, not vanish."""
    c, wid, _u, _worker, pid, _items = _bootstrap()
    iid = _add_item(wid, pid, code="NOSTAGES", stages={})
    assert iid in _board_column(c, pid, "DOWN")


def test_board_advances_to_stage_without_a_row():
    """DOWN+CNC done, no EDGED/PAINTED/MADE rows (the seed's shape): next
    open stage is EDGED — the item stays on the board rather than dropping off."""
    c, wid, _u, _worker, pid, _items = _bootstrap()
    iid = _add_item(wid, pid, code="THRUCNC", stages={"DOWN": True, "CNC": True})
    assert iid in _board_column(c, pid, "EDGED")


def test_board_skips_painted_when_not_required_and_row_missing():
    """painting_req=false with DOWN..EDGED done and no PAINTED/MADE rows:
    PAINTED is skipped, next open stage is MADE."""
    c, wid, _u, _worker, pid, _items = _bootstrap()
    iid = _add_item(
        wid, pid, code="NOPAINT", painting_req=False,
        stages={"DOWN": True, "CNC": True, "EDGED": True},
    )
    assert iid in _board_column(c, pid, "MADE")


# --- Complete requires in_progress (status machine) -----------------------

def test_complete_requires_in_progress():
    """assigned -> done skips in_progress; it must 409, leave started_at NULL,
    and write no completion log."""
    c, _w, _u, worker, pid, items = _bootstrap()
    a = _assign(c, pid, items[0], "DOWN", worker)  # status 'assigned', not started
    r = c.post(f"/assignments/{a['assignment_id']}/complete", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOT_IN_PROGRESS"

    s = SessionLocal()
    try:
        row = s.execute(
            text(
                """
                SELECT status, started_at FROM worker_assignment
                WHERE assignment_id = :a
                """
            ),
            {"a": a["assignment_id"]},
        ).mappings().first()
        assert row["status"] == "assigned"
        assert row["started_at"] is None
        logs = s.execute(
            text("SELECT COUNT(*) FROM stage_completion_log WHERE assignment_id = :a"),
            {"a": a["assignment_id"]},
        ).scalar()
        assert logs == 0
    finally:
        s.close()


# --- Undo cannot strand a completed later stage ---------------------------

def _start_and_complete(c: TestClient, pid: int, iid: int, stage: str,
                        worker: int) -> dict:
    a = _assign(c, pid, iid, stage, worker)
    c.post(f"/assignments/{a['assignment_id']}/start")
    r = c.post(f"/assignments/{a['assignment_id']}/complete", json={})
    assert r.status_code == 200, r.text
    return r.json()


def test_undo_blocked_when_later_stage_done():
    """DOWN and CNC both done; undoing DOWN would leave DOWN open with CNC
    done — the out-of-order state /complete forbids. Must 409 and preserve
    DOWN's done_date."""
    c, _w, _u, worker, pid, items = _bootstrap()
    down = _start_and_complete(c, pid, items[0], "DOWN", worker)
    _start_and_complete(c, pid, items[0], "CNC", worker)

    r = c.post(f"/completions/{down['log_id']}/undo")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "LATER_STAGE_DONE"
    assert "CNC" in r.json()["detail"]["blocking"]

    s = SessionLocal()
    try:
        done_date = s.execute(
            text("SELECT done_date FROM item_stages WHERE item_id = :i AND stage_key = 'DOWN'"),
            {"i": items[0]},
        ).scalar()
        assert done_date is not None
    finally:
        s.close()


def test_undo_allowed_for_the_latest_completed_stage():
    """Undoing the most-recent stage (no later stage done) still works."""
    c, _w, _u, worker, pid, items = _bootstrap()
    _start_and_complete(c, pid, items[0], "DOWN", worker)
    cnc = _start_and_complete(c, pid, items[0], "CNC", worker)

    r = c.post(f"/completions/{cnc['log_id']}/undo")
    assert r.status_code == 200, r.text

    s = SessionLocal()
    try:
        cnc_done = s.execute(
            text("SELECT done_date FROM item_stages WHERE item_id = :i AND stage_key = 'CNC'"),
            {"i": items[0]},
        ).scalar()
        assert cnc_done is None
    finally:
        s.close()


# --- Q3: deactivate / un-flag a worker holding active assignments ----------
#
# Deactivating or un-flagging a worker who still holds assigned/in_progress
# work would strand those rows on the board, and uniq_active_assignment then
# blocks reassigning that (item, stage). Both paths 409 until the work is
# reassigned or cancelled (shop-floor spec §15 Q3, resolved as 409-reject).

def _is_active(worker_id: int) -> bool:
    s = SessionLocal()
    try:
        return s.execute(
            text("SELECT is_active FROM app_user WHERE id = :i"), {"i": worker_id}
        ).scalar()
    finally:
        s.close()


def _is_shop_worker(worker_id: int) -> bool:
    s = SessionLocal()
    try:
        return s.execute(
            text("SELECT is_shop_worker FROM app_user WHERE id = :i"), {"i": worker_id}
        ).scalar()
    finally:
        s.close()


def test_cannot_deactivate_worker_holding_active_assignment():
    c, _w, _u, worker, pid, items = _bootstrap(role="admin")
    a = _assign(c, pid, items[0], "DOWN", worker)  # status 'assigned'
    r = c.patch(f"/users/{worker}", json={"is_active": False})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "HAS_ACTIVE_ASSIGNMENTS"
    assert any(
        x["assignment_id"] == a["assignment_id"] for x in detail["assignments"]
    )
    assert _is_active(worker) is True  # unchanged


def test_cannot_unflag_worker_with_in_progress_assignment():
    c, _w, _u, worker, pid, items = _bootstrap(role="admin")
    a = _assign(c, pid, items[0], "DOWN", worker)
    c.post(f"/assignments/{a['assignment_id']}/start")  # -> in_progress
    r = c.patch(f"/users/{worker}/shop-worker", json={"is_shop_worker": False})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "HAS_ACTIVE_ASSIGNMENTS"
    assert _is_shop_worker(worker) is True  # unchanged


def test_can_deactivate_worker_after_assignment_cancelled():
    c, _w, _u, worker, pid, items = _bootstrap(role="admin")
    a = _assign(c, pid, items[0], "DOWN", worker)
    c.delete(f"/assignments/{a['assignment_id']}")  # cancelled -> not active
    r = c.patch(f"/users/{worker}", json={"is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False


def test_can_deactivate_worker_with_no_assignments():
    c, _w, _u, worker, _pid, _items = _bootstrap(role="admin")
    r = c.patch(f"/users/{worker}", json={"is_active": False})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
