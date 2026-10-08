"""Tests for the labour-apportionment half of the actual-costs rollup
(Q549) — a cutlist's stage completion is shared work, split across its
linked items by each item's share of total part area."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app
from .helpers import log_in



pytestmark = pytest.mark.usefixtures("truncate_after")


def _login():
    suffix = uuid.uuid4().hex[:8]
    slug = f"ac-{suffix}"
    email = f"u-{suffix}@t"
    s = SessionLocal()
    try:
        wid = s.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'T') RETURNING id"),
            {"s": slug},
        ).scalar()
        uid = s.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, 'manager') RETURNING id
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw")},
        ).scalar()
        for sk, label, sort in (("CNC", "CNC", 50),):
            s.execute(
                text(
                    "INSERT INTO stages(stage_key, label, sort_order) "
                    "VALUES (:k, :l, :o) ON CONFLICT DO NOTHING"
                ),
                {"k": sk, "l": label, "o": sort},
            )
        s.execute(
            text(
                "INSERT INTO workspace_labour_rate(workspace_id, stage_key, hourly_rate) "
                "VALUES (:w, 'CNC', 100.00)"
            ),
            {"w": wid},
        )
        pid = s.execute(
            text(
                "INSERT INTO projects(project_code, name, workspace_id, created_by) "
                "VALUES ('P1','P1',:w,:cb) RETURNING project_id"
            ),
            {"w": wid, "cb": str(uid)},
        ).scalar()
        cutlist_id = s.execute(
            text(
                "INSERT INTO cutlist(project_id, cutlist_no, created_by) "
                "VALUES (:p, 900001, :u) RETURNING cutlist_id"
            ),
            {"p": pid, "u": uid},
        ).scalar()

        def _make_item(area_len: int | None, area_wid: int | None) -> int:
            item_id = s.execute(
                text(
                    """
                    INSERT INTO items(num, project_id, cutlist_id, description, qty)
                    VALUES (nextval('joinery_number_seq'), :p, :cl, 'Item', 1)
                    RETURNING item_id
                    """
                ),
                {"p": pid, "cl": cutlist_id},
            ).scalar()
            if area_len is not None:
                module_id = s.execute(
                    text(
                        "INSERT INTO modules(item_id, module_no, name) "
                        "VALUES (:i, '1', 'M1') RETURNING module_id"
                    ),
                    {"i": item_id},
                ).scalar()
                s.execute(
                    text(
                        """
                        INSERT INTO parts(module_id, seq, qty, part_name, len_mm, wid_mm)
                        VALUES (:m, 1, 1, 'Part', :l, :w)
                        """
                    ),
                    {"m": module_id, "l": area_len, "w": area_wid},
                )
            return item_id

        item_big = _make_item(2000, 1000)    # area 2,000,000 -> 2/3 share
        item_small = _make_item(1000, 1000)  # area 1,000,000 -> 1/3 share

        assignment_id = s.execute(
            text(
                """
                INSERT INTO worker_assignment(
                    cutlist_id, stage_key, worker_id, status, assigned_by, started_at
                ) VALUES (:cl, 'CNC', :u, 'done', :u, :st)
                RETURNING assignment_id
                """
            ),
            {"cl": cutlist_id, "u": uid, "st": datetime.now(timezone.utc) - timedelta(hours=2)},
        ).scalar()
        s.execute(
            text(
                """
                INSERT INTO stage_completion_log(
                    cutlist_id, stage_key, assignment_id, worker_id, completed_at
                ) VALUES (:cl, 'CNC', :a, :u, :now)
                """
            ),
            {"cl": cutlist_id, "a": assignment_id, "u": uid, "now": datetime.now(timezone.utc)},
        )
        s.commit()
        result = {
            "wid": wid, "pid": pid, "cutlist_id": cutlist_id,
            "item_big": item_big, "item_small": item_small,
        }
    finally:
        s.close()
    c = TestClient(app)
    log_in(slug, email, client=c)
    return c, result


def test_labour_apportioned_by_part_area_share():
    c, ids = _login()
    r = c.get(f"/projects/{ids['pid']}/actual-costs")
    assert r.status_code == 200, r.text
    body = r.json()
    # 2 hours * $100/h = $200 total, split 2:1 by area between big and small.
    assert float(body["labour_actual"]) == pytest.approx(200.00, abs=0.01)
    by_item = {int(k): float(v) for k, v in body["labour_by_item"].items()}
    assert by_item[ids["item_big"]] == pytest.approx(133.33, abs=0.01)
    assert by_item[ids["item_small"]] == pytest.approx(66.67, abs=0.01)
    assert by_item[ids["item_big"]] + by_item[ids["item_small"]] == pytest.approx(200.00, abs=0.01)


def test_materials_actual_excludes_cancelled_batch():
    c, ids = _login()
    s = SessionLocal()
    try:
        s.execute(
            text(
                """
                INSERT INTO procurement_batches(
                    project_id, material_type, material_id, qty_received, cost_per_unit
                ) VALUES (:p, 'BOARD', 1, 10, 50.00)
                """
            ),
            {"p": ids["pid"]},
        )
        s.execute(
            text(
                """
                INSERT INTO procurement_batches(
                    project_id, material_type, material_id, qty_received, cost_per_unit, cancelled_at
                ) VALUES (:p, 'BOARD', 2, 10, 999.00, now())
                """
            ),
            {"p": ids["pid"]},
        )
        s.commit()
    finally:
        s.close()

    r = c.get(f"/projects/{ids['pid']}/actual-costs")
    assert r.status_code == 200, r.text
    # 10 * $50 = $500 from the live batch; the cancelled batch's 10 * $999
    # must not be added on top.
    assert float(r.json()["materials_actual"]) == pytest.approx(500.00, abs=0.01)


# --- soft-deleted items (migration 0052) -----------------------------------
# Labour is priced from the cutlist's stage completions, which a delete keeps: hours already
# worked stay costed. Only the per-item split follows the live items.

def test_deleting_an_item_does_not_lower_the_project_labour_total():
    c, ids = _login()
    before = c.get(f"/projects/{ids['pid']}/actual-costs").json()
    assert c.delete(f"/items/{ids['item_big']}").status_code == 204
    after = c.get(f"/projects/{ids['pid']}/actual-costs").json()
    assert after["labour_actual"] == before["labour_actual"] == "200.00"
    assert after["total_actual"] == before["total_actual"]


def test_a_deleted_item_drops_out_of_the_per_item_split_and_its_share_goes_to_the_live_items():
    c, ids = _login()
    assert c.delete(f"/items/{ids['item_big']}").status_code == 204
    split = c.get(f"/projects/{ids['pid']}/actual-costs").json()["labour_by_item"]
    assert str(ids["item_big"]) not in split
    assert split[str(ids["item_small"])] == "200.00"          # the whole cutlist's labour: nothing is lost


def test_deleting_every_item_keeps_the_labour_in_the_total_with_no_per_item_split():
    c, ids = _login()
    for key in ("item_big", "item_small"):
        assert c.delete(f"/items/{ids[key]}").status_code == 204
    body = c.get(f"/projects/{ids['pid']}/actual-costs").json()
    assert body["labour_actual"] == "200.00"
    assert body["labour_by_item"] == {}


def test_restoring_the_item_restores_its_share():
    c, ids = _login()
    assert c.delete(f"/items/{ids['item_big']}").status_code == 204
    assert c.post(f"/items/{ids['item_big']}/restore").status_code == 204
    split = c.get(f"/projects/{ids['pid']}/actual-costs").json()["labour_by_item"]
    assert split[str(ids["item_big"])] == "133.33" and split[str(ids["item_small"])] == "66.67"
