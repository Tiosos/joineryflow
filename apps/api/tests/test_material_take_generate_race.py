"""Regression test for the material_take draft-exists race in generate().

generate() checked for an existing draft with a plain, unlocked SELECT, then
computed SELECT COALESCE(MAX(version), 0) + 1, then inserted a new draft —
with no lock anywhere in between. Two concurrent
POST /items/{iid}/material-take/generate calls on an item with no existing
draft could both pass the unlocked pre-check and race on
uniq_take_draft / UNIQUE(item_id, version) (migration 0034), and the
route's error handling (material_takes/routes.py::_call) catches only the
app-level NotFound/Conflict exceptions — not IntegrityError — so the loser
got a raw 500 instead of the clean 409 DRAFT_EXISTS the pre-check is meant
to give.

The fix locks the items row for the rest of the transaction before the
draft-exists check, so a concurrent generate() on the same item serializes
instead of racing.
"""
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app
from app.material_takes import queries as q

from .conftest import TRUNCATE_TABLES


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE board_inventory, board_materials, "
                       + ", ".join(TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _sql(sql, **p):
    s = SessionLocal()
    try:
        r = s.execute(text(sql), p)
        out = r.scalar() if r.returns_rows else None
        s.commit()
        return out
    finally:
        s.close()


def _bootstrap() -> dict:
    suffix = uuid.uuid4().hex[:8]
    slug = f"mtr-{suffix}"
    wid = _sql("INSERT INTO workspace(slug, name) VALUES (:s, 'MTR') RETURNING id", s=slug)
    uid = _sql(
        "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
        " VALUES (:w, :e, 'U', :p, 'drafter') RETURNING id",
        w=wid, e=f"d-{suffix}@x.test", p=hash_password("pw"),
    )
    pid = _sql(
        "INSERT INTO projects(project_code, name, workspace_id) VALUES ('MTR', :n, :w)"
        " RETURNING project_id",
        n=f"MTR {suffix}", w=wid,
    )
    iid = _sql(
        """INSERT INTO items(num, project_id, description, status)
           VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'LIVE') RETURNING item_id""",
        p=pid,
    )
    bid = _sql(
        "INSERT INTO board_materials(code, description, sku, workspace_id)"
        " VALUES (:c, '18mm MDF', :c, :w) RETURNING material_id",
        c=f"MTR-{iid}", w=wid,
    )
    _sql(
        "INSERT INTO board_inventory(workspace_id, material_id, len_mm, wid_mm, qty_on_hand)"
        " VALUES (:w, :b, 2440, 1220, 5)",
        w=wid, b=bid,
    )
    mid = _sql("INSERT INTO modules(item_id, module_no) VALUES (:i, 1) RETURNING module_id", i=iid)
    _sql(
        "INSERT INTO parts(module_id, qty, len_mm, wid_mm, board_material_id)"
        " VALUES (:m, 4, 2000, 600, :b)",
        m=mid, b=bid,
    )
    return {"wid": wid, "uid": uid, "iid": iid}


def test_concurrent_generate_serializes_instead_of_raw_500():
    ctx = _bootstrap()
    wid, uid, iid = ctx["wid"], ctx["uid"], ctx["iid"]

    lock_acquired = threading.Event()

    def worker_a():
        s = SessionLocal()
        try:
            q.generate(s, iid, wid, uid)
            lock_acquired.set()
            time.sleep(0.4)  # hold the item row lock so B is forced to wait
            s.commit()
        finally:
            s.close()

    t = threading.Thread(target=worker_a)
    t.start()
    assert lock_acquired.wait(timeout=2), "worker A never reached generate()"

    s2 = SessionLocal()
    try:
        start = time.monotonic()
        with pytest.raises(q.Conflict) as exc_info:
            q.generate(s2, iid, wid, uid)
        elapsed = time.monotonic() - start
        s2.rollback()
    finally:
        s2.close()
    t.join(timeout=2)

    assert elapsed >= 0.3, (
        f"generate() for B did not block on A's lock (elapsed={elapsed:.3f}s) "
        "— the race is back"
    )
    assert exc_info.value.code == "DRAFT_EXISTS"

    rows = _sql("SELECT count(*) FROM material_take WHERE item_id = :i", i=iid)
    assert rows == 1, "worker B must not have inserted a second draft"
