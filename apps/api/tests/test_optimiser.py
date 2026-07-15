"""Tests for the CutPlan optimiser stub (sub-project #9).

Two layers:
  * pure-function packing unit tests (no DB) against `pack_naive`, and
  * route tests for POST /projects/{pid}/optimise — non-mutating,
    workspace-isolated, RBAC-gated, and proposal round-trips into the
    existing create-plan endpoint.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.cut_floor.optimiser import PackPart, pack_naive
from app.db import SessionLocal
from app.main import app

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        extra = ("cut_schedule", "part_slot", "cut_sheet", "cut_plan")
        all_tables = ", ".join(list(extra) + list(TRUNCATE_TABLES))
        s.execute(text(f"TRUNCATE {all_tables} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Pure-function unit tests (no DB)
# ---------------------------------------------------------------------------

def _no_overlap(placed) -> bool:
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            separated = (
                a.x + a.w <= b.x or b.x + b.w <= a.x
                or a.y + a.h <= b.y or b.y + b.h <= a.y
            )
            if not separated:
                return False
    return True


def test_pack_single_part_fits():
    r = pack_naive([PackPart(720, 580, "P1", 1)], 2440, 1220, kerf=3)
    assert len(r.placed) == 1
    assert not r.skipped
    assert (r.placed[0].x, r.placed[0].y) == (0, 0)
    assert 0 < r.utilization_pct < 1


def test_pack_grid_no_overlap():
    parts = [PackPart(600, 400, f"P{i}", i) for i in range(8)]
    r = pack_naive(parts, 2440, 1220, kerf=3)
    assert len(r.placed) == 8
    assert not r.skipped
    assert _no_overlap(r.placed)


def test_pack_rotates_when_allowed():
    # 1200x300 only fits a 1000-wide sheet when rotated to 300x1200.
    r = pack_naive(
        [PackPart(1200, 300, "wide", 1, allow_rotation=True)],
        1000, 2000, kerf=3,
    )
    assert len(r.placed) == 1
    assert (r.placed[0].w, r.placed[0].h) == (300, 1200)


def test_pack_grain_locked_not_rotated():
    r = pack_naive(
        [PackPart(1200, 300, "wide", 1, allow_rotation=False)],
        1000, 2000, kerf=3,
    )
    assert not r.placed
    assert len(r.skipped) == 1
    assert r.skipped[0].reason == "too_large"


def test_pack_skips_oversized():
    r = pack_naive([PackPart(5000, 5000, "huge", 9)], 2440, 1220)
    assert not r.placed
    assert r.skipped[0].reason == "too_large"


def test_pack_overflow_is_no_room():
    parts = [PackPart(2400, 1200, "fills", 1), PackPart(2400, 1200, "second", 2)]
    r = pack_naive(parts, 2440, 1220, kerf=3)
    assert len(r.placed) == 1
    assert len(r.skipped) == 1
    assert r.skipped[0].reason == "no_room"


def test_pack_kerf_spacing():
    r = pack_naive(
        [PackPart(500, 400, "a", 1), PackPart(500, 400, "b", 2)],
        2440, 1220, kerf=10,
    )
    # second part starts one kerf past the first (500 + 10).
    assert sorted(s.x for s in r.placed) == [0.0, 510.0]


def test_pack_empty_input():
    r = pack_naive([], 2440, 1220)
    assert not r.placed and not r.skipped
    assert r.utilization_pct == 0.0


# ---------------------------------------------------------------------------
# Route tests (DB)
# ---------------------------------------------------------------------------

def _setup(role: str = "drafter"):
    """Fresh workspace + user + project + item + module. Returns
    (client, wid, uid, pid, iid, mid, slug, email)."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"r-{suffix}"
    email = f"u-{suffix}@example.com"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'R') RETURNING id"),
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
            {"pc": f"P-{suffix}", "pn": f"Project {suffix}", "w": wid, "u": uid},
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
        s.commit()
    finally:
        s.close()

    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, wid, uid, pid, iid, mid, slug, email


def _add_board(wid: int, grain_locked: bool) -> int:
    s = SessionLocal()
    try:
        mid = s.execute(
            text(
                """
                INSERT INTO board_materials(code, sku, description, workspace_id,
                                            grain_locked)
                VALUES (:code, :sku, 'Board', :w, :gl) RETURNING material_id
                """
            ),
            {
                "code": f"BM-{uuid.uuid4().hex[:8]}",
                "sku": f"SKU-{uuid.uuid4().hex[:6]}",
                "w": wid,
                "gl": grain_locked,
            },
        ).scalar()
        s.commit()
        return mid
    finally:
        s.close()


def _add_part(mid: int, len_mm, wid_mm, qty=1, board_material_id=None):
    s = SessionLocal()
    try:
        s.execute(
            text(
                """
                INSERT INTO parts(module_id, seq, qty, part_name, len_mm, wid_mm,
                                  board_material_id)
                VALUES (:m, 1, :q, 'Part', :l, :wd, :bm)
                """
            ),
            {"m": mid, "q": qty, "l": len_mm, "wd": wid_mm, "bm": board_material_id},
        )
        s.commit()
    finally:
        s.close()


def _body(**over):
    base = {
        "name": "Nest A",
        "material_sku": "18-PB",
        "sheet_len_mm": 2440,
        "sheet_wid_mm": 1220,
        "kerf_mm": 3,
    }
    base.update(over)
    return base


def test_optimise_returns_proposal_and_summary():
    c, _wid, _uid, pid, _iid, mid, *_ = _setup("drafter")
    _add_part(mid, 720, 580, qty=3)
    r = c.post(f"/projects/{pid}/optimise", json=_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposal"]["sheets"][0]["material_sku"] == "18-PB"
    assert body["summary"]["total_parts"] == 3
    assert body["summary"]["placed"] == 3
    assert body["summary"]["sheets_used"] == 1
    assert len(body["proposal"]["sheets"][0]["slots"]) == 3


def test_optimise_empty_project_zero_placed():
    c, _wid, _uid, pid, *_ = _setup("drafter")
    r = c.post(f"/projects/{pid}/optimise", json=_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["total_parts"] == 0
    assert body["summary"]["placed"] == 0
    assert body["summary"]["sheets_used"] == 0
    assert body["proposal"]["sheets"][0]["slots"] == []


def test_optimise_grain_locked_part_not_rotated():
    c, wid, _uid, pid, _iid, mid, *_ = _setup("drafter")
    locked = _add_board(wid, grain_locked=True)
    _add_part(mid, 1200, 300, qty=1, board_material_id=locked)
    # narrow sheet: 1200-long part only fits if rotated, which lock forbids.
    r = c.post(f"/projects/{pid}/optimise", json=_body(sheet_len_mm=1000, sheet_wid_mm=2000))
    assert r.status_code == 200, r.text
    summary = r.json()["summary"]
    assert summary["placed"] == 0
    assert summary["skipped"] == 1
    assert summary["skipped_reasons"][0]["reason"] == "too_large"


def test_optimise_unlocked_part_rotates_and_places():
    c, wid, _uid, pid, _iid, mid, *_ = _setup("drafter")
    free = _add_board(wid, grain_locked=False)
    _add_part(mid, 1200, 300, qty=1, board_material_id=free)
    r = c.post(f"/projects/{pid}/optimise", json=_body(sheet_len_mm=1000, sheet_wid_mm=2000))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["placed"] == 1
    slot = body["proposal"]["sheets"][0]["slots"][0]
    assert (slot["w"], slot["h"]) == (300, 1200)  # rotated


def test_optimise_does_not_write_audit():
    c, wid, _uid, pid, _iid, mid, *_ = _setup("drafter")
    _add_part(mid, 720, 580, qty=2)
    r = c.post(f"/projects/{pid}/optimise", json=_body())
    assert r.status_code == 200, r.text
    s = SessionLocal()
    try:
        n = s.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE workspace_id = :w AND event LIKE 'cut%'"
            ),
            {"w": wid},
        ).scalar()
    finally:
        s.close()
    assert n == 0


def test_optimise_viewer_forbidden():
    c, _wid, _uid, pid, *_ = _setup("viewer")
    r = c.post(f"/projects/{pid}/optimise", json=_body())
    assert r.status_code == 403, r.text


def test_optimise_cross_workspace_404():
    c_a, _wa, _ua, _pa, *_ = _setup("drafter")
    _c_b, _wb, _ub, pid_b, *_ = _setup("drafter")
    # client A (workspace A) targets project in workspace B.
    r = c_a.post(f"/projects/{pid_b}/optimise", json=_body())
    assert r.status_code == 404, r.text


def test_optimise_proposal_round_trips_into_create_plan():
    c, _wid, _uid, pid, _iid, mid, *_ = _setup("drafter")
    _add_part(mid, 720, 580, qty=4)
    r = c.post(f"/projects/{pid}/optimise", json=_body())
    assert r.status_code == 200, r.text
    proposal = r.json()["proposal"]

    # "Save as plan" forwards the identical proposal to the existing endpoint.
    r2 = c.post(f"/projects/{pid}/cut-plans", json=proposal)
    assert r2.status_code == 201, r2.text
    plan = r2.json()
    assert plan["name"] == "Nest A"
    assert len(plan["sheets"]) == 1
    assert len(plan["sheets"][0]["slots"]) == 4
