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

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


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
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"})
    assert r.status_code == 200, r.text
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
