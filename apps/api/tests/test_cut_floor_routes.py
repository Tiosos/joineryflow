"""Tests for cut_floor routes (sub-project #7c).

Covers CutPlan create/get/list/delete + CutSchedule create/list/patch/
reorder/cancel + RBAC + workspace isolation.
"""
import uuid
from datetime import date, timedelta

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
        extra = (
            "cut_schedule",
            "part_slot",
            "cut_sheet",
            "cut_plan",
        )
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(
            text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE")
        )
        s.commit()
    finally:
        s.close()


def _login(role: str = "drafter"):
    """Create a fresh workspace + user + project + 1 item with 1 module + 2 parts.

    Returns (client, wid, uid, pid, iid, [part_id_1, part_id_2]).
    """
    suffix = uuid.uuid4().hex[:8]
    slug = f"r-{suffix}"
    email = f"u-{suffix}@example.com"
    s = SessionLocal()
    try:
        wid = s.execute(
            text(
                "INSERT INTO workspace(slug, name) VALUES(:s, 'R') RETURNING id"
            ),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name,
                                     password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r) RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
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
        iid = s.execute(
            text(
                """
                INSERT INTO items(num, project_id, description)
                VALUES (:n, :p, 'Item 1') RETURNING item_id
                """
            ),
            {"n": wid * 1000 + 1, "p": pid},
        ).scalar()
        mid = s.execute(
            text(
                """
                INSERT INTO modules(item_id, module_no, name)
                VALUES (:i, '1', 'M1') RETURNING module_id
                """
            ),
            {"i": iid},
        ).scalar()
        part_ids = []
        for i in range(2):
            pid_ = s.execute(
                text(
                    """
                    INSERT INTO parts(module_id, seq, qty, part_name, len_mm, wid_mm)
                    VALUES (:m, :seq, 1, :pn, 720, 580) RETURNING part_id
                    """
                ),
                {"m": mid, "seq": i + 1, "pn": f"Part {i + 1}"},
            ).scalar()
            part_ids.append(pid_)
        s.commit()
    finally:
        s.close()

    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid, pid, iid, part_ids


def _make_cut_plan(c: TestClient, pid: int, part_ids: list[int]) -> dict:
    body = {
        "name": "Plan A",
        "notes": "first nest",
        "sheets": [{
            "sheet_no": 1,
            "material_sku": "18-PB",
            "slots": [
                {"x": 10, "y": 10, "w": 720, "h": 580,
                 "label": "P1", "part_id": part_ids[0]},
                {"x": 750, "y": 10, "w": 720, "h": 580,
                 "label": "P2", "part_id": part_ids[1]},
                {"x": 10, "y": 620, "w": 400, "h": 200,
                 "label": "Foreign", "part_id": None},
            ],
        }],
    }
    r = c.post(f"/projects/{pid}/cut-plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- CutPlan ---------------------------------------------------------------

def test_create_cut_plan_persists_sheets_and_slots():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    assert plan["name"] == "Plan A"
    assert len(plan["sheets"]) == 1
    assert len(plan["sheets"][0]["slots"]) == 3


def test_list_cut_plans_returns_summary():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    _make_cut_plan(c, pid, parts)
    r = c.get(f"/projects/{pid}/cut-plans")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["sheet_count"] == 1
    assert body[0]["slot_count"] == 3


def test_get_item_cut_plan_marks_foreign_slots():
    c, _wid, _uid, pid, iid, parts = _login("drafter")
    _make_cut_plan(c, pid, parts)
    r = c.get(f"/items/{iid}/cut-plan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan"] is not None
    assert len(body["sheets"]) == 1
    slots = body["sheets"][0]["slots"]
    foreign = [s for s in slots if s["is_foreign"]]
    own = [s for s in slots if not s["is_foreign"]]
    assert len(own) == 2
    assert len(foreign) == 1


def test_get_item_cut_plan_empty_when_no_plan():
    c, _wid, _uid, _pid, iid, _parts = _login("drafter")
    r = c.get(f"/items/{iid}/cut-plan")
    assert r.status_code == 200
    assert r.json()["plan"] is None


def test_delete_cut_plan_blocks_when_active_schedule_exists():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    r = c.post(
        "/cut-schedules",
        json={"cut_plan_id": plan["id"], "scheduled_for": today},
    )
    assert r.status_code == 201, r.text

    r = c.delete(f"/cut-plans/{plan['id']}")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "PLAN_HAS_SCHEDULES"


def test_delete_cut_plan_succeeds_when_only_cancelled_schedules():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    sid = c.post(
        "/cut-schedules",
        json={"cut_plan_id": plan["id"], "scheduled_for": today},
    ).json()["id"]
    cancel = c.delete(f"/cut-schedules/{sid}")
    assert cancel.status_code == 200, cancel.text
    r = c.delete(f"/cut-plans/{plan['id']}")
    assert r.status_code == 204


# --- CutSchedule -----------------------------------------------------------

def test_schedule_auto_priority():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    a = c.post(
        "/cut-schedules",
        json={"cut_plan_id": plan["id"], "scheduled_for": today},
    ).json()
    b = c.post(
        "/cut-schedules",
        json={"cut_plan_id": plan["id"], "scheduled_for": today},
    ).json()
    assert a["priority"] == 100
    assert b["priority"] == 200


def test_schedule_status_transitions():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    sid = c.post(
        "/cut-schedules",
        json={"cut_plan_id": plan["id"], "scheduled_for": today},
    ).json()["id"]

    r = c.patch(f"/cut-schedules/{sid}", json={"status": "running"})
    assert r.status_code == 200
    r = c.patch(f"/cut-schedules/{sid}", json={"status": "done"})
    assert r.status_code == 200
    r = c.patch(f"/cut-schedules/{sid}", json={"status": "running"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "BAD_TRANSITION"


def test_schedule_planned_to_cancelled_via_delete():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    sid = c.post(
        "/cut-schedules",
        json={"cut_plan_id": plan["id"], "scheduled_for": today},
    ).json()["id"]
    r = c.delete(f"/cut-schedules/{sid}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    r2 = c.delete(f"/cut-schedules/{sid}")
    assert r2.status_code == 409


def test_schedule_reorder_writes_dense_priorities():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    a = c.post("/cut-schedules", json={"cut_plan_id": plan["id"],
                                        "scheduled_for": today}).json()
    b = c.post("/cut-schedules", json={"cut_plan_id": plan["id"],
                                        "scheduled_for": today}).json()
    cc = c.post("/cut-schedules", json={"cut_plan_id": plan["id"],
                                         "scheduled_for": today}).json()

    r = c.post(
        "/cut-schedules/reorder",
        json={"scheduled_for": today,
              "ordered_ids": [cc["id"], a["id"], b["id"]]},
    )
    assert r.status_code == 200
    rows = r.json()
    pri_by_id = {row["id"]: row["priority"] for row in rows}
    assert pri_by_id[cc["id"]] == 100
    assert pri_by_id[a["id"]] == 200
    assert pri_by_id[b["id"]] == 300


def test_list_schedules_filters_by_date():
    c, _wid, _uid, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c, pid, parts)
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    c.post("/cut-schedules", json={"cut_plan_id": plan["id"],
                                    "scheduled_for": today})
    c.post("/cut-schedules", json={"cut_plan_id": plan["id"],
                                    "scheduled_for": tomorrow})
    r = c.get(f"/cut-schedules?date={today}")
    assert r.status_code == 200
    assert len(r.json()) == 1


# --- RBAC / workspace ------------------------------------------------------

def test_viewer_cannot_create_cut_plan():
    c, _wid, _uid, pid, _iid, parts = _login("viewer")
    body = {"name": "x", "sheets": []}
    r = c.post(f"/projects/{pid}/cut-plans", json=body)
    assert r.status_code == 403


def test_purchase_officer_cannot_create_schedule():
    c, _wid, _uid, pid, _iid, parts = _login("purchase_officer")
    body = {"cut_plan_id": 9999, "scheduled_for": date.today().isoformat()}
    r = c.post("/cut-schedules", json=body)
    assert r.status_code == 403


def test_cross_workspace_get_returns_404():
    c1, _wid1, _uid1, pid, _iid, parts = _login("drafter")
    plan = _make_cut_plan(c1, pid, parts)
    c2, _wid2, _uid2, _pid2, _iid2, _parts2 = _login("drafter")
    r = c2.get(f"/cut-plans/{plan['id']}")
    assert r.status_code == 404
